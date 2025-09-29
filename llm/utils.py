# llm/utils.py

import os
import json
import re
import time
import csv
import pandas as pd
from datetime import datetime
from pathlib import Path
import json
from typing import Dict, Any, List
import pandas as pd
from datetime import datetime


def apply_deflection_defaults(answers, questions, deflection_defaults_path="deflection_defaults.csv"):

    deflection_defaults = {}
    paths_to_try = [deflection_defaults_path, os.path.join("..", deflection_defaults_path),
        os.path.join("..", "..", deflection_defaults_path), os.path.abspath(deflection_defaults_path)]
    
    file_found = False
    for path in paths_to_try:
        try:
            with open(path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    deflection_defaults[row['Question']] = row['DefaultAnswer']
            file_found = True
            print(f"Loaded {len(deflection_defaults)} deflection defaults from: {path}")
            break
        except FileNotFoundError:
            continue
    
    if not file_found:
        print(f"Warning: deflection_defaults.csv not found in any expected location. Skipping default application.")
        return answers

    processed_answers = {}
    defaults_applied = 0
    
    for i, question in enumerate(questions):
        qid = f"Q{i+1}"
        
        if qid in answers:
            answer_data = answers[qid]
            
            if isinstance(answer_data, str):
                answer_text = answer_data
                page_info = None
                confidence = 50
            else:
                answer_text = answer_data.get('answer', 'Not Found')
                page_info = answer_data.get('page', None)
                confidence = answer_data.get('confidence', 0)
            
            answer_not_found = (answer_text.lower() in ['not found', 'nan', '', 'error'] or
                              answer_text.startswith('Error'))
            question_has_default = question in deflection_defaults
            
            if answer_not_found and question_has_default:
                processed_answers[qid] = {
                    'answer': deflection_defaults[question],
                    'page': 'Default',
                    'confidence': 95,
                    'source': 'deflection_defaults.csv'
                }
                defaults_applied += 1
                print(f"Applied default for Q{i+1}: {question} = {deflection_defaults[question]}")
            else:
                processed_answers[qid] = {
                    'answer': answer_text if answer_text else 'Not Found',
                    'page': page_info,
                    'confidence': confidence,
                    'source': 'OCR' if not answer_not_found else 'Not Found in Document'
                }
        else:
            processed_answers[qid] = {
                'answer': 'Not Found',
                'page': None,
                'confidence': 0,
                'source': 'Missing'
            }
    
    if defaults_applied > 0:
        print(f"Applied {defaults_applied} deflection defaults out of {len(questions)} questions")
    
    return processed_answers


def normalize_answers_and_units(answers, questions):
    def _uws(s):
        if not isinstance(s, str):
            return s
        s = s.replace("\u00A0", " ").replace("\u202F", " ").replace("\u2007", " ").replace("±", "±").replace(
            """, '"').replace(""", '"')
        return re.sub(r"\s+", " ", s).strip()

    def first_number_token(text):
        t = _uws(text)
        m = re.search(r"(?<![A-Za-z])([±\+\-]?\d+(?:\.\d+)?)(?![A-Za-z])", t)
        return m.group(1) if m else None

    def normalize_decimal(text, places, keep_sign=False):
        t = _uws(text)
        if keep_sign:
            m = re.search(r"(?<![A-Za-z])([±\+\-]\s*\d+(?:\.\d+)?|\d+(?:\.\d+)?)(?![A-Za-z])", t)
        else:
            m = re.search(r"(?<![A-Za-z])([±\+\-]?\d+(?:\.\d+)?)(?![A-Za-z])", t)

        if not m:
            return None

        tok = m.group(1)
        if places is None:
            return tok

        s = tok.strip()
        sign = ""
        if s.startswith(("±", "+", "-")):
            sign = s[0]
            s = s[1:].strip()

        if "." in s:
            intp, frac = s.split(".", 1)
        else:
            intp, frac = s, ""

        frac = (frac + "000000")[:places]
        out = f"{intp}.{frac}" if places > 0 else intp
        return (sign + out) if keep_sign and sign else out

    def canonical_building_code(text):
        t = _uws(text)
        m = re.search(
            r"\b(?P<year>(?:19|20)\d{2})\s+(?P<code>[A-Z][A-Za-z0-9\s()\/\-,&]*?Building Code(?:\s*\([^)]+\))?)\b", t,
            re.I)
        if m:
            code = re.sub(r"^\s*the\s+", "", m.group("code"), flags=re.I).strip().rstrip(" ,;:.")
            return f"{code} {m.group('year')}"

        m = re.search(
            r"\b(?P<code>[A-Z][A-Za-z0-9\s()\/\-,&]*?Building Code(?:\s*\([^)]+\))?)\b(?:\s*,?\s*(?P<year>(?:19|20)\d{2}))?",
            t, re.I)
        if m:
            code = re.sub(r"^\s*the\s+", "", m.group("code"), flags=re.I).strip().rstrip(" ,;:.")
            yr = m.group("year")
            return f"{code} {yr}" if yr else code

        abbr_group = r"(IBC|OBC|CBC|FBC|BCNYS|NYCBC|MSBC|EBC|RCID|Chicago Building Code)"
        m = re.search(rf"\b(?P<year>(?:19|20)\d{{2}})\s*(?P<abbr>{abbr_group})\b", t, re.I)
        if m:
            return f"{m.group('abbr').upper()} {m.group('year')}"

        m = re.search(rf"\b(?P<abbr>{abbr_group})\b(?:\s*(?P<year>(?:19|20)\d{{2}}))?", t, re.I)
        if m:
            abbr = m.group("abbr").upper()
            yr = m.group("year")
            return f"{abbr} {yr}" if yr else abbr
        return None

    def parse_deflection_answer(raw_text, question_num):
        if not isinstance(raw_text, str) or not raw_text.strip():
            return None, ""

        text = " ".join(raw_text.split())

        t = text.lower()
        compact = re.sub(r"\s+", "", t)
        combination = None

        if "d+lr" in compact or re.search(r"\bdead\s*\+\s*roof\s+live\b", t):
            combination = "D+Lr"
        elif "d+l" in compact or re.search(r"\bdead\s*\+\s*live\b", t):
            combination = "D+L"
        elif re.search(r"\broof\s+live(\s+load)?\b", t) or re.search(r"\bLr\b", t):
            combination = "Lr"
        elif re.search(r"\blive\s+load\b", t):
            combination = "L"
        elif "snow" in t:
            combination = "S"
        elif "wind" in t:
            combination = "W"

        results = []
        for m in re.finditer(r"1\s*/\s*(\d{2,4})", text):
            ratio = int(m.group(1))
            results.append({
                "Description": "",
                "Combination": combination or "",
                "LimitRation": ratio,
                "Max": "Null"
            })

        if not results:
            for m in re.finditer(r"\bL\s*/\s*(\d{2,4})", text, flags=re.I):
                ratio = int(m.group(1))
                results.append({
                    "Description": "",
                    "Combination": combination or "",
                    "LimitRation": ratio,
                    "Max": "Null"
                })

        if results:
            labels = {3: "Exterior wall", 4: "Interior wall", 5: "Roof", 6: "Floor", 7: "Ceiling"}
            label = labels.get(question_num, "Deflection")
            return f'{label}: {json.dumps(results, ensure_ascii=False)}', ""

        return None, ""

    unit_patterns = [
        (re.compile(r"(?P<value>[±\+\-]?\d+(?:\.\d+)?)\s*(?P<u>in(?:\.|ch|ches)?|\'|')\b", re.I), "inch"),
        (re.compile(r"(?P<value>[±\+\-]?\d+(?:\.\d+)?)\s*(?P<u>ft(?:\.|)|foot|feet|\'|')\b", re.I), "ft"),
        (re.compile(r"(?P<value>\d+(?:\.\d+)?)\s*(?P<u>miles?\s+per\s+hour|mi/h|mph)\b", re.I), "mph"),
        (re.compile(r"(?P<value>\d+(?:\.\d+)?)\s*(?P<u>(?:pounds?|lb)s?\s*(?:per|/)\s*(?:square\s*foot|sq\.?\s*ft\.?|sf|ft\^2)|psf|lb/ft\^2|lb\s*/\s*sf)\b",
        re.I), "psf"),
        (re.compile(r"(?P<value>\d+(?:\.\d+)?)\s*(?P<u>plf|pounds?\s+per\s+linear\s+foot|lb\s*/\s*ft|lb/ft)\b", re.I), "plf"),
        (re.compile(r"(?P<value>\d+(?:\.\d+)?)\s*(?P<u>psi|ksi|ksf)\b", re.I), lambda m: m.group("u").lower()),]

    enhanced_answers = {}

    for i, question in enumerate(questions):
        qid = f"Q{i + 1}"
        qnum = i + 1

        if qid not in answers:
            continue

        answer_data = answers[qid].copy()
        raw_text = str(answer_data.get('answer', ''))
        t = _uws(raw_text)

        normalized_answer = None
        unit = ""

        if qnum == 1:
            bc = canonical_building_code(t)
            if bc:
                normalized_answer = bc

        elif qnum == 2:
            m = re.search(r"\bASCE\s*7\s*[-–]?\s*(\d{2})\b", t, re.I)
            if m:
                normalized_answer = f"ASCE 7-{m.group(1)}"

        elif qnum in [3, 4, 5, 6, 7]:
            defl_norm, defl_unit = parse_deflection_answer(raw_text, qnum)
            if defl_norm:
                normalized_answer = defl_norm
                unit = defl_unit

        elif qnum == 8:
            v = normalize_decimal(t, places=None, keep_sign=False)
            if v:
                normalized_answer = v

        elif qnum == 9:
            tok = first_number_token(t)
            if tok:
                normalized_answer = tok.split(".")[0]

        elif qnum == 10:
            m = re.search(r"\b(IV|III|II|I)\b", t, re.I)
            if m:
                normalized_answer = m.group(1).upper()
            else:
                m = re.search(r"\b([1-4])\b", t)
                if m:
                    normalized_answer = m.group(1)

        elif qnum == 11:
            m = re.search(r"\b([BCD])\b", t, re.I)
            if m:
                normalized_answer = m.group(1).upper()

        elif qnum == 12:
            v = normalize_decimal(t, places=None, keep_sign=True)
            if v:
                normalized_answer = v

        elif qnum in [13, 15, 19]:
            tok = first_number_token(t)
            if tok:
                normalized_answer = tok.split(".")[0]
                unit = "psf"

        elif qnum == 14:
            tok = first_number_token(t)
            if tok:
                normalized_answer = tok.split(".")[0]
                unit = "plf"

        elif qnum in [16, 18]:
            v = normalize_decimal(t, places=None, keep_sign=False)
            if v:
                normalized_answer = v

        elif qnum == 17:
            v = normalize_decimal(t, places=1, keep_sign=False)
            if v:
                normalized_answer = v

        elif qnum == 20:
            m = re.search(r"\b([ABCD])\b", t, re.I)
            if m:
                normalized_answer = m.group(1).upper()

        elif qnum in [21, 22]:
            v = normalize_decimal(t, places=2, keep_sign=False)
            if v:
                normalized_answer = v

        elif qnum == 23:
            m = re.search(r"\b(A|B|C|D|E|F|BC|CD|DE)\b", t, re.I)
            if m:
                normalized_answer = m.group(1).upper()

        elif qnum in [24, 25]:
            v = normalize_decimal(t, places=3, keep_sign=False)
            if v:
                normalized_answer = v

        if normalized_answer is None:
            for pattern, unit_type in unit_patterns:
                m = pattern.search(t)
                if m:
                    normalized_answer = m.group("value")
                    if callable(unit_type):
                        unit = unit_type(m)
                    else:
                        unit = unit_type
                    break

        if normalized_answer is None:
            tok = first_number_token(t)
            if tok:
                normalized_answer = tok
            else:
                clean_text = re.sub(r"^(the|this)\s+", "", t, flags=re.I)
                clean_text = re.sub(r"\b(is|are|was|were|:)\s+", "", clean_text, count=1, flags=re.I)
                normalized_answer = clean_text.strip() or raw_text

        answer_data['normalized_answer'] = normalized_answer or raw_text
        answer_data['unit'] = unit
        enhanced_answers[qid] = answer_data

    return enhanced_answers


def discover_project_folders(data_dir="data"):
    project_folders = []
    data_path = Path(data_dir)
    
    if data_path.exists():
        for folder in data_path.iterdir():
            if folder.is_dir():
                json_files = list(folder.glob("*_ocr_result*.json"))
                if json_files:
                    project_folders.append(str(folder))
    
    return project_folders


def discover_json_files(data_dir="data"):
    json_files = []
    data_path = Path(data_dir)
    
    if data_path.exists():
        json_files = list(data_path.glob("**/*_ocr_result*.json"))
    
    return [str(f) for f in json_files]


def load_and_combine_documents(json_files=None, data_dir="data", verbose=True):
    if json_files is None:
        json_files = discover_json_files(data_dir)
        if verbose and json_files:
            print(f"Auto-discovered {len(json_files)} JSON files in {data_dir}")
    
    if not json_files:
        if verbose:
            print(f"No JSON files found")
        return [], [], {'filtered_pages_only': []}
    combined_pages = []
    document_info = []
    
    if verbose:
        print(f"Loading {len(json_files)} documents...")
    
    for json_file in json_files:
        if verbose:
            print(f"Loading: {os.path.basename(json_file)}")
        
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                ocr_result = json.load(f)
            
            if 'filtered_pages_only' in ocr_result:
                doc_pages = ocr_result['filtered_pages_only']
            elif 'pages' in ocr_result:
                doc_pages = ocr_result['pages']
            else:
                if verbose:
                    print(f"  Unknown OCR format in {json_file}")
                continue
            
            start_page = len(combined_pages)
            
            for page_idx, page_data in enumerate(doc_pages):
                combined_pages.append(page_data)
                document_info.append({
                    'original_file': json_file,
                    'original_page': page_idx,
                    'combined_page': start_page + page_idx,
                    'doc_name': os.path.basename(json_file).replace('_ocr_result.json', '')
                })
            
            if verbose:
                print(f"   Added {len(doc_pages)} pages")
                
        except Exception as e:
            if verbose:
                print(f"   Error loading {json_file}: {e}")
    
    combined_ocr_result = {'filtered_pages_only': combined_pages}
    
    if verbose:
        print(f"\nTotal: {len(json_files)} documents, {len(combined_pages)} pages")
    
    return combined_pages, document_info, combined_ocr_result


def map_page_to_source(page_info, relevant_page_indices, document_info):

    source_doc = "Unknown"
    original_page = page_info

    if page_info and page_info not in ['N/A', 'Not Found', 'Default']:
        page_num = None

        if isinstance(page_info, int):
            page_num = page_info
        elif isinstance(page_info, str) and page_info.isdigit():
            page_num = int(page_info)
        elif isinstance(page_info, str):
            import re
            match = re.search(r'\d+', str(page_info))
            if match:
                page_num = int(match.group())
        
        if page_num is not None:
            try:
                if 0 <= page_num < len(relevant_page_indices):
                    combined_page_idx = relevant_page_indices[page_num]
                    if 0 <= combined_page_idx < len(document_info):
                        doc_info = document_info[combined_page_idx]
                        source_doc = doc_info['doc_name']
                        original_page = f"{doc_info['original_page']} (from {source_doc})"
                        return source_doc, original_page
                
                if 0 <= page_num < len(document_info):
                    doc_info = document_info[page_num]
                    source_doc = doc_info['doc_name']
                    original_page = f"{doc_info['original_page']} (from {source_doc})"
                    return source_doc, original_page
                
                for i, rel_page_idx in enumerate(relevant_page_indices):
                    if 0 <= rel_page_idx < len(document_info):
                        doc_info = document_info[rel_page_idx]
                        if doc_info['original_page'] == page_num or doc_info['combined_page'] == page_num:
                            source_doc = doc_info['doc_name']
                            original_page = f"{doc_info['original_page']} (from {source_doc})"
                            return source_doc, original_page
                            
            except (ValueError, IndexError, TypeError) as e:
                pass
    
    if relevant_page_indices and len(relevant_page_indices) > 0:
        try:
            first_relevant_idx = relevant_page_indices[0]
            if 0 <= first_relevant_idx < len(document_info):
                doc_info = document_info[first_relevant_idx]
                source_doc = doc_info['doc_name']
                if page_info and page_info not in ['N/A', 'Not Found']:
                    original_page = f"{page_info} (from {source_doc})"
                else:
                    original_page = f"from {source_doc}"
        except (IndexError, TypeError):
            pass
    
    return source_doc, original_page


def display_processing_summary(results, found_answers, total_questions, combined_pages, verbose=True):
    if verbose:
        print(f"Questions answered: {found_answers}/{total_questions} ({found_answers/total_questions*100:.1f}%)")
        print(f"Completed at: {datetime.now().strftime('%H:%M:%S')}")
        total_pages_searched = sum(r.get('pages_searched', 0) for r in results)
        avg_pages_per_question = total_pages_searched / len(results) if results else 0
        print(f"Efficiency: Averaged {avg_pages_per_question:.1f} pages per question (vs {len(combined_pages)} total)")


def export_results_summary(results, output_folder=None, filename_prefix="pipeline_results_v4", project_name=None):
    df = pd.DataFrame(results)
    successful_results = [r for r in results if r['answer'] != 'Not Found' and not r['answer'].startswith('Error')]

    print(f"  Successful answers: {len(successful_results)}/{len(results)} ({len(successful_results)/len(results)*100:.1f}%)")
    
    if successful_results:
        avg_confidence = sum(r['confidence'] for r in successful_results) / len(successful_results)
        print(f" Average confidence: {avg_confidence:.1f}%")

        doc_counts = {}
        for result in successful_results:
            doc = result['source_document']
            if doc != "Unknown" and doc != "Error":
                doc_counts[doc] = doc_counts.get(doc, 0) + 1
        
        if doc_counts:
            print(f" Answers by document:")
            for doc, count in doc_counts.items():
                print(f"      • {doc}: {count} answers")

    print(f"\nKEY SUCCESSFUL ANSWERS:")
    for result in successful_results[:10]:  # Show first 10
        print(f"   Q{result['question_number']}: {result['answer'][:70]}... ({result['confidence']}%)")

    if output_folder is None:
        output_folder = "."
        if results and results[0].get('source_document') != 'Error':
            output_folder = "data"
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    if project_name:
        output_filename = f"{filename_prefix}_{project_name}_{timestamp}.csv"
    else:
        output_filename = f"{filename_prefix}_{timestamp}.csv"
    output_path = os.path.join(output_folder, output_filename)
    
    os.makedirs(output_folder, exist_ok=True)
    
    df.to_csv(output_path, index=False, encoding='utf-8')
    file_size = os.path.getsize(output_path)
    
    print(f"\nEXPORT COMPLETE:")
    print(f"   File: {output_path}")
    print(f"   Rows: {len(df)}")
    print(f"   Size: {file_size:,} bytes")
    print(f"   Columns: {list(df.columns)}")
    
    print(f"Ready for engineering analysis with {len(successful_results)} successful answers!")
    
    return df, output_path, successful_results


def get_efficiency_metrics(results, combined_pages):
    total_pages_searched = sum(r.get('pages_searched', 0) for r in results)
    avg_pages_per_question = total_pages_searched / len(results) if results else 0
    successful_results = [r for r in results if r['answer'] != 'Not Found' and not r['answer'].startswith('Error')]
    
    return {
        'total_questions': len(results),
        'successful_answers': len(successful_results),
        'success_rate': len(successful_results) / len(results) * 100 if results else 0,
        'avg_confidence': sum(r['confidence'] for r in successful_results) / len(successful_results) if successful_results else 0,
        'total_pages_searched': total_pages_searched,
        'avg_pages_per_question': avg_pages_per_question,
        'total_pages_available': len(combined_pages),
        'efficiency_ratio': avg_pages_per_question / len(combined_pages) if combined_pages else 0
    }


def answers_with_coordinates(processed_answers: Dict[str, Dict], questions: List[str]) -> Dict[str, Dict]:
    coordinated_answer = {}

    for i, question in enumerate(questions, 1):
        qid = f"Q{i + 1}"

        if qid not in processed_answers:
            continue

        answer_data = processed_answers[qid]

        coordinated_answer = {
            'answer': answer_data.get('answer', 'Not Found'),
            'page': answer_data.get('page', 'N/A'),
            'confidence': answer_data.get('confidence', 0),
            'source': answer_data.get('source', 'Unknown'),
            'normalized_answer': answer_data.get('normalized_answer', answer_data.get('answer', '')),
            'unit': answer_data.get('unit', ''),
        }

        if 'coordinates' in answer_data:
            coordinated_answer['coordinates'] = answer_data['coordinates']
            coordinated_answer['has_coordinates'] = True

            coords = answer_data['coordinates']
            if 'bounding_box' in coords:
                bbox = coords['bounding_box']
                coordinated_answer['coordinate_summary'] = {
                    'x': bbox.get('x', 0),
                    'y': bbox.get('y', 0),
                    'width': bbox.get('width', 0),
                    'height': bbox.get('height', 0),
                    'match_confidence': coords.get('confidence_score', 0),
                    'match_type': coords.get('match_type', 'unknown')
                }
        else:
            coordinated_answer['has_coordinates'] = False
            coordinated_answer['coordinates'] = None
            coordinated_answer['coordinate_summary'] = None

        coordinated_answer[qid] = coordinated_answer

    return coordinated_answer


def format_coordinates_for_output(coordinate_data: Dict[str, Any]) -> str:
    if not coordinate_data or not coordinate_data.get('bounding_box'):
        return "No coordinates"
    bbox = coordinate_data['bounding_box']
    match_type = coordinate_data.get('match_type', 'unknown')
    confidence = coordinate_data.get('confidence_score', 0)
    return f"x:{bbox['x']}, y:{bbox['y']}, w:{bbox['width']}, h:{bbox['height']} ({match_type}, {confidence:.1f}%)"


def create_coordinate_json_output(results_data: List[Dict], output_path: str) -> None:
    output = {'metadata': {'coordinate_tracking_enabled': True,
            'coordinate_algorithm': 'fuzzy_text_matching',
            'coordinate_fields_explanation': {
                'coordinates': 'Full coordinate mapping data',
                'coordinate_summary': 'Quick access to key coordinate info',
                'has_coordinates': 'Boolean indicating if coordinates were found'}}, 'results': results_data}

    with open(output_path, 'w') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)


