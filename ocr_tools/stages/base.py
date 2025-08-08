import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, List
from ocr_tools.core.interfaces import ProcessingStage

logger = logging.getLogger(__name__)


class BaseProcessingStage(ProcessingStage):
    """Base class for all processing stages."""
    
    def __init__(self, name: str, dependencies: List[str] = None, optional: bool = False):
        self._name = name
        self._dependencies = dependencies or []
        self._optional = optional
        self.logger = logging.getLogger(f"{__name__}.{name}")
    
    @property
    def name(self) -> str:
        return self._name
    
    @property
    def dependencies(self) -> List[str]:
        return self._dependencies
    
    @property
    def optional(self) -> bool:
        return self._optional
    
    def validate_input(self, data: Dict[str, Any]) -> bool:
        """Basic input validation - check for required keys."""
        required_keys = ['input_path', 'result', 'config']
        return all(key in data for key in required_keys)
    
    @abstractmethod
    def process(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Process data and return updated context."""
        pass
    
    def _log_stage_start(self, context: Dict[str, Any]) -> None:
        """Log stage start."""
        filename = context.get('input_path', 'unknown').name if hasattr(context.get('input_path'), 'name') else 'unknown'
        self.logger.debug(f"Starting {self.name} stage for {filename}")
    
    def _log_stage_complete(self, context: Dict[str, Any], **metrics) -> None:
        """Log stage completion with metrics."""
        filename = context.get('input_path', 'unknown').name if hasattr(context.get('input_path'), 'name') else 'unknown'
        metric_str = ', '.join(f"{k}={v}" for k, v in metrics.items())
        self.logger.debug(f"Completed {self.name} stage for {filename} ({metric_str})")



class PDFTextStage(BaseProcessingStage):

    def __init__(self, pdf_extractor):
        super().__init__("pdf_text", dependencies=[])
        self.pdf_extractor = pdf_extractor
    
    def process(self, context: Dict[str, Any]) -> Dict[str, Any]:
        self._log_stage_start(context)
        
        input_path = context['input_path']
        result = context['result']

        pdf_data = self.pdf_extractor.extract_text_and_metadata(input_path)

        result.extracted_text = pdf_data['text']
        result.total_pages = pdf_data['total_pages']
        result.metadata.update(pdf_data['metadata'])

        if 'tables' in pdf_data:
            result.tables.extend(pdf_data['tables'])

        context['pdf_data'] = pdf_data
        context['result'] = result
        
        self._log_stage_complete(context, 
                               pages=result.total_pages, 
                               text_length=len(result.extracted_text),
                               tables=len(pdf_data.get('tables', [])))
        
        return context


class OCRStage(BaseProcessingStage):

    def __init__(self, ocr_registry, image_processor):
        super().__init__("ocr", dependencies=["pdf_text"], optional=True)
        self.ocr_registry = ocr_registry
        self.image_processor = image_processor
    
    def validate_input(self, data: Dict[str, Any]) -> bool:
        base_valid = super().validate_input(data)
        use_ocr = data.get('use_ocr', True)
        return base_valid and use_ocr
    
    def process(self, context: Dict[str, Any]) -> Dict[str, Any]:
        self._log_stage_start(context)
        
        input_path = context['input_path']
        result = context['result']
        use_ocr = context.get('use_ocr', True)
        
        if not use_ocr:
            self.logger.debug("OCR disabled, skipping")
            return context

        images = self._extract_images_from_pdf(input_path, result.total_pages)

        all_elements = []
        for page_num, image in images.items():
            try:
                if context.get('enhance_images', True):
                    image = self.image_processor.enhance_image(image)

                elements = self.ocr_registry.extract_with_fallback(image, page_num)
                all_elements.extend(elements)
                
            except Exception as e:
                self.logger.warning(f"OCR failed for page {page_num}: {e}")
                continue

        result.elements.extend(all_elements)

        result.images = [
            {'page_number': page_num, 'format': 'array', 'dimensions': img.shape[:2]}
            for page_num, img in images.items()
        ]
        
        context['result'] = result
        context['images'] = images
        
        self._log_stage_complete(context, elements=len(all_elements))
        return context
    
    def _extract_images_from_pdf(self, pdf_path, total_pages):
        try:
            import fitz  # PyMuPDF
            import cv2
            import numpy as np
            
            images = {}
            doc = fitz.open(pdf_path)
            
            for page_num in range(total_pages):
                page = doc[page_num]
                mat = fitz.Matrix(2.0, 2.0)  # Scale factor
                pix = page.get_pixmap(matrix=mat)
                img_data = pix.tobytes("png")

                nparr = np.frombuffer(img_data, np.uint8)
                img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                
                images[page_num + 1] = img
            
            doc.close()
            return images
            
        except Exception as e:
            self.logger.error(f"Failed to extract images: {e}")
            return {}


class TableStage(BaseProcessingStage):

    def __init__(self, table_extractor, image_processor):
        super().__init__("table_extraction", dependencies=["pdf_text"], optional=True)
        self.table_extractor = table_extractor
        self.image_processor = image_processor
    
    def process(self, context: Dict[str, Any]) -> Dict[str, Any]:
        self._log_stage_start(context)
        
        result = context['result']
        images = context.get('images', {})
        extract_tables = context.get('extract_tables', True)
        
        if not extract_tables:
            self.logger.debug("Table extraction disabled, skipping")
            return context

        table_elements = []
        for page_num, image in images.items():
            try:
                tables = self.image_processor.detect_tables(image, page_num)
                table_elements.extend(tables)
            except Exception as e:
                self.logger.warning(f"Table detection failed for page {page_num}: {e}")
                continue

        result.elements.extend(table_elements)
        
        context['result'] = result
        
        self._log_stage_complete(context, tables=len(table_elements))
        return context


class PatternStage(BaseProcessingStage):

    def __init__(self, pattern_processor):
        super().__init__("pattern_extraction", dependencies=["pdf_text"])
        self.pattern_processor = pattern_processor
    
    def process(self, context: Dict[str, Any]) -> Dict[str, Any]:
        self._log_stage_start(context)
        
        result = context['result']
        extract_patterns = context.get('extract_patterns', True)
        
        if not extract_patterns:
            self.logger.debug("Pattern extraction disabled, skipping")
            return context

        structured_data = self.pattern_processor.extract_patterns(result.extracted_text)

        result.structured_data.update(structured_data)
        
        context['result'] = result
        
        self._log_stage_complete(context, patterns=len(structured_data))
        return context


class SpatialStage(BaseProcessingStage):

    def __init__(self, spatial_analyzer):
        super().__init__("spatial_analysis", dependencies=["ocr"], optional=True)
        self.spatial_analyzer = spatial_analyzer
    
    def process(self, context: Dict[str, Any]) -> Dict[str, Any]:
        self._log_stage_start(context)
        
        result = context['result']

        spatial_data = self.spatial_analyzer.analyze_layout(result.elements, result.total_pages)

        result.spatial_analysis = spatial_data
        
        context['result'] = result
        
        self._log_stage_complete(context)
        return context


class ClassificationStage(BaseProcessingStage):

    def __init__(self, document_classifier):
        super().__init__("classification", dependencies=["pattern_extraction"])
        self.document_classifier = document_classifier
    
    def process(self, context: Dict[str, Any]) -> Dict[str, Any]:
        self._log_stage_start(context)
        
        result = context['result']

        doc_type = self.document_classifier.classify(result.extracted_text, result.elements)

        result.document_type = doc_type
        
        context['result'] = result
        
        self._log_stage_complete(context, document_type=doc_type.value)
        return context


class FinalizationStage(BaseProcessingStage):

    def __init__(self):
        super().__init__("finalization", dependencies=["pdf_text"])
    
    def process(self, context: Dict[str, Any]) -> Dict[str, Any]:
        self._log_stage_start(context)
        
        result = context['result']

        result.processing_metrics.update_from_elements(result.elements)

        result.extracted_text = result.extracted_text.strip()

        result.elements.sort(key=lambda e: (e.page_number, e.bbox.y if e.bbox else 0, e.bbox.x if e.bbox else 0))
        
        context['result'] = result
        
        self._log_stage_complete(context)
        return context