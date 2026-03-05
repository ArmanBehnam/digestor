import time
import logging
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path
import numpy as np
from ocr.utils.text_utils import TextProcessor

from ocr.core.interfaces import OCREngine
from ocr.core.models import ExtractedElement, BoundingBox, ElementType
from ocr.core.exceptions import OCRError, OCREngineNotAvailableError, OCRExtractionError, OCRConfigurationError, TimeoutError
from ocr.config.settings import get_config

logger = logging.getLogger(__name__)


class BaseOCREngine(OCREngine):

    def __init__(self, name: str, priority: int = 50):
        self._name = name
        self._priority = priority
        self.config = get_config()
        self._is_configured = False
        self._last_error: Optional[Exception] = None

    @property
    def name(self) -> str:
        return self._name

    @property
    def priority(self) -> int:
        return self._priority

    def get_confidence_threshold(self) -> float:
        return self.config.get('ocr.confidence_threshold', 0.5)

    def get_timeout(self) -> int:
        return self.config.get('ocr.timeout_seconds', 30)

    def get_max_retries(self) -> int:
        return self.config.get('ocr.max_retries', 3)

    def extract_text(self, image: np.ndarray, page_num: int, **kwargs) -> List[ExtractedElement]:
        if not self.is_available():
            raise OCREngineNotAvailableError(self.name, "Engine not available or configured")

        max_retries = self.get_max_retries()
        timeout = self.get_timeout()

        for attempt in range(max_retries + 1):
            try:
                logger.debug(f"OCR attempt {attempt + 1}/{max_retries + 1} with {self.name}")

                start_time = time.time()
                elements = self._extract_text_impl(image, page_num, **kwargs)
                elapsed_time = time.time() - start_time

                if elapsed_time > timeout:
                    raise TimeoutError(f"OCR extraction with {self.name}", timeout)

                threshold = self.get_confidence_threshold()
                filtered_elements = [e for e in elements if e.confidence >= threshold]

                logger.info(f"OCR {self.name} extracted {len(filtered_elements)} elements (page {page_num})")
                return filtered_elements

            except Exception as e:
                self._last_error = e
                logger.warning(f"OCR attempt {attempt + 1} failed with {self.name}: {e}")

                if attempt == max_retries:
                    raise OCRExtractionError(self.name, page_num, str(e))

                # Brief wait before retry
                time.sleep(0.5 * (attempt + 1))

        return []

    @abstractmethod
    def _extract_text_impl(self, image: np.ndarray, page_num: int, **kwargs) -> List[ExtractedElement]:
        pass

    @abstractmethod
    def _check_availability(self) -> Tuple[bool, str]:
        pass

    def is_available(self) -> bool:
        try:
            available, reason = self._check_availability()
            if not available:
                logger.debug(f"OCR engine {self.name} not available: {reason}")
            return available
        except Exception as e:
            logger.error(f"Error checking availability for {self.name}: {e}")
            return False

    def get_last_error(self) -> Optional[Exception]:
        return self._last_error

    def validate_image(self, image: np.ndarray) -> bool:
        if image is None or image.size == 0:
            return False

        if len(image.shape) not in [2, 3]:
            return False

        height, width = image.shape[:2]
        if height < 10 or width < 10:
            return False

        max_pixels = 50_000_000  # 50MP
        if height * width > max_pixels:
            return False

        return True

    def preprocess_image(self, image: np.ndarray) -> np.ndarray:
        if not self.validate_image(image):
            raise ValueError("Invalid image for OCR processing")

        if len(image.shape) == 3:
            import cv2
            image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

        return image

    def create_element(self, text: str, bbox_data: Dict[str, Any], page_num: int,
                       confidence: float, metadata: Dict[str, Any] = None) -> ExtractedElement:
        bbox = None
        if bbox_data:
            bbox = BoundingBox(
                x=float(bbox_data.get('x', 0)),
                y=float(bbox_data.get('y', 0)),
                width=float(bbox_data.get('width', 0)),
                height=float(bbox_data.get('height', 0)),
                confidence=confidence
            )

        element_metadata = {'ocr_engine': self.name}
        if metadata:
            element_metadata.update(metadata)

        return ExtractedElement(
            text=text.strip(),
            element_type=ElementType.TEXT,
            page_number=page_num,
            confidence=confidence,
            bbox=bbox,
            metadata=element_metadata
        )


