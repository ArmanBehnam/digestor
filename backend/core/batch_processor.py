# core/batch_processor.py

import asyncio
import argparse
import json
from pathlib import Path
from typing import Dict, List
import pandas as pd
from datetime import datetime
from core.workflow import Talk2DrawingsWorkflow
from agents.validation import ValidationAgent

current_dir = Path(__file__).parent.parent
import sys

sys.path.insert(0, str(current_dir))
sys.path.insert(0, str(current_dir / "llm"))
sys.path.insert(0, str(current_dir / "ocr"))
sys.path.insert(0, str(current_dir / "agentic"))

# Credentials are loaded from environment variables via config_loader.
# NEVER hardcode secrets here. See .env.example for required env vars.


def chunk_pages_by_tokens(merged_pages, max_tokens=30000):
    chunks = []
    current_chunk = []
    current_tokens = 0

    for page in merged_pages:
        page_text = page.get('extracted_text', '')
        page_tokens = len(page_text) // 3
        overhead = 2000

        total_tokens_needed = current_tokens + page_tokens + overhead

        if total_tokens_needed > max_tokens and current_chunk:
            chunks.append(current_chunk)
            current_chunk = [page]
            current_tokens = page_tokens
        else:
            current_chunk.append(page)
            current_tokens += page_tokens

    if current_chunk:
        chunks.append(current_chunk)

    return chunks

def estimate_tokens(text: str) -> int:
    return len(text) // 3


def validate_chunk_size(chunk, max_tokens=30000):
    total_text = ""
    for page in chunk:
        total_text += page.get('extracted_text', '')

    estimated_tokens = estimate_tokens(total_text) + 2000
    if estimated_tokens > max_tokens:
        print(f"WARNING: Chunk may exceed token limit: {estimated_tokens} > {max_tokens}")
        return False
    return True


