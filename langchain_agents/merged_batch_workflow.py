import asyncio
import argparse
import os
import json
from pathlib import Path
from workflow import Talk2DrawingsWorkflow
from typing import Dict, Any
import pandas as pd
from datetime import datetime


def chunk_pages_by_tokens(merged_pages, max_tokens=25000):
    chunks = []
    current_chunk = []
    current_tokens = 0

    for page in merged_pages:
        page_tokens = len(page.get('extracted_text', '')) // 4

        if current_tokens + page_tokens > max_tokens and current_chunk:
            chunks.append(current_chunk)
            current_chunk = [page]
            current_tokens = page_tokens
        else:
            current_chunk.append(page)
            current_tokens += page_tokens

    if current_chunk:
        chunks.append(current_chunk)

    return chunks


async def process_directory_merged(directory_path, prompt_engineering=True):
    dir_path = Path(directory_path)
    pdf_files = list(dir_path.glob("*.pdf"))

    if not pdf_files:
        print(f"No PDF files found in: {directory_path}")
        return []

    print(f"Found {len(pdf_files)} PDF files for merged processing")
    for pdf in pdf_files:
        print(f"   • {pdf.name}")

    workflow = Talk2DrawingsWorkflow()
    
    print(f"\nStep 1: OCR Processing All PDFs")

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
    
    print(f"\nStep 2: Merging JSON Data")

    merged_data = merge_json_results(all_json_data)
    total_pages = sum(item['page_count'] for item in all_json_data)
    
    print(f"Merged Results:")
    print(f"   Total pages: {total_pages}")
    print(f"   Source PDFs: {len(all_json_data)}")
    print(f"   Filtered pages: {len(merged_data.get('matching_pages', []))}")
    
    print(f"\nStep 3: LLM Processing on Merged Data")

    try:
        chunks = chunk_pages_by_tokens(merged_data['filtered_pages']['matching_pages'])
        print(f"Processing {len(chunks)} chunks to stay under token limits")

        all_qa_results = {}
        for i, chunk in enumerate(chunks):
            print(f"   Processing chunk {i + 1}/{len(chunks)}")
            chunk_data = {'filtered_pages': {'matching_pages': chunk}}
            chunk_result = await workflow.orchestrator.qa_agent.safe_process(chunk_data)
            if chunk_result['success']:
                all_qa_results.update(chunk_result['qa_results'])

        qa_result = {
            'success': True,
            'qa_results': all_qa_results,
            'questions_processed': len(all_qa_results)
        }
        
        if qa_result['success']:
            print(f"LLM Success: {qa_result.get('questions_processed', 0)} questions answered")
            
            final_results = await workflow.orchestrator._generate_final_results(
                merged_data, qa_result, directory_path, {'prompt_engineering': prompt_engineering}
            )
            
            print(f"\nResults saved:")
            print(f"   CSV: {final_results['csv_path']}")
            print(f"   JSON: {final_results['json_path']}")
            
            return {
                'success': True,
                'merged_processing': True,
                'source_pdfs': [item['source_pdf'] for item in all_json_data],
                'total_pages': total_pages,
                'questions_answered': qa_result.get('questions_processed', 0),
                'final_results': final_results
            }
        else:
            print(f"LLM Failed: {qa_result.get('error', 'Unknown error')}")
            return []
            
    except Exception as e:
        print(f"LLM Error: {e}")
        return []


def merge_json_results(all_json_data):

    merged_pages = []
    source_mapping = []
    
    for pdf_data in all_json_data:
        pdf_name = pdf_data['source_pdf']
        ocr_data = pdf_data['ocr_data']
        
        filtered_pages = ocr_data.get('filtered_pages', {}).get('matching_pages', [])
        
        for page in filtered_pages:
            enhanced_page = page.copy()
            enhanced_page['source_pdf'] = pdf_name
            enhanced_page['source_pdf_path'] = pdf_data['pdf_path']
            enhanced_page['global_page_id'] = f"{pdf_name}_page_{page['page_number']}"
            
            merged_pages.append(enhanced_page)
            source_mapping.append({
                'global_page_id': enhanced_page['global_page_id'],
                'source_pdf': pdf_name,
                'original_page': page['page_number']
            })
    
    merged_data = {
        'filtered_pages': {
            'matching_pages': merged_pages,
            'total_matching_pages': len(merged_pages),
            'keywords_found': list(set(
                kw for pdf_data in all_json_data 
                for kw in pdf_data['ocr_data'].get('filtered_pages', {}).get('keywords_found', [])
            )),
            'source_pdfs': [item['source_pdf'] for item in all_json_data],
            'merged_processing': True
        },
        'source_mapping': source_mapping,
        'document_info': {
            'merged_from': len(all_json_data),
            'total_pages': len(merged_pages),
            'source_files': [item['source_pdf'] for item in all_json_data]
        }
    }
    
    return merged_data


