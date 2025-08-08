"""
Utils.py - Utility functions extracted from Pipeline Script v3

This module contains all the optimized functions and utilities used in the 
pipeline.ipynb notebook for efficient document processing.

Functions:
- find_relevant_pages(): Smart page filtering with keyword matching
- load_and_combine_documents(): Multi-document loading and combination
- process_questions_optimized(): Optimized question processing with smart filtering
- export_results_summary(): Enhanced results display and export
- map_page_to_source(): Map page numbers back to source documents
"""

import os
import json
import re
import time
import csv
import pandas as pd
from datetime import datetime
from pathlib import Path


def apply_deflection_defaults(answers, questions, deflection_defaults_path="deflection_defaults.csv"):
    """
    Apply default deflection values for deflection-related questions if not found in OCR.
    
    Args:
        answers (dict): Dictionary of answers from LLM processing
        questions (list): List of questions processed
        deflection_defaults_path (str): Path to deflection defaults CSV file
    
    Returns:
        dict: Processed answers with deflection defaults applied where appropriate
    """
    # Load deflection defaults - try multiple paths
    deflection_defaults = {}
    paths_to_try = [
        deflection_defaults_path,  # Original path
        os.path.join("..", deflection_defaults_path),  # Parent directory
        os.path.join("..", "..", deflection_defaults_path),  # Two levels up
        os.path.abspath(deflection_defaults_path)  # Absolute path
    ]
    
    file_found = False
    for path in paths_to_try:
        try:
            with open(path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    deflection_defaults[row['Question']] = row['DefaultAnswer']
            file_found = True
            print(f"✅ Loaded {len(deflection_defaults)} deflection defaults from: {path}")
            break
        except FileNotFoundError:
            continue
    
    if not file_found:
        print(f"Warning: deflection_defaults.csv not found in any expected location. Skipping default application.")
        return answers
    
    # Process each answer
    processed_answers = {}
    defaults_applied = 0
    
    for i, question in enumerate(questions):
        qid = f"Q{i+1}"
        
        if qid in answers:
            answer_data = answers[qid]
            
            # Handle both old format (string) and new format (dict)
            if isinstance(answer_data, str):
                answer_text = answer_data
                page_info = None
                confidence = 50
            else:
                answer_text = answer_data.get('answer', 'Not Found')
                page_info = answer_data.get('page', None)
                confidence = answer_data.get('confidence', 0)
            
            # Check if this is a deflection question and answer was not found
            answer_not_found = (answer_text.lower() in ['not found', 'nan', '', 'error'] or 
                              answer_text.startswith('Error'))
            question_has_default = question in deflection_defaults
            
            if answer_not_found and question_has_default:
                # Apply default value for deflection questions only
                processed_answers[qid] = {
                    'answer': deflection_defaults[question],
                    'page': 'Default',
                    'confidence': 95,
                    'source': 'deflection_defaults.csv'
                }
                defaults_applied += 1
                print(f"✅ Applied default for Q{i+1}: {question} = {deflection_defaults[question]}")
            else:
                # Keep original answer - including "Not Found" for non-deflection questions
                processed_answers[qid] = {
                    'answer': answer_text if answer_text else 'Not Found',
                    'page': page_info,
                    'confidence': confidence,
                    'source': 'OCR' if not answer_not_found else 'Not Found in Document'
                }
        else:
            # No answer found at all
            processed_answers[qid] = {
                'answer': 'Not Found',
                'page': None,
                'confidence': 0,
                'source': 'Missing'
            }
    
    if defaults_applied > 0:
        print(f"🎯 Applied {defaults_applied} deflection defaults out of {len(questions)} questions")
    
    return processed_answers


def find_relevant_pages(question, pages_data, max_pages=5):
    """
    Find most relevant pages using improved keyword matching.
    
    This function implements smart filtering to identify the most relevant pages
    for a given question, reducing processing time and improving accuracy.
    
    Args:
        question (str): The question to find relevant pages for
        pages_data (list): List of page data dictionaries
        max_pages (int): Maximum number of pages to return (default: 5)
    
    Returns:
        list: Indices of the most relevant pages, sorted by relevance score
    """
    keywords = {
        'building code': ['IBC', 'building code', 'NYSBC', 'NYCBC', 'code'],
        'ASCE': ['ASCE', 'ASCE 7', 'standard'],
        'deflection': ['deflection', 'L/', 'vertical', 'horizontal', 'wall'],
        'wind': ['wind', 'exposure', 'pressure', 'GCpi', 'mph'],
        'snow': ['snow', 'Pg', 'Is =', 'Ce =', 'Ct', 'Pf'],
        'load': ['load', 'live', 'dead', 'roof'],
        'seismic': ['seismic', 'Sds', 'Sd1', 'site class', 'importance']
    }
    
    question_lower = question.lower()
    relevant_keywords = []
    for category, words in keywords.items():
        if any(word.lower() in question_lower for word in words):
            relevant_keywords.extend(words)
    
    # Refined keywords to avoid false positives
    refined_keywords = []
    for keyword in relevant_keywords:
        if keyword in ['Is', 'Ce']:
            refined_keywords.extend([f'{keyword} =', f'{keyword}='])
        else:
            refined_keywords.append(keyword)
    
    # Score pages by keyword relevance
    page_scores = []
    for i, page in enumerate(pages_data):
        text = page.get('extracted_text', '').lower()
        score = 0
        
        for keyword in refined_keywords:
            keyword_lower = keyword.lower()
            
            if any(param in keyword_lower for param in ['is =', 'ce =', 'pg', 'ct', 'pf']):
                if 'is =' in keyword_lower:
                    pattern = r'\bis\s*=\s*[\d.]+|\bimportance\s+factor\s*=\s*[\d.]+|\bis\s*[\d.]+\b'
                    if re.search(pattern, text, re.IGNORECASE):
                        score += 10
                elif 'ce =' in keyword_lower:
                    pattern = r'\bce\s*=\s*[\d.]+|\bexposure\s+factor\s*=\s*[\d.]+|\bce\s*[\d.]+\b'
                    if re.search(pattern, text, re.IGNORECASE):
                        score += 10
                else:
                    pattern = rf'\b{keyword_lower}\s*=\s*[\d.]+|\b{keyword_lower}\s*[\d.]+\b'
                    if re.search(pattern, text, re.IGNORECASE):
                        score += 8
            else:
                count = text.count(keyword_lower)
                if len(keyword_lower) <= 2 and keyword_lower.isalpha():
                    pattern = rf'\b{re.escape(keyword_lower)}\b'
                    matches = re.findall(pattern, text, re.IGNORECASE)
                    count = len(matches)
                score += count
        
        if score > 0:
            page_scores.append((i, score))
    
    if page_scores:
        page_scores.sort(key=lambda x: x[1], reverse=True)
        return [page_idx for page_idx, score in page_scores[:max_pages]]
    else:
        return list(range(min(max_pages, len(pages_data))))


def discover_project_folders(data_dir="data"):
    """
    Discover all project folders in the data directory.
    
    Args:
        data_dir (str): Base data directory containing project folders
    
    Returns:
        list: List of project folder paths that contain JSON files
    """
    project_folders = []
    data_path = Path(data_dir)
    
    if data_path.exists():
        # Find all subdirectories that contain JSON files
        for folder in data_path.iterdir():
            if folder.is_dir():
                json_files = list(folder.glob("*_ocr_result*.json"))
                if json_files:
                    project_folders.append(str(folder))
    
    return project_folders


def discover_json_files(data_dir="data"):
    """
    Discover all OCR JSON files in project directories.
    
    Args:
        data_dir (str): Base data directory containing project folders
    
    Returns:
        list: List of paths to OCR JSON files found
    """
    json_files = []
    data_path = Path(data_dir)
    
    if data_path.exists():
        # Look for JSON files in all subdirectories
        json_files = list(data_path.glob("**/*_ocr_result*.json"))
    
    return [str(f) for f in json_files]


def load_and_combine_documents(json_files=None, data_dir="data", verbose=True):
    """
    Load and combine multiple OCR JSON files into a single structure.
    
    Args:
        json_files (list, optional): List of paths to OCR JSON files. If None, auto-discover from data_dir
        data_dir (str): Base data directory to search for JSON files (used if json_files is None)
        verbose (bool): Whether to print loading progress
    
    Returns:
        tuple: (combined_pages, document_info, combined_ocr_result)
            - combined_pages: List of all pages from all documents
            - document_info: List of document mapping information
            - combined_ocr_result: Combined OCR result structure
    """
    # Auto-discover JSON files if not provided
    if json_files is None:
        json_files = discover_json_files(data_dir)
        if verbose and json_files:
            print(f"🔍 Auto-discovered {len(json_files)} JSON files in {data_dir}")
    
    if not json_files:
        if verbose:
            print(f"❌ No JSON files found")
        return [], [], {'filtered_pages_only': []}
    combined_pages = []
    document_info = []
    
    if verbose:
        print(f"📄 Loading {len(json_files)} documents...")
    
    for json_file in json_files:
        if verbose:
            print(f"📄 Loading: {os.path.basename(json_file)}")
        
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                ocr_result = json.load(f)
            
            # Handle different OCR result formats
            if 'filtered_pages_only' in ocr_result:
                doc_pages = ocr_result['filtered_pages_only']
            elif 'pages' in ocr_result:
                doc_pages = ocr_result['pages']
            else:
                if verbose:
                    print(f"   ❌ Unknown OCR format in {json_file}")
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
                print(f"   ✅ Added {len(doc_pages)} pages")
                
        except Exception as e:
            if verbose:
                print(f"   ❌ Error loading {json_file}: {e}")
    
    combined_ocr_result = {'filtered_pages_only': combined_pages}
    
    if verbose:
        print(f"\n📊 Total: {len(json_files)} documents, {len(combined_pages)} pages")
    
    return combined_pages, document_info, combined_ocr_result


def map_page_to_source(page_info, relevant_page_indices, document_info):
    """
    Map page information back to the source document.
    
    Args:
        page_info: Page information from LLM response
        relevant_page_indices (list): List of relevant page indices used
        document_info (list): Document mapping information
    
    Returns:
        tuple: (source_doc, original_page) - mapped source information
    """
    source_doc = "Unknown"
    original_page = page_info
    
    # Debug: Print mapping details
    # print(f"🔍 Mapping page_info: {page_info}, type: {type(page_info)}")
    # print(f"   Relevant indices: {relevant_page_indices[:5]}...")  # Show first 5
    # print(f"   Document info length: {len(document_info)}")
    
    # Handle various page_info formats
    if page_info and page_info not in ['N/A', 'Not Found', 'Default']:
        # Try to extract page number from different formats
        page_num = None
        
        # Case 1: Direct integer
        if isinstance(page_info, int):
            page_num = page_info
        # Case 2: String representation of integer
        elif isinstance(page_info, str) and page_info.isdigit():
            page_num = int(page_info)
        # Case 3: Handle "page X" format
        elif isinstance(page_info, str):
            # Try to extract number from strings like "page 5", "5", etc.
            import re
            match = re.search(r'\d+', str(page_info))
            if match:
                page_num = int(match.group())
        
        if page_num is not None:
            try:
                # Method 1: If page_num is index into relevant_page_indices
                if 0 <= page_num < len(relevant_page_indices):
                    combined_page_idx = relevant_page_indices[page_num]
                    if 0 <= combined_page_idx < len(document_info):
                        doc_info = document_info[combined_page_idx]
                        source_doc = doc_info['doc_name']
                        original_page = f"{doc_info['original_page']} (from {source_doc})"
                        return source_doc, original_page
                
                # Method 2: If page_num is direct index into document_info
                if 0 <= page_num < len(document_info):
                    doc_info = document_info[page_num]
                    source_doc = doc_info['doc_name']
                    original_page = f"{doc_info['original_page']} (from {source_doc})"
                    return source_doc, original_page
                
                # Method 3: Search for page number in relevant pages
                for i, rel_page_idx in enumerate(relevant_page_indices):
                    if 0 <= rel_page_idx < len(document_info):
                        doc_info = document_info[rel_page_idx]
                        # Check if this matches the page number we're looking for
                        if doc_info['original_page'] == page_num or doc_info['combined_page'] == page_num:
                            source_doc = doc_info['doc_name']
                            original_page = f"{doc_info['original_page']} (from {source_doc})"
                            return source_doc, original_page
                            
            except (ValueError, IndexError, TypeError) as e:
                # print(f"   ❌ Mapping error: {e}")
                pass
    
    # Fallback: If we can't map properly, try to get source from first relevant page
    if relevant_page_indices and len(relevant_page_indices) > 0:
        try:
            first_relevant_idx = relevant_page_indices[0]
            if 0 <= first_relevant_idx < len(document_info):
                doc_info = document_info[first_relevant_idx]
                source_doc = doc_info['doc_name']
                # Keep original page info but add source context
                if page_info and page_info not in ['N/A', 'Not Found']:
                    original_page = f"{page_info} (from {source_doc})"
                else:
                    original_page = f"from {source_doc}"
        except (IndexError, TypeError):
            pass
    
    return source_doc, original_page


def process_questions_optimized(questions, combined_pages, combined_ocr_result, 
                              document_info, llm_interface, verbose=True, apply_defaults=True):
    """
    Process all questions with optimized smart filtering and deflection defaults.
    
    Args:
        questions (list): List of questions to process
        combined_pages (list): Combined pages from all documents
        combined_ocr_result (dict): Combined OCR result structure
        document_info (list): Document mapping information
        llm_interface: LLM interface for processing
        verbose (bool): Whether to print processing progress
        apply_defaults (bool): Whether to apply deflection defaults
    
    Returns:
        tuple: (results, found_answers, total_questions) - processing results
    """
    results = []
    found_answers = 0
    total_questions = len(questions)
    
    # Step 1: Process all questions and collect raw answers
    raw_answers = {}
    
    if verbose:
        print(f"Processing {total_questions} questions with smart filtering...")
        print()
    
    for i, question in enumerate(questions, 1):
        if verbose:
            print(f"❓ Question {i}/{total_questions}: {question}")
        
        try:
            # Find most relevant pages (max 5)
            relevant_page_indices = find_relevant_pages(question, combined_pages, max_pages=5)
            if verbose:
                print(f"   📄 Searching {len(relevant_page_indices)} most relevant pages")
            
            # Process with LLM
            answer_data = llm_interface.answer_question(
                question, combined_ocr_result, relevant_page_indices
            )
            
            # Store raw answer
            qid = f"Q{i}"
            raw_answers[qid] = answer_data
            
            # Display raw result
            if answer_data['answer'] not in ["Not Found", "Error"] and not answer_data['answer'].startswith('Error'):
                if verbose:
                    print(f"   ✅ Raw Answer: {answer_data['answer']}")
                    print(f"   📊 Confidence: {answer_data['confidence']}%")
            else:
                if verbose:
                    print(f"   ❌ Not found")
            
        except Exception as e:
            if verbose:
                print(f"   ❌ Error: {e}")
            qid = f"Q{i}"
            raw_answers[qid] = {
                'answer': f'Error: {str(e)}',
                'page': 'N/A',
                'confidence': 0
            }
        
        # Small delay for rate limit prevention
        time.sleep(0.5)
        if verbose:
            print()
    
    # Step 2: Apply deflection defaults if enabled
    if apply_defaults:
        if verbose:
            print("🔧 Applying deflection defaults...")
        processed_answers = apply_deflection_defaults(raw_answers, questions)
    else:
        # Convert raw answers to processed format
        processed_answers = {}
        for i, question in enumerate(questions):
            qid = f"Q{i+1}"
            if qid in raw_answers:
                answer_data = raw_answers[qid]
                processed_answers[qid] = {
                    'answer': answer_data['answer'],
                    'page': answer_data['page'],
                    'confidence': answer_data['confidence'],
                    'source': 'OCR' if answer_data['answer'] not in ["Not Found", "Error"] and not answer_data['answer'].startswith('Error') else 'Not Found in Document'
                }
    
    # Step 3: Create final results with source mapping
    for i, question in enumerate(questions, 1):
        qid = f"Q{i}"
        
        if qid in processed_answers:
            answer_info = processed_answers[qid]
            
            # Map back to source document (only for non-default answers)
            if answer_info.get('source') != 'deflection_defaults.csv':
                # Find the relevant pages that were used for this question
                relevant_page_indices = find_relevant_pages(question, combined_pages, max_pages=5)
                
                # Debug: Print mapping details for first few questions
                if i <= 3 and verbose:
                    print(f"🔍 Debug Q{i}: page='{answer_info['page']}', relevant_indices={relevant_page_indices[:3]}...")
                    print(f"    Doc info sample: {document_info[:2] if document_info else 'None'}")
                
                source_doc, original_page = map_page_to_source(
                    answer_info['page'], relevant_page_indices, document_info
                )
                
                if i <= 3 and verbose:
                    print(f"    → Mapped to: source='{source_doc}', page='{original_page}'")
            else:
                source_doc = "Default"
                original_page = "deflection_defaults.csv"
            
            # Count successful answers
            if answer_info['answer'] not in ["Not Found", "Error"] and not answer_info['answer'].startswith('Error'):
                found_answers += 1
            
            results.append({
                'question_number': i,
                'question': question,
                'answer': answer_info['answer'],
                'page': original_page,
                'source_document': source_doc,
                'confidence': answer_info['confidence'],
                'pages_searched': len(find_relevant_pages(question, combined_pages, max_pages=5)),
                'timestamp': datetime.now().isoformat(),
                'source': answer_info.get('source', 'OCR')
            })
        else:
            # Fallback for missing answers
            results.append({
                'question_number': i,
                'question': question,
                'answer': 'Not Found',
                'page': 'N/A',
                'source_document': 'Error',
                'confidence': 0,
                'pages_searched': 0,
                'timestamp': datetime.now().isoformat(),
                'source': 'Missing'
            })
    
    if verbose and apply_defaults:
        defaults_applied = len([r for r in results if r.get('source') == 'deflection_defaults.csv'])
        if defaults_applied > 0:
            print(f"✅ Applied {defaults_applied} deflection defaults in final results")
    
    return results, found_answers, total_questions


def display_processing_summary(results, found_answers, total_questions, combined_pages, verbose=True):
    """
    Display comprehensive processing summary and efficiency metrics.
    
    Args:
        results (list): Processing results
        found_answers (int): Number of successful answers
        total_questions (int): Total number of questions processed
        combined_pages (list): Combined pages from all documents
        verbose (bool): Whether to print detailed summary
    """
    if verbose:
        print("=" * 60)
        print("📊 PROCESSING COMPLETE")
        print("=" * 60)
        print(f"✅ Questions answered: {found_answers}/{total_questions} ({found_answers/total_questions*100:.1f}%)")
        print(f"⏰ Completed at: {datetime.now().strftime('%H:%M:%S')}")
        
        # Efficiency metrics
        total_pages_searched = sum(r.get('pages_searched', 0) for r in results)
        avg_pages_per_question = total_pages_searched / len(results) if results else 0
        print(f"🔧 Efficiency: Averaged {avg_pages_per_question:.1f} pages per question (vs {len(combined_pages)} total)")


def export_results_summary(results, output_folder=None, filename_prefix="pipeline_results_v4", project_name=None):
    """
    Enhanced results display and export with detailed statistics.
    
    Args:
        results (list): Processing results
        output_folder (str, optional): Output folder for CSV export. If None, uses first document's folder
        filename_prefix (str): Prefix for output filename
        project_name (str, optional): Project name to include in filename
    
    Returns:
        tuple: (df, output_path, successful_results) - DataFrame, output path, and successful results
    """
    print("📋 RESULTS SUMMARY")
    print("=" * 80)
    
    # Create summary DataFrame
    df = pd.DataFrame(results)
    successful_results = [r for r in results if r['answer'] != 'Not Found' and not r['answer'].startswith('Error')]
    
    # Display summary statistics
    print(f"📊 SUMMARY STATISTICS:")
    print(f"   ✅ Successful answers: {len(successful_results)}/{len(results)} ({len(successful_results)/len(results)*100:.1f}%)")
    
    if successful_results:
        avg_confidence = sum(r['confidence'] for r in successful_results) / len(successful_results)
        print(f"   📈 Average confidence: {avg_confidence:.1f}%")
        
        # Document breakdown
        doc_counts = {}
        for result in successful_results:
            doc = result['source_document']
            if doc != "Unknown" and doc != "Error":
                doc_counts[doc] = doc_counts.get(doc, 0) + 1
        
        if doc_counts:
            print(f"   📄 Answers by document:")
            for doc, count in doc_counts.items():
                print(f"      • {doc}: {count} answers")
    
    # Display key successful answers
    print(f"\n🏆 KEY SUCCESSFUL ANSWERS:")
    for result in successful_results[:10]:  # Show first 10
        print(f"   Q{result['question_number']}: {result['answer'][:70]}... ({result['confidence']}%)")
    
    # Determine output folder
    if output_folder is None:
        # Use the directory of the first result or default to current directory
        output_folder = "."
        if results and results[0].get('source_document') != 'Error':
            # Try to find the project folder from document info
            output_folder = "data"
    
    # Export to CSV with project name
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    if project_name:
        output_filename = f"{filename_prefix}_{project_name}_{timestamp}.csv"
    else:
        output_filename = f"{filename_prefix}_{timestamp}.csv"
    output_path = os.path.join(output_folder, output_filename)
    
    # Ensure output directory exists
    os.makedirs(output_folder, exist_ok=True)
    
    df.to_csv(output_path, index=False, encoding='utf-8')
    file_size = os.path.getsize(output_path)
    
    print(f"\n💾 EXPORT COMPLETE:")
    print(f"   📁 File: {output_path}")
    print(f"   📊 Rows: {len(df)}")
    print(f"   📏 Size: {file_size:,} bytes")
    print(f"   📋 Columns: {list(df.columns)}")
    
    print(f"\n✅ Pipeline v4 processing complete!")
    print(f"🎉 Ready for engineering analysis with {len(successful_results)} successful answers!")
    
    return df, output_path, successful_results


def get_efficiency_metrics(results, combined_pages):
    """
    Calculate and return efficiency metrics for the processing.
    
    Args:
        results (list): Processing results
        combined_pages (list): Combined pages from all documents
    
    Returns:
        dict: Dictionary containing efficiency metrics
    """
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


# Example usage function
def run_complete_pipeline_v4(data_dir="data", questions=None, llm_interface=None, output_folder=None, verbose=True):
    """
    Complete pipeline execution using all utility functions.
    
    Args:
        data_dir (str): Base data directory containing project folders with JSON files
        questions (list, optional): List of questions to process. If None, loads from config
        llm_interface (optional): LLM interface for processing. If None, creates from config
        output_folder (str, optional): Output folder for results. If None, uses data directory
        verbose (bool): Whether to print detailed progress
    
    Returns:
        dict: Complete processing results and metrics
    """
    if verbose:
        print("🚀 COMPLETE PIPELINE v4 EXECUTION")
        print("=" * 60)
    
    # Load config and initialize LLM if not provided
    if questions is None or llm_interface is None:
        from llm_tools.config_loader import ConfigLoader
        from llm_tools.llm_interface import LLMInterface
        
        config = ConfigLoader.load("llm_tools/config.yaml")
        if questions is None:
            questions = config['questions']
        if llm_interface is None:
            llm_interface = LLMInterface(config)
    
    # Step 1: Load and combine documents (auto-discover from data_dir)
    combined_pages, document_info, combined_ocr_result = load_and_combine_documents(
        json_files=None, data_dir=data_dir, verbose=verbose
    )
    
    if not combined_pages:
        if verbose:
            print("❌ No documents found to process")
        return None
    
    # Step 2: Process questions with optimization
    results, found_answers, total_questions = process_questions_optimized(
        questions, combined_pages, combined_ocr_result, document_info, llm_interface, verbose=verbose
    )
    
    # Step 3: Display processing summary
    if verbose:
        display_processing_summary(results, found_answers, total_questions, combined_pages)
    
    # Step 4: Export results with summary (include project name in filename)
    if output_folder is None:
        output_folder = data_dir
    
    # Extract project name from data_dir path
    project_name = os.path.basename(data_dir) if data_dir else None
    
    df, output_path, successful_results = export_results_summary(
        results, output_folder, filename_prefix="pipeline_results_v4", project_name=project_name
    )
    
    # Step 5: Get efficiency metrics
    metrics = get_efficiency_metrics(results, combined_pages)
    
    return {
        'results': results,
        'dataframe': df,
        'output_path': output_path,
        'successful_results': successful_results,
        'metrics': metrics,
        'combined_pages': combined_pages,
        'document_info': document_info
    }


def run_pipeline_per_project(data_dir="data", questions=None, llm_interface=None, verbose=True):
    """
    Process each project folder separately and save results in respective folders.
    
    Args:
        data_dir (str): Base data directory containing project folders
        questions (list, optional): List of questions to process
        llm_interface (optional): LLM interface for processing
        verbose (bool): Whether to print detailed progress
    
    Returns:
        dict: Results for all projects with per-project metrics
    """
    if verbose:
        print("🚀 PROJECT-BASED PIPELINE v4 EXECUTION")
        print("=" * 60)
    
    # Load config and initialize LLM if not provided
    if questions is None or llm_interface is None:
        from llm_tools.config_loader import ConfigLoader
        from llm_tools.llm_interface import LLMInterface
        
        config = ConfigLoader.load("llm_tools/config.yaml")
        if questions is None:
            questions = config['questions']
        if llm_interface is None:
            llm_interface = LLMInterface(config)
    
    # Discover project folders
    project_folders = discover_project_folders(data_dir)
    
    if not project_folders:
        if verbose:
            print(f"❌ No project folders with JSON files found in {data_dir}")
        return None
    
    if verbose:
        print(f"📁 Found {len(project_folders)} project folders:")
        for folder in project_folders:
            print(f"   • {os.path.basename(folder)}")
        print()
    
    all_project_results = {}
    overall_stats = {
        'total_projects': len(project_folders),
        'successful_projects': 0,
        'total_questions': 0,
        'total_answers': 0,
        'all_results': []
    }
    
    # Process each project folder separately
    for project_folder in project_folders:
        project_name = os.path.basename(project_folder)
        
        if verbose:
            print(f"🏗️ Processing project: {project_name}")
            print("-" * 40)
        
        try:
            # Process this project only
            project_results = run_complete_pipeline_v4(
                data_dir=project_folder,
                questions=questions,
                llm_interface=llm_interface,
                output_folder=project_folder,  # Save results in project folder
                verbose=False  # Reduce verbosity for individual projects
            )
            
            if project_results:
                all_project_results[project_name] = project_results
                overall_stats['successful_projects'] += 1
                overall_stats['total_questions'] += project_results['metrics']['total_questions']
                overall_stats['total_answers'] += project_results['metrics']['successful_answers']
                overall_stats['all_results'].extend(project_results['results'])
                
                if verbose:
                    metrics = project_results['metrics']
                    print(f"   ✅ {metrics['success_rate']:.1f}% success ({metrics['successful_answers']}/{metrics['total_questions']})")
                    print(f"   📁 Results saved to: {project_results['output_path']}")
            else:
                if verbose:
                    print(f"   ❌ No results for {project_name}")
                    
        except Exception as e:
            if verbose:
                print(f"   ❌ Error processing {project_name}: {e}")
        
        if verbose:
            print()
    
    # Calculate overall statistics
    overall_success_rate = (overall_stats['total_answers'] / overall_stats['total_questions'] * 100) if overall_stats['total_questions'] > 0 else 0
    
    if verbose:
        print("=" * 60)
        print("📊 OVERALL SUMMARY")
        print("=" * 60)
        print(f"🏗️ Projects processed: {overall_stats['successful_projects']}/{overall_stats['total_projects']}")
        print(f"🎯 Overall success rate: {overall_success_rate:.1f}%")
        print(f"📊 Total answers found: {overall_stats['total_answers']}/{overall_stats['total_questions']}")
        print(f"💾 Results saved in respective project folders")
    
    return {
        'project_results': all_project_results,
        'overall_stats': overall_stats,
        'overall_success_rate': overall_success_rate
    }