class OCREngineRegistry:

    def __init__(self):
        self._engines: Dict[str, BaseOCREngine] = {}
        self._preferred_order: List[str] = []

    def register(self, engine: BaseOCREngine) -> None:
        self._engines[engine.name] = engine
        logger.info(f"Registered OCR engine: {engine.name}")

        self._update_preferred_order()

    def unregister(self, engine_name: str) -> bool:
        if engine_name in self._engines:
            del self._engines[engine_name]
            self._update_preferred_order()
            logger.info(f"Unregistered OCR engine: {engine_name}")
            return True
        return False

    def _update_preferred_order(self) -> None:
        self._preferred_order = sorted(
            self._engines.keys(),
            key=lambda name: self._engines[name].priority
        )

    def get_engine(self, name: str) -> Optional[BaseOCREngine]:
        return self._engines.get(name)

    def get_available_engines(self) -> List[BaseOCREngine]:
        available = []
        for engine_name in self._preferred_order:
            engine = self._engines[engine_name]
            if engine.is_available():
                available.append(engine)
        return available

    def get_best_engine(self) -> Optional[BaseOCREngine]:
        config = get_config()
        preferred = config.get('ocr.preferred_engine')

        if preferred and preferred in self._engines:
            engine = self._engines[preferred]
            if engine.is_available():
                return engine

        available = self.get_available_engines()
        return available[0] if available else None

    def extract_with_fallback(self, image: np.ndarray, page_num: int, **kwargs) -> List[ExtractedElement]:
        available_engines = self.get_available_engines()

        if not available_engines:
            raise OCREngineNotAvailableError("No engines", "No OCR engines are available")

        last_error = None

        for engine in available_engines:
            try:
                logger.debug(f"Trying OCR engine: {engine.name}")
                elements = engine.extract_text(image, page_num, **kwargs)

                if elements:
                    logger.info(f"Successfully extracted {len(elements)} elements with {engine.name}")
                    return elements

                logger.debug(f"No elements extracted with {engine.name}, trying next engine")

            except Exception as e:
                last_error = e
                logger.warning(f"OCR engine {engine.name} failed: {e}")
                continue

        error_msg = f"All OCR engines failed. Last error: {last_error}"
        raise OCRExtractionError("all_engines", page_num, error_msg)

    def get_engine_info(self) -> Dict[str, Dict[str, Any]]:
        info = {}
        for name, engine in self._engines.items():
            info[name] = {
                'name': engine.name,
                'priority': engine.priority,
                'available': engine.is_available(),
                'confidence_threshold': engine.get_confidence_threshold(),
                'timeout': engine.get_timeout(),
                'last_error': str(engine.get_last_error()) if engine.get_last_error() else None
            }
        return info

    def validate_configuration(self) -> Dict[str, List[str]]:
        issues = {}

        for name, engine in self._engines.items():
            engine_issues = []

            try:
                available, reason = engine._check_availability()
                if not available:
                    engine_issues.append(f"Not available: {reason}")
            except Exception as e:
                engine_issues.append(f"Configuration error: {e}")

            if engine_issues:
                issues[name] = engine_issues

        return issues