async def main():
    parser = argparse.ArgumentParser(description="Merged JSON batch processing")
    parser.add_argument("--directory", required=True, help="Directory containing PDF files")
    parser.add_argument("--prompt-engineering", action="store_true", default=True)

    args = parser.parse_args()

    result = await process_directory_merged(args.directory, args.prompt_engineering)
    
    if result:
        print(f"\nMerged Processing Complete!")
        print(f"Processed {len(result['source_pdfs'])} PDFs in merged mode")
        print(f"Total pages: {result['total_pages']}")
        print(f"Questions answered: {result['questions_answered']}")
    else:
        print(f"\nMerged processing failed")

    async def _generate_final_results_merged(self, merged_data: Dict, qa_result: Dict, output_dir: str, config: Dict) -> Dict[str, Any]:

        try:
            from llm_tools.utils import apply_deflection_defaults
            questions = self.qa_agent.questions
            raw_answers = qa_result['qa_results']
            processed_answers = apply_deflection_defaults(raw_answers, questions)
        except ImportError:
            processed_answers = qa_result['qa_results']
            questions = self.qa_agent.questions

        results_data = []
        for i, question in enumerate(questions, 1):
            qid = f"Q{i}"
            answer_data = processed_answers.get(qid, {})

            if isinstance(answer_data, dict):
                answer = answer_data.get('answer', 'Not Found')
                page = answer_data.get('page', 'N/A')
                confidence = answer_data.get('confidence', 0)
                source = answer_data.get('source', 'Unknown')
            else:
                answer = str(answer_data) if answer_data else 'Not Found'
                page = 'N/A'
                confidence = 0
                source = 'Legacy'

            source_pdf = self._identify_source_pdf(page, merged_data)

            results_data.append({
                'Question_Number': i,
                'Question': question,
                'Answer': answer,
                'Page': page,
                'Source_PDF': source_pdf,
                'Confidence': f"{confidence}%",
                'Source': source,
                'Deflection_Default': 'Applied' if source == 'deflection_defaults.csv' else '',
                'Processing_Mode': 'Merged_JSON'
            })

        df = pd.DataFrame(results_data)

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        source_pdfs = merged_data.get('document_info', {}).get('source_files', [])
        project_name = f"merged_{len(source_pdfs)}_pdfs"

        output_dir = Path(output_dir)
        csv_path = output_dir / f"pipeline_results_merged_{project_name}_{timestamp}.csv"
        json_path = output_dir / f"pipeline_results_merged_{project_name}_{timestamp}.json"

        df.to_csv(csv_path, index=False)

        json_results = {
            'processing_mode': 'merged_json',
            'source_pdfs': source_pdfs,
            'merged_pages': merged_data.get('filtered_pages', {}).get('total_matching_pages', 0),
            'processing_summary': {
                'questions_total': len(questions),
                'questions_answered': len([r for r in results_data if r['Answer'] != 'Not Found']),
                'defaults_applied': len([r for r in results_data if r['Deflection_Default'] == 'Applied']),
                'timestamp': timestamp,
                'source_files': source_pdfs
            },
            'results': results_data
        }

        with open(json_path, 'w') as f:
            json.dump(json_results, f, indent=2)

        print(f"Merged results saved:")
        print(f"   CSV: {csv_path}")
        print(f"   JSON: {json_path}")

        return {
            'csv_path': str(csv_path),
            'json_path': str(json_path),
            'results_dataframe': df,
            'summary': json_results['processing_summary']
        }

    def _identify_source_pdf(self, page_ref: str, merged_data: Dict) -> str:
        try:
            source_mapping = merged_data.get('source_mapping', [])
            for mapping in source_mapping:
                if str(page_ref) in mapping.get('global_page_id', ''):
                    return mapping.get('source_pdf', 'Unknown')

            source_files = merged_data.get('document_info', {}).get('source_files', [])
            return source_files[0] if source_files else 'Unknown'
        except:
            return 'Unknown'



if __name__ == "__main__":
    asyncio.run(main())