def normalize_answers_and_units_with_coordinates(answers: Dict[str, Dict], questions: List[str]) -> Dict[str, Dict]:
    normalized = normalize_answers_and_units(answers, questions)
    for qid in normalized:
        if qid in answers and isinstance(answers[qid], dict):
            original_answer = answers[qid]
            if 'coordinates' in original_answer:
                normalized[qid]['coordinates'] = original_answer['coordinates']
                normalized[qid]['has_coordinates'] = original_answer.get('has_coordinates', True)

            if 'raw_response' in original_answer:
                normalized[qid]['raw_response'] = original_answer['raw_response']
    return normalized


def apply_deflection_defaults_with_coordinates(answers: Dict[str, Dict], questions: List[str],deflection_defaults_path: str = "deflection_defaults.csv") -> Dict[str, Dict]:

    processed = apply_deflection_defaults(answers, questions, deflection_defaults_path)
    for qid in processed:
        if qid in answers and isinstance(answers[qid], dict):
            original_answer = answers[qid]

            if processed[qid].get('source') != 'deflection_defaults.csv':
                if 'coordinates' in original_answer:
                    processed[qid]['coordinates'] = original_answer['coordinates']
                    processed[qid]['has_coordinates'] = original_answer.get('has_coordinates', True)

                if 'raw_response' in original_answer:
                    processed[qid]['raw_response'] = original_answer['raw_response']
            else:
                processed[qid]['has_coordinates'] = False
                processed[qid]['coordinates'] = None

    return processed


