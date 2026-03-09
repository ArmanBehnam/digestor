import asyncio
import sys
import os
import json
from typing import Dict, Any, List
from pathlib import Path

sys.path.append('..')
from .base_agent import Talk2DrawingsBaseAgent


class OCRAgent(Talk2DrawingsBaseAgent):

    def __init__(self, config: Dict[str, Any] = None):
        super().__init__("OCR_Agent")
        self.config = config or {}
        self.save_ocr_json = config.get('save_ocr_json', True)

        try:
            from ocr.utils.help import Phase1PDFProcessor
            self.processor = Phase1PDFProcessor()
            print(f"{self.name}: Phase1PDFProcessor loaded successfully")
        except ImportError as e:
            print(f"{self.name}: Could not load Phase1PDFProcessor: {e}")
            self.processor = None
            self.is_available = False

    def validate_input(self, input_data: Any) -> bool:
        if isinstance(input_data, (str, Path)):
            path = Path(input_data)
            return path.exists() and path.suffix.lower() == '.pdf'
        return False

    async def process(self, pdf_path: str, context: Dict[str, Any] = None) -> Dict[str, Any]:
        if not self.processor:
            raise Exception("OCR processor not available")
        try:
            print(f"OCR Agent processing: {Path(pdf_path).name}")
            result = self.processor.process_with_page_results(Path(pdf_path), use_ocr=True, extract_tables=True, extract_patterns=True, enhance_images=False)
            ocr_result = {'success': True, 'agent': self.name, 'document_info': result['document_info'], 'page_results': result['page_level_results'],
                'filtered_pages': result['filtered_pages'], 'processing_time': result['document_info']['processing_time']}

            if self.save_ocr_json:
                json_path = self._save_ocr_json(pdf_path, result)
                ocr_result['ocr_json_path'] = json_path
                print(f"OCR JSON saved: {json_path}")
            return ocr_result

        except Exception as e:
            raise Exception(f"OCR processing failed: {e}")

    def _save_ocr_json(self, pdf_path: str, result: Dict) -> str:
        filtered_result = {'document_info': result['document_info'],
            'filtered_pages_only': result['filtered_pages']['matching_pages']}

        pdf_path_obj = Path(pdf_path)
        json_path = pdf_path_obj.parent / f"{pdf_path_obj.stem}_ocr_result.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(filtered_result, f, indent=2, ensure_ascii=False, default=str)
        return str(json_path)