async def process_directory_merged(directory_path, prompt_engineering=True, enable_validation=True):
    dir_path = Path(directory_path)
    pdf_files = list(dir_path.glob("*.pdf"))

    if not pdf_files:
        print(f"No PDF files found in: {directory_path}")
        return []

    print(f"Found {len(pdf_files)} PDF files for merged processing")
    for pdf in pdf_files:
        print(f"   • {pdf.name}")

    workflow = Talk2DrawingsWorkflow()

    validation_agent = ValidationAgent(workflow.config) if enable_validation else None
    if validation_agent and not validation_agent.is_available:
        print("ValidationAgent not available, skipping validation")
        validation_agent = None

    print("\nStep 1: OCR Processing All PDFs")

    all_json_data = []
    ocr_success = 0

    for i, pdf_path in enumerate(pdf_files, 1):
        print(f"OCR Processing {i}/{len(pdf_files)}: {pdf_path.name}")

        try:
            result = await workflow.orchestrator.ocr_agent.safe_process(str(pdf_path))

            if result['success']:
                all_json_data.append({
                    'source_pdf': pdf_path.name,
                    'pdf_path': str(pdf_path),
                    'ocr_data': result,
                    'page_count': len(result.get('page_results', [])),
                    'filtered_pages': result.get('filtered_pages', {})
                })
                ocr_success += 1
                print(f"   OCR Success: {len(result.get('page_results', []))} pages")
            else:
                print(f"   OCR Failed: {result.get('error', 'Unknown error')}")

        except Exception as e:
            print(f"   OCR Error: {pdf_path.name} - {e}")

    if not all_json_data:
        print("No successful OCR results to process")
        return []

    print(f"\nOCR Summary: {ocr_success}/{len(pdf_files)} PDFs processed")

    print("\nStep 2: Merging JSON Data")

    merged_data = merge_json_results(all_json_data)
    total_pages = sum(item['page_count'] for item in all_json_data)

    print("Merged Results:")
    print(f"   Total pages: {total_pages}")
    print(f"   Source PDFs: {len(all_json_data)}")
    print(f"   Filtered pages: {len(merged_data['filtered_pages']['matching_pages'])}")

    print("\nStep 3: LLM Processing on Merged Data")

    try:
        chunks = chunk_pages_by_tokens(merged_data['filtered_pages']['matching_pages'], max_tokens=30000)
        print(f"Processing {len(chunks)} chunks to stay under token limits")
        all_qa_results = {}
        successful_chunks = 0
        for i, chunk in enumerate(chunks):
            print(f"   Processing chunk {i + 1}/{len(chunks)} ({len(chunk)} pages)")
            if not validate_chunk_size(chunk, max_tokens=30000):
                print(f"   Skipping chunk {i + 1} - too large")
                continue
            chunk_data = {'filtered_pages': {'matching_pages': chunk}}
            try:
                chunk_result = await workflow.orchestrator.qa_agent.safe_process(chunk_data)
                if chunk_result['success']:
                    for qid, new_answer in chunk_result['qa_results'].items():
                        if qid not in all_qa_results:
                            all_qa_results[qid] = new_answer
                        else:
                            old_ans = all_qa_results[qid]
                            new_ans_text = new_answer.get('answer', '')
                            old_ans_text = old_ans.get('answer', '')
                            if old_ans_text == 'Not Found' and new_ans_text != 'Not Found':
                                all_qa_results[qid] = new_answer
                            elif new_ans_text != 'Not Found':
                                new_conf = new_answer.get('confidence', 0)
                                old_conf = old_ans.get('confidence', 0)
                                if new_conf > old_conf:
                                    all_qa_results[qid] = new_answer
                    successful_chunks += 1
                    print(f"   Chunk {i + 1} successful: {len(chunk_result['qa_results'])} answers")
                else:
                    print(f"   Chunk {i + 1} failed: {chunk_result.get('error', 'Unknown error')}")
            except Exception as e:
                print(f"   Chunk {i + 1} error: {e}")
                continue

        print(f"Processed {successful_chunks}/{len(chunks)} chunks successfully")

        qa_result = {'success': successful_chunks > 0, 'qa_results': all_qa_results,
                     'questions_processed': len(all_qa_results)}

        if qa_result['success']:
            print(f"LLM Success: {qa_result.get('questions_processed', 0)} questions answered")
        else:
            print("LLM Failed: No successful chunks")
    except Exception as e:
        print(f"LLM Processing Error: {e}")
        qa_result = {'success': False, 'error': str(e), 'qa_results': {}}

    print("\nStep 4: Generating Final Results")

    output_dir = Path("outputs")
    output_dir.mkdir(exist_ok=True)

    final_results = await generate_final_results_merged(
        workflow,
        merged_data,
        qa_result,
        str(output_dir),
        {'prompt_engineering': prompt_engineering},
        all_json_data
    )

    if validation_agent and final_results.get('results_dataframe') is not None:
        print("\nStep 5: Validating Results")
        try:
            validation_result = await validation_agent.safe_process({
                'results_dataframe': final_results['results_dataframe']
            })

            if validation_result['success']:
                validated_df = validation_result['validated_dataframe']

                val_csv_path = output_dir / f"validated_{Path(final_results['csv_path']).name}"
                validated_df.to_csv(val_csv_path, index=False)

                final_results['validated_csv_path'] = str(val_csv_path)
                final_results['validation_results'] = validation_result

                print("Validation complete:")
                print(f"   Total validated: {validation_result['total_validated']}")
                print(f"   Passed: {validation_result['passed']}")
                print(f"   Failed: {validation_result['failed']}")
                print(f"   Skipped: {validation_result['skipped']}")
                print(f"   CSV: {val_csv_path}")
            else:
                print(f"Validation failed: {validation_result.get('error', 'Unknown')}")

        except Exception as e:
            print(f"Validation error: {e}")

    return final_results


def merge_json_results(all_json_data: List[Dict]) -> Dict:
    merged_pages = []
    source_mapping = []
    global_page_id = 0

    for json_data in all_json_data:
        source_pdf = json_data['source_pdf']
        ocr_data = json_data['ocr_data']
        filtered_pages = ocr_data.get('filtered_pages', {}).get('matching_pages', [])

        for page in filtered_pages:
            original_page_number = page.get('page_number', 0)
            merged_page = page.copy()
            merged_page['source_pdf'] = source_pdf
            merged_page['global_page_id'] = global_page_id
            merged_pages.append(merged_page)

            source_mapping.append({
                'global_page_id': global_page_id,
                'source_pdf': source_pdf,
                'original_page': original_page_number
            })
            global_page_id += 1

    merged_data = {
        'filtered_pages': {
            'matching_pages': merged_pages,
            'total_matching_pages': len(merged_pages)
        },
        'source_mapping': source_mapping,
        'document_info': {
            'merged_from': len(all_json_data),
            'total_pages': len(merged_pages),
            'source_files': [item['source_pdf'] for item in all_json_data]}}
    return merged_data


