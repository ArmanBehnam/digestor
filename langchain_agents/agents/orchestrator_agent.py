import asyncio
import sys
from typing import Dict, Any, List
from pathlib import Path
import pandas as pd
from datetime import datetime
from .base_agent import Talk2DrawingsBaseAgent
from .ocr_agent import OCRAgent
from .qa_agent import EngineeringQAAgent
from .validation_agent import ValidationAgent
import json
sys.path.append('..')


class OrchestratorAgent(Talk2DrawingsBaseAgent):

    def __init__(self, config: Dict[str, Any] = None):
        super().__init__("Orchestrator_Agent")
        self.config = config or {}

        self.ocr_agent = OCRAgent(config)
        self.qa_agent = EngineeringQAAgent(config)

        print(f"{self.name}: Initialized with OCR and QA agents")

    def validate_input(self, input_data: Any) -> bool:
        return (isinstance(input_data, dict) and
                'pdf_path' in input_data)

    async def process(self, input_data: Dict[str, Any], context: Dict[str, Any] = None) -> Dict[str, Any]:
        try:
            pdf_path = input_data['pdf_path']
            config = input_data.get('config', {})

            print(f"Orchestrator starting workflow for: {Path(pdf_path).name}")

            print("Step 1: OCR Processing")
            ocr_result = await self.ocr_agent.safe_process(pdf_path, context)

            if not ocr_result['success']:
                return {
                    'success': False,
                    'agent': self.name,
                    'error': f"OCR failed: {ocr_result.get('error', 'Unknown error')}",
                    'step_failed': 'OCR'
                }

            print(f"OCR completed: {len(ocr_result['page_results'])} pages processed")

            print("Step 2: Engineering Q&A")
            qa_result = await self.qa_agent.safe_process(ocr_result, context)

            if not qa_result['success']:
                return {
                    'success': False,
                    'agent': self.name,
                    'error': f"QA failed: {qa_result.get('error', 'Unknown error')}",
                    'step_failed': 'QA'
                }

            print(f"QA completed: {qa_result.get('questions_processed', 0)} questions processed")

            print("Step 3: Generating final results")
            final_results = await self._generate_final_results(
                ocr_result, qa_result, pdf_path, config
            )

            print("Workflow completed successfully!")

            return {
                'success': True,
                'agent': self.name,
                'final_results': final_results,
                'processing_summary': {
                    'ocr_pages': len(ocr_result.get('page_results', [])),
                    'filtered_pages': len(ocr_result.get('filtered_pages', {}).get('matching_pages', [])),
                    'questions_answered': qa_result.get('questions_processed', 0),
                    'total_processing_time': ocr_result.get('processing_time', 0)
                }
            }

        except Exception as e:
            raise Exception(f"Orchestration failed: {e}")

    async def _generate_final_results(self, ocr_result: Dict, qa_result: Dict, pdf_path: str, config: Dict) -> Dict[str, Any]:
        try:
            from llm_tools.utils import apply_deflection_defaults

            questions = self.qa_agent.questions
            raw_answers = qa_result['qa_results']

            processed_answers = apply_deflection_defaults(raw_answers, questions)

        except ImportError:
            print("Could not import apply_deflection_defaults, using raw answers")
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

            results_data.append({
                'Question_Number': i,
                'Question': question,
                'Answer': answer,
                'Page': page,
                'Confidence': f"{confidence}%",
                'Source': source,
                'Deflection_Default': 'Applied' if source == 'deflection_defaults.csv' else ''})

        df = pd.DataFrame(results_data)

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        project_name = Path(pdf_path).stem

        output_dir = Path(pdf_path).parent
        csv_path = output_dir / f"pipeline_results_agents_{project_name}_{timestamp}.csv"
        json_path = output_dir / f"pipeline_results_agents_{project_name}_{timestamp}.json"

        df.to_csv(csv_path, index=False)

        json_results = {
            'document_info': ocr_result['document_info'],
            'processing_summary': {
                'questions_total': len(questions),
                'questions_answered': len([r for r in results_data if r['Answer'] != 'Not Found']),
                'defaults_applied': len([r for r in results_data if r['Deflection_Default'] == 'Applied']),
                'timestamp': timestamp
            },
            'results': results_data}

        import json
        with open(json_path, 'w') as f:
            json.dump(json_results, f, indent=2)

        print(f"Results saved:")
        print(f"   CSV: {csv_path}")
        print(f"   JSON: {json_path}")

        return {
            'csv_path': str(csv_path),
            'json_path': str(json_path),
            'results_dataframe': df,
            'summary': json_results['processing_summary']
        }

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