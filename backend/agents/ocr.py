# agents/ocr.py

import sys
import json
import gc
import logging
from typing import Any, Dict, Optional
from pathlib import Path

sys.path.append('..')
from .base import Talk2DrawingsBaseAgent

logger = logging.getLogger(__name__)


class OCRAgent(Talk2DrawingsBaseAgent):

    def __init__(self, config: Dict[str, Any] = None, blackboard=None):
        super().__init__("OCR_Agent", blackboard=blackboard)
        self.config = config or {}
        self.save_ocr_json = self.config.get('save_ocr_json', True)

        agentic_cfg = self.config.get('agentic', {})
        self.quality_threshold = agentic_cfg.get('ocr_quality_threshold', 0.7)
        self.max_retries = agentic_cfg.get('max_ocr_retries', 2)

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

    # ── Agentic: Document Assessment ────────────────────────────────────

    def assess_document(self, pdf_path: str) -> Dict[str, Any]:
        """Analyze document characteristics to inform OCR strategy.

        Uses PyMuPDF to quickly scan the PDF without full OCR.
        Returns assessment dict with type, DPI, page count, etc.
        """
        try:
            import fitz  # PyMuPDF
        except ImportError:
            return {'type': 'unknown', 'page_count': 0, 'has_tables': False,
                    'has_images': False, 'avg_text_length': 0, 'dpi': 0}

        doc = fitz.open(pdf_path)
        page_count = len(doc)
        total_text_len = 0
        has_images = False
        has_tables = False
        estimated_dpi = 300  # default assumption
        digital_pages = 0
        scanned_pages = 0

        for page_idx in range(min(page_count, 5)):  # sample first 5 pages
            page = doc[page_idx]
            text = page.get_text()
            total_text_len += len(text)

            # Check for embedded images (scanned pages have large images)
            images = page.get_images(full=True)
            if images:
                has_images = True
                # Estimate DPI from largest image
                for img in images:
                    xref = img[0]
                    try:
                        base_image = doc.extract_image(xref)
                        if base_image:
                            img_width = base_image.get('width', 0)
                            page_width_pts = page.rect.width
                            if page_width_pts > 0 and img_width > 0:
                                dpi = int(img_width / (page_width_pts / 72))
                                estimated_dpi = min(estimated_dpi, dpi)
                    except Exception:
                        pass

            # Classify page as digital or scanned
            word_count = len(text.split())
            if word_count > 50:
                digital_pages += 1
            elif images:
                scanned_pages += 1

            # Simple table detection: look for grid-like text patterns
            if '\t' in text or text.count('|') > 5:
                has_tables = True

        doc.close()

        sampled = min(page_count, 5)
        avg_text_length = total_text_len / max(sampled, 1)

        if scanned_pages > digital_pages:
            doc_type = 'scanned'
        elif digital_pages > scanned_pages:
            doc_type = 'digital'
        else:
            doc_type = 'mixed'

        assessment = {
            'type': doc_type,
            'page_count': page_count,
            'has_tables': has_tables,
            'has_images': has_images,
            'avg_text_length': round(avg_text_length, 1),
            'dpi': estimated_dpi,
            'digital_pages': digital_pages,
            'scanned_pages': scanned_pages
        }

        self.log_decision(
            f"Document assessed as '{doc_type}' ({page_count} pages, DPI~{estimated_dpi})",
            f"digital={digital_pages}, scanned={scanned_pages}, tables={has_tables}",
            decision_type="document_assessment"
        )

        return assessment

    # ── Agentic: Strategy Selection ─────────────────────────────────────

    def decide_strategy(self, assessment: Dict[str, Any],
                        memory_suggestions: Optional[Dict] = None) -> Dict[str, Any]:
        """Choose OCR strategy based on document assessment and memory.

        Returns strategy dict with primary_engine, fallback, and processing flags.
        """
        # Memory override: if we've seen similar docs, use what worked
        if memory_suggestions and memory_suggestions.get('suggested_ocr_engine'):
            strategy = {
                'primary_engine': memory_suggestions['suggested_ocr_engine'],
                'fallback_engine': 'aws_textract',
                'use_ocr': True,
                'extract_tables': True,
                'extract_patterns': True,
                'enhance_images': False,
                'source': 'memory'
            }
            self.log_decision(
                f"Using memory-suggested engine: {strategy['primary_engine']}",
                f"Similar document processed successfully before",
                decision_type="ocr_engine_selected"
            )
            return strategy

        doc_type = assessment.get('type', 'unknown')
        has_tables = assessment.get('has_tables', False)
        dpi = assessment.get('dpi', 300)
        avg_text = assessment.get('avg_text_length', 0)

        # Decision tree
        if doc_type == 'digital' and avg_text > 200:
            strategy = {
                'primary_engine': 'aws_textract',
                'fallback_engine': 'azure',
                'use_ocr': False,  # PDF text extraction is sufficient
                'extract_tables': has_tables,
                'extract_patterns': True,
                'enhance_images': False,
                'source': 'assessment_digital'
            }
            reason = f"Digital PDF with rich text (avg {avg_text:.0f} chars/page)"

        elif doc_type == 'scanned' and dpi < 200:
            strategy = {
                'primary_engine': 'aws_textract',
                'fallback_engine': 'azure',
                'use_ocr': True,
                'extract_tables': True,
                'extract_patterns': True,
                'enhance_images': True,  # Low DPI needs enhancement
                'source': 'assessment_low_dpi_scan'
            }
            reason = f"Low-DPI scanned document ({dpi} DPI), enabling image enhancement"

        elif has_tables:
            strategy = {
                'primary_engine': 'aws_textract',
                'fallback_engine': 'azure',
                'use_ocr': True,
                'extract_tables': True,
                'extract_patterns': True,
                'enhance_images': False,
                'source': 'assessment_tables'
            }
            reason = "Document contains tables, using Textract for table extraction"

        else:
            # Default strategy
            strategy = {
                'primary_engine': 'aws_textract',
                'fallback_engine': 'azure',
                'use_ocr': True,
                'extract_tables': True,
                'extract_patterns': True,
                'enhance_images': False,
                'source': 'assessment_default'
            }
            reason = f"Standard {doc_type} document, using default strategy"

        self.log_decision(
            f"Selected OCR strategy: {strategy['primary_engine']} "
            f"(fallback: {strategy['fallback_engine']})",
            reason,
            decision_type="ocr_engine_selected"
        )

        return strategy

    # ── Agentic: Quality Check ──────────────────────────────────────────

    def check_quality(self, result: Dict[str, Any]) -> float:
        """Evaluate OCR output quality. Returns confidence 0.0-1.0."""
        if not result.get('success'):
            return 0.0

        page_results = result.get('page_results', [])
        if not page_results:
            return 0.0

        confidences = []
        for page in page_results:
            conf = page.get('confidence_avg', page.get('confidence', 0))
            if isinstance(conf, (int, float)):
                # Normalize to 0-1 range
                if conf > 1:
                    conf = conf / 100.0
                confidences.append(conf)

        if not confidences:
            return 0.5  # Unknown quality, don't trigger retry

        avg_confidence = sum(confidences) / len(confidences)
        return round(avg_confidence, 3)

    # ── Main Process (Agentic) ──────────────────────────────────────────

    async def process(self, pdf_path: str, context: Dict[str, Any] = None) -> Dict[str, Any]:
        if not self.processor:
            raise Exception("OCR processor not available")

        context = context or {}
        memory_suggestions = context.get('memory_suggestions')

        try:
            # Step 1: Assess document
            assessment = self.assess_document(str(pdf_path))

            # Step 2: Decide strategy
            strategy = self.decide_strategy(assessment, memory_suggestions)

            # Step 3: Execute OCR
            result = self._execute_ocr(str(pdf_path), strategy)
            ocr_result = self._build_result(pdf_path, result, strategy, assessment)

            # Step 4: Check quality and retry if needed
            quality = self.check_quality(ocr_result)
            ocr_result['quality_score'] = quality
            ocr_result['ocr_strategy'] = strategy
            ocr_result['assessment'] = assessment
            ocr_result['retries_used'] = 0

            if quality < self.quality_threshold and strategy.get('fallback_engine'):
                self.log_decision(
                    f"OCR quality {quality:.2f} below threshold {self.quality_threshold}",
                    f"Retrying with fallback engine: {strategy['fallback_engine']}",
                    decision_type="retry_triggered"
                )

                # Retry with fallback strategy
                fallback_strategy = strategy.copy()
                fallback_strategy['primary_engine'] = strategy['fallback_engine']
                fallback_strategy['enhance_images'] = True
                fallback_strategy['source'] = 'retry_fallback'

                retry_result = self._execute_ocr(str(pdf_path), fallback_strategy)
                retry_ocr = self._build_result(pdf_path, retry_result, fallback_strategy, assessment)
                retry_quality = self.check_quality(retry_ocr)

                if retry_quality > quality:
                    ocr_result = retry_ocr
                    ocr_result['quality_score'] = retry_quality
                    ocr_result['ocr_strategy'] = fallback_strategy
                    ocr_result['assessment'] = assessment
                    ocr_result['retries_used'] = 1
                    self.log_decision(
                        f"Retry improved quality: {quality:.2f} -> {retry_quality:.2f}",
                        f"Using fallback engine results",
                        decision_type="quality_threshold_met"
                    )

            # Save OCR JSON if configured
            if self.save_ocr_json:
                json_path = self._save_ocr_json(str(pdf_path), result)
                ocr_result['ocr_json_path'] = json_path

            return ocr_result

        except Exception as e:
            raise Exception(f"OCR processing failed: {e}")

    def _execute_ocr(self, pdf_path: str, strategy: Dict[str, Any]) -> Dict:
        """Execute OCR with the given strategy."""
        print(f"OCR Agent processing: {Path(pdf_path).name} "
              f"(engine: {strategy.get('primary_engine', 'default')})")

        result = self.processor.process_with_page_results(
            Path(pdf_path),
            use_ocr=strategy.get('use_ocr', True),
            extract_tables=strategy.get('extract_tables', True),
            extract_patterns=strategy.get('extract_patterns', True),
            enhance_images=strategy.get('enhance_images', False)
        )

        # Memory cleanup
        if hasattr(self.processor, 'pdf_document'):
            self.processor.pdf_document = None
        gc.collect()

        return result

    def _build_result(self, pdf_path: str, result: Dict,
                      strategy: Dict, assessment: Dict) -> Dict[str, Any]:
        """Build standardized OCR result dict."""
        return {
            'success': True,
            'agent': self.name,
            'document_info': result['document_info'],
            'page_results': result['page_level_results'],
            'filtered_pages': result['filtered_pages'],
            'processing_time': result['document_info']['processing_time']
        }

    def _save_ocr_json(self, pdf_path: str, result: Dict) -> str:
        filtered_result = {
            'document_info': result['document_info'],
            'filtered_pages_only': result['filtered_pages']['matching_pages']
        }
        pdf_path_obj = Path(pdf_path)
        json_path = pdf_path_obj.parent / f"{pdf_path_obj.stem}_ocr_result.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(filtered_result, f, indent=2, ensure_ascii=False, default=str)
        return str(json_path)