def get_pdf_ocr_confidence(source_pdf: str, all_ocr_results: List[Dict]) -> int:
    for ocr_result in all_ocr_results:
        if ocr_result.get('source_pdf') == source_pdf:
            conf = ocr_result.get('ocr_data', {}).get('document_info', {}).get('confidence', 0)
            return int(conf * 100) if conf <= 1 else int(conf)
    return 0


async def generate_final_results_merged(workflow, merged_data: Dict, qa_result: Dict, output_dir: str, config: Dict, all_ocr_results: List[Dict] = None):

    questions = workflow.orchestrator.qa_agent.questions
    raw_answers = qa_result['qa_results']

    if not isinstance(raw_answers, dict):
        print(f"WARNING: raw_answers is {type(raw_answers)}, initializing empty dict")
        raw_answers = {}

    processed_answers = raw_answers.copy()
    try:
        from llm.utils import apply_deflection_defaults, normalize_answers_and_units
        result = apply_deflection_defaults(raw_answers, questions)
        if isinstance(result, dict):
            processed_answers = result
        elif isinstance(result, (tuple, list)) and len(result) > 0:
            processed_answers = result[0] if isinstance(result[0], dict) else raw_answers
        elif isinstance(result, str):
            print("WARNING: apply_deflection_defaults returned string, using raw_answers")
            processed_answers = raw_answers
        else:
            print(f"WARNING: apply_deflection_defaults returned {type(result)}, using raw_answers")
            processed_answers = raw_answers
        result = normalize_answers_and_units(processed_answers, questions)
        if isinstance(result, dict):
            processed_answers = result
        elif isinstance(result, (tuple, list)) and len(result) > 0:
            processed_answers = result[0] if isinstance(result[0], dict) else processed_answers
        elif isinstance(result, str):
            print("WARNING: normalize_answers_and_units returned string, using previous")
        else:
            print(f"WARNING: normalize_answers_and_units returned {type(result)}, using previous")

    except ImportError:
        pass
    except Exception as e:
        print(f"WARNING: Error in utility functions: {e}, using raw_answers")
        processed_answers = raw_answers

    if not isinstance(processed_answers, dict):
        print(f"WARNING: Final processed_answers is {type(processed_answers)}, using raw_answers")
        processed_answers = raw_answers

    results_data = []
    for i, question in enumerate(questions, 1):
        qid = f"Q{i}"
        answer_data = processed_answers.get(qid, {})
        raw_data = raw_answers.get(qid, {})

        if isinstance(answer_data, dict):
            answer = answer_data.get('answer', 'Not Found')
            page = answer_data.get('page', 'N/A')
            confidence = answer_data.get('confidence', 0)
            source = answer_data.get('source', 'Unknown')
            normalized = answer_data.get('normalized_answer', answer)
            unit = answer_data.get('unit', '')
        else:
            answer = str(answer_data) if answer_data else 'Not Found'
            page = 'N/A'
            confidence = 0
            source = 'Unknown'
            normalized = answer
            unit = ''

        section = raw_data.get('section', 'N/A') if isinstance(raw_data, dict) else 'N/A'
        coordinates = raw_data.get('coordinates_display', 'N/A') if isinstance(raw_data, dict) else 'N/A'
        source_pdf = identify_source_pdf(page, merged_data, section)

        llm_source_pdf = raw_data.get('source_pdf', source_pdf) if isinstance(raw_data, dict) else source_pdf
        source_pages = [p for p in merged_data.get('filtered_pages', {}).get('matching_pages', [])
                        if p.get('source_pdf') == llm_source_pdf]

        actual_page = 'N/A'
        ocr_conf = 0
        if source_pages:
            first_page = source_pages[0]
            actual_page = first_page.get('page_number', 'N/A')
            raw_conf = first_page.get('confidence_avg', 0)
            ocr_conf = int(raw_conf * 100) if raw_conf <= 1 else int(raw_conf)

        ocr_conf = get_pdf_ocr_confidence(source_pdf, all_ocr_results or [])
        results_data.append({'Question_Number': i,
            'Question': question,
            'Main_Answer': answer,
            'Normalized_Answer': normalized,
            'Unit': unit,
            'Page': actual_page,
            'Section': section,
            'Source_PDF': source_pdf,
            'Coordinates': coordinates,
            'OCR_Confidence': ocr_conf if ocr_conf > 0 else (95 if source == 'deflection_defaults.csv' else 0),
            'OCR_Source': answer_data.get('ocr_engine', 'aws_textract') if isinstance(answer_data,
                                                                                      dict) else 'aws_textract',
            'Deflection_Default': 'Applied' if source == 'deflection_defaults.csv' else '',
            'Processing_Mode': 'Merged_JSON'})

    df = pd.DataFrame(results_data)
    config_metadata = config.get('metadata', {})
    df['Upload_Timestamp'] = config_metadata.get('timestamp', 'N/A')
    df['Source_Files'] = '; '.join(config_metadata.get('source_files', []))
    df['Project_Version'] = config_metadata.get('project_version', 'N/A')

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    source_pdfs = merged_data.get('document_info', {}).get('source_files', [])
    project_name = f"merged_{len(source_pdfs)}_pdfs"

    output_dir = Path(output_dir)
    csv_path = output_dir / f"pipeline_results_merged_{project_name}_{timestamp}.csv"
    json_path = output_dir / f"pipeline_results_merged_{project_name}_{timestamp}.json"

    json_results = {'processing_mode': 'merged_json', 'source_pdfs': source_pdfs,
        'merged_pages': merged_data.get('filtered_pages', {}).get('total_matching_pages', 0),
        'processing_summary': {'questions_total': len(questions),
            'questions_answered': len([r for r in results_data if r['Main_Answer'] != 'Not Found']),
            'defaults_applied': len([r for r in results_data if r['Deflection_Default'] == 'Applied']),
            'timestamp': timestamp, 'source_files': source_pdfs}, 'results': results_data}

    with open(json_path, 'w') as f:
        json.dump(json_results, f, indent=2)
    csv_path_str = None
    try:
        df.to_csv(csv_path, index=False, encoding='utf-8')
        csv_path_str = str(csv_path)
    except Exception as e:
        print(f"FATAL WARNING: Failed to write final CSV file to {csv_path}. Reason: {e}")

    print("Merged results saved:")
    print(f"   CSV: {csv_path}")
    print(f"   JSON: {json_path}")
    return {'csv_path': str(csv_path), 'json_path': str(json_path),
        'results_dataframe': df, 'summary': json_results['processing_summary']}