class OCRResultProcessor:

    @staticmethod
    def merge_elements(elements: List[ExtractedElement],
                       distance_threshold: float = 20.0) -> List[ExtractedElement]:
        if not elements:
            return elements

        sorted_elements = sorted(elements, key=lambda e: (e.bbox.y if e.bbox else 0, e.bbox.x if e.bbox else 0))

        merged = []
        current_group = [sorted_elements[0]]

        for element in sorted_elements[1:]:
            if not element.bbox or not current_group[-1].bbox:
                merged.append(element)
                current_group = [element]
                continue

            last_element = current_group[-1]
            distance = OCRResultProcessor._calculate_distance(last_element.bbox, element.bbox)

            if distance <= distance_threshold:
                current_group.append(element)
            else:
                if len(current_group) > 1:
                    merged_element = OCRResultProcessor._merge_element_group(current_group)
                    merged.append(merged_element)
                else:
                    merged.append(current_group[0])
                current_group = [element]

        if len(current_group) > 1:
            merged_element = OCRResultProcessor._merge_element_group(current_group)
            merged.append(merged_element)
        else:
            merged.append(current_group[0])

        return merged

    @staticmethod
    def _calculate_distance(bbox1: BoundingBox, bbox2: BoundingBox) -> float:
        center1 = bbox1.center()
        center2 = bbox2.center()
        return ((center1[0] - center2[0]) ** 2 + (center1[1] - center2[1]) ** 2) ** 0.5

    @staticmethod
    def _merge_element_group(elements: List[ExtractedElement]) -> ExtractedElement:

        text_parts = [e.text for e in elements if e.text.strip()]
        merged_text = " ".join(text_parts)

        bboxes = [e.bbox for e in elements if e.bbox]
        if bboxes:
            min_x = min(bbox.x for bbox in bboxes)
            min_y = min(bbox.y for bbox in bboxes)
            max_x = max(bbox.x + bbox.width for bbox in bboxes)
            max_y = max(bbox.y + bbox.height for bbox in bboxes)

            merged_bbox = BoundingBox(
                x=min_x,
                y=min_y,
                width=max_x - min_x,
                height=max_y - min_y,
                confidence=sum(bbox.confidence for bbox in bboxes) / len(bboxes)
            )
        else:
            merged_bbox = None

        first_element = elements[0]

        return ExtractedElement(
            text=merged_text,
            element_type=first_element.element_type,
            page_number=first_element.page_number,
            confidence=sum(e.confidence for e in elements) / len(elements),
            bbox=merged_bbox,
            metadata={
                'merged_from': len(elements),
                'ocr_engines': list(set(e.metadata.get('ocr_engine', 'unknown') for e in elements))
            }
        )

    @staticmethod
    def filter_low_quality(elements: List[ExtractedElement],
                           min_confidence: float = 0.3,
                           min_text_length: int = 2) -> List[ExtractedElement]:
        filtered = []

        for element in elements:
            if element.confidence < min_confidence:
                continue

            if len(element.text.strip()) < min_text_length:
                continue

            if element.text.strip() in ['|', '-', '_', '.', ':', ';', '!', '?']:
                continue

            text = element.text.strip()
            alpha_count = sum(1 for c in text if c.isalnum())
            if len(text) > 0 and alpha_count / len(text) < 0.3:
                continue

            filtered.append(element)

        return TextProcessor.filter_low_quality_elements(
            elements, min_confidence, min_text_length
        )

    @staticmethod
    def sort_reading_order(elements: List[ExtractedElement]) -> List[ExtractedElement]:
        if not elements:
            return elements

        rows = OCRResultProcessor._group_by_rows(elements)

        sorted_elements = []
        for row in rows:
            row_sorted = sorted(row, key=lambda e: e.bbox.x if e.bbox else 0)
            sorted_elements.extend(row_sorted)

        return sorted_elements

    @staticmethod
    def _group_by_rows(elements: List[ExtractedElement], tolerance: float = 10.0) -> List[List[ExtractedElement]]:
        if not elements:
            return []

        sorted_elements = sorted(elements, key=lambda e: e.bbox.y if e.bbox else 0)

        rows = []
        current_row = [sorted_elements[0]]
        current_y = sorted_elements[0].bbox.y if sorted_elements[0].bbox else 0

        for element in sorted_elements[1:]:
            element_y = element.bbox.y if element.bbox else 0

            if abs(element_y - current_y) <= tolerance:
                current_row.append(element)
            else:
                rows.append(current_row)
                current_row = [element]
                current_y = element_y

        if current_row:
            rows.append(current_row)

        return rows


_ocr_registry: Optional[OCREngineRegistry] = None


def get_ocr_registry() -> OCREngineRegistry:
    global _ocr_registry
    if _ocr_registry is None:
        _ocr_registry = OCREngineRegistry()
    return _ocr_registry


def reset_ocr_registry() -> None:
    global _ocr_registry
    _ocr_registry = None