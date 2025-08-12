import asyncio
import sys
import os
from typing import Dict, Any, List
from pathlib import Path

# Add parent directory to path to import existing modules
sys.path.append('..')
from .base_agent import Talk2DrawingsBaseAgent


class OCRAgent(Talk2DrawingsBaseAgent):
    """Agent responsible for OCR processing with hierarchical fallback"""

    def __init__(self, config: Dict[str, Any] = None):
        super().__init__("OCR_Agent")
        self.config = config or {}

        # Import your existing OCR processor
        try:
            from ocr_tools.utils.help import EnhancedPDFProcessor
            self.processor = EnhancedPDFProcessor()
            print(f"✅ {self.name}: EnhancedPDFProcessor loaded successfully")
        except ImportError as e:
            print(f"⚠️ {self.name}: Could not load EnhancedPDFProcessor: {e}")
            self.processor = None
            self.is_available = False

    def validate_input(self, input_data: Any) -> bool:
        """Validate PDF input"""
        if isinstance(input_data, (str, Path)):
            path = Path(input_data)
            return path.exists() and path.suffix.lower() == '.pdf'
        return False

    async def process(self, pdf_path: str, context: Dict[str, Any] = None) -> Dict[str, Any]:
        """Process PDF with OCR engines"""
        if not self.processor:
            raise Exception("OCR processor not available")

        try:
            print(f"🔍 OCR Agent processing: {Path(pdf_path).name}")

            # Use your existing enhanced processor
            result = self.processor.process_with_page_results(
                Path(pdf_path),
                use_ocr=True,
                extract_tables=True,
                extract_patterns=True,
                enhance_images=False
            )

            return {
                'success': True,
                'agent': self.name,
                'document_info': result['document_info'],
                'page_results': result['page_level_results'],
                'filtered_pages': result['filtered_pages'],
                'processing_time': result['document_info']['processing_time']
            }

        except Exception as e:
            raise Exception(f"OCR processing failed: {e}")