def identify_source_pdf(page_ref: str, merged_data: Dict, section: str = None) -> str:
    try:
        if section and section != 'N/A':
            source_mapping = merged_data.get('source_mapping', [])
            for mapping in source_mapping:
                page_data = next((p for p in merged_data.get('filtered_pages', {}).get('matching_pages', [])
                                  if p.get('global_page_id') == mapping.get('global_page_id')
                                  and p.get('section') == section), None)
                if page_data:
                    return mapping.get('source_pdf', 'Unknown')

        if page_ref and str(page_ref) != '0' and page_ref != 'Default':
            source_mapping = merged_data.get('source_mapping', [])
            page_num = int(page_ref) if str(page_ref).isdigit() else None
            if page_num:
                for mapping in source_mapping:
                    if mapping.get('original_page') == page_num:
                        return mapping.get('source_pdf', 'Unknown')

        source_files = merged_data.get('document_info', {}).get('source_files', [])
        return source_files[0] if source_files else 'Unknown'
    except Exception:
        return 'Unknown'

async def main():
    parser = argparse.ArgumentParser(description="Merged JSON batch processing with validation")
    parser.add_argument("--directory", required=True, help="Directory containing PDF files")
    parser.add_argument("--prompt-engineering", action="store_true", default=True)
    parser.add_argument("--enable-validation", action="store_true", default=True, help="Enable validation of results")
    parser.add_argument("--processing-mode", choices=['ocr_only', 'llm_only', 'full'], default='full',
                        help="Processing mode")
    parser.add_argument("--ocr-data-dir", help="Directory with existing OCR JSON files (for llm_only mode)")
    args = parser.parse_args()
    result = await process_directory_merged(args.directory, args.prompt_engineering, args.enable_validation)

    if result:
        print(f"Processed {len(result['source_pdfs'])} PDFs in merged mode")
        print(f"Total pages: {result['total_pages']}")
        print(f"Questions answered: {result['questions_answered']}")

        if 'validation_results' in result and result['validation_results']:
            validation = result['validation_results']
            if validation['success']:
                print(f"   Total validated: {validation['total_validated']}")
                print(f"   Passed: {validation['passed']}")
                print(f"   Failed: {validation['failed']}")
                print(f"   Skipped: {validation['skipped']}")

                validation_summary = validation['validation_summary']
                for status, count in validation_summary.items():
                    print(f"   {status}: {count}")
            else:
                print(f"\nValidation failed: {validation.get('error', 'Unknown error')}")
        else:
            print("\nValidation: Not performed")
    else:
        print("\nMerged processing failed")


if __name__ == "__main__":
    asyncio.run(main())