def export_results_with_coordinates(results: List[Dict], output_folder: str, filename_prefix: str = "pipeline_results_with_coords", project_name: str = None) -> Dict[str, str]:

    csv_data = []
    for result in results:
        csv_row = result.copy()

        if result.get('has_coordinates') and result.get('coordinate_summary'):
            coord_summary = result['coordinate_summary']
            csv_row.update({'Coord_X': coord_summary.get('x', 0), 'Coord_Y': coord_summary.get('y', 0),
                'Coord_Width': coord_summary.get('width', 0),
                'Coord_Height': coord_summary.get('height', 0),
                'Coord_Match_Type': coord_summary.get('match_type', 'none'),
                'Coord_Match_Confidence': coord_summary.get('match_confidence', 0), 'Coordinates_Found': 'Yes'})
        else:
            csv_row.update({'Coord_X': 0, 'Coord_Y': 0, 'Coord_Width': 0, 'Coord_Height': 0,
                'Coord_Match_Type': 'none', 'Coord_Match_Confidence': 0, 'Coordinates_Found': 'No'})

        csv_data.append(csv_row)

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    if project_name:
        base_name = f"{filename_prefix}_{project_name}_{timestamp}"
    else:
        base_name = f"{filename_prefix}_{timestamp}"

    csv_path = f"{output_folder}/{base_name}.csv"
    json_path = f"{output_folder}/{base_name}_with_coordinates.json"

    df = pd.DataFrame(csv_data)
    df.to_csv(csv_path, index=False)

    create_coordinate_json_output(results, json_path)

    coord_count = sum(1 for r in results if r.get('has_coordinates'))
    print(f"Coordinate tracking results:")
    print(f"  Total answers: {len(results)}")
    print(f"  With coordinates: {coord_count}")
    print(f"  Success rate: {coord_count / len(results) * 100:.1f}%")
    print(f"  Files created: {csv_path}, {json_path}")

    return {'csv_path': csv_path, 'json_path': json_path, 'coordinate_success_rate': coord_count / len(results) * 100 if results else 0}