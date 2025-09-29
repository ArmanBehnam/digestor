import logging
from typing import List, Dict, Any, Tuple, Optional
import numpy as np

from ocr.ocr_engine.base import BaseOCREngine
from ocr.core.models import ExtractedElement
from ocr.core.exceptions import OCRExtractionError, DependencyError

logger = logging.getLogger(__name__)


class OpenCVEngine(BaseOCREngine):

    def __init__(self):
        super().__init__("opencv_fallback", priority=90)  # Low priority - fallback only
        self._cv2 = None
        self._initialize_opencv()

    def _initialize_opencv(self) -> None:
        try:
            import cv2
            self._cv2 = cv2
            self._is_configured = True
            logger.info("OpenCV OCR fallback initialized successfully")
        except ImportError:
            logger.error("OpenCV library not found. Install with: pip install opencv-python")
            raise DependencyError("opencv-python", "pip install opencv-python")

    def _check_availability(self) -> Tuple[bool, str]:
        if not self._is_configured or not self._cv2:
            return False, "OpenCV not initialized"

        try:
            test_image = np.zeros((100, 100), dtype=np.uint8)
            self._cv2.findContours(test_image, self._cv2.RETR_EXTERNAL, self._cv2.CHAIN_APPROX_SIMPLE)
            return True, "OpenCV available"
        except Exception as e:
            return False, f"OpenCV not working: {e}"

    def _extract_text_impl(self, image: np.ndarray, page_num: int, **kwargs) -> List[ExtractedElement]:
        logger.debug("Using OpenCV fallback - detecting text regions only")

        elements = []

        mser_elements = self._detect_with_mser(image, page_num)
        elements.extend(mser_elements)

        # Contour-based detection
        contour_elements = self._detect_with_contours(image, page_num)
        elements.extend(contour_elements)

        # Edge-based detection
        edge_elements = self._detect_with_edges(image, page_num)
        elements.extend(edge_elements)

        elements = self._filter_and_deduplicate(elements)

        logger.debug(f"OpenCV detected {len(elements)} potential text regions")
        return elements

    def _detect_with_mser(self, image: np.ndarray, page_num: int) -> List[ExtractedElement]:
        elements = []

        try:
            gray = self._ensure_grayscale(image)

            mser = self._cv2.MSER_create()
            regions, _ = mser.detectRegions(gray)

            for region in regions:
                x, y, w, h = self._cv2.boundingRect(region)

                if w > 10 and h > 8 and w < image.shape[1] * 0.8 and h < image.shape[0] * 0.5:
                    aspect_ratio = w / h

                    if 0.1 < aspect_ratio < 20:
                        bbox_data = {'x': x, 'y': y, 'width': w, 'height': h}

                        element = self.create_element(
                            text="[DETECTED_TEXT_REGION]",
                            bbox_data=bbox_data,
                            page_num=page_num,
                            confidence=0.6,
                            metadata={
                                'detection_method': 'mser',
                                'aspect_ratio': aspect_ratio,
                                'region_area': w * h
                            }
                        )
                        elements.append(element)

        except Exception as e:
            logger.debug(f"MSER detection failed: {e}")

        return elements

    def _detect_with_contours(self, image: np.ndarray, page_num: int) -> List[ExtractedElement]:
        elements = []

        try:
            gray = self._ensure_grayscale(image)

            _, thresh = self._cv2.threshold(gray, 0, 255, self._cv2.THRESH_BINARY_INV + self._cv2.THRESH_OTSU)

            contours, _ = self._cv2.findContours(thresh, self._cv2.RETR_EXTERNAL, self._cv2.CHAIN_APPROX_SIMPLE)

            for contour in contours:
                x, y, w, h = self._cv2.boundingRect(contour)
                area = self._cv2.contourArea(contour)

                if (w > 15 and h > 8 and area > 100 and
                        w < image.shape[1] * 0.9 and h < image.shape[0] * 0.8):

                    aspect_ratio = w / h

                    hull = self._cv2.convexHull(contour)
                    hull_area = self._cv2.contourArea(hull)
                    solidity = area / hull_area if hull_area > 0 else 0

                    if 0.1 < aspect_ratio < 15 and solidity > 0.5:
                        bbox_data = {'x': x, 'y': y, 'width': w, 'height': h}

                        element = self.create_element(
                            text="[DETECTED_TEXT_REGION]",
                            bbox_data=bbox_data,
                            page_num=page_num,
                            confidence=0.5,
                            metadata={
                                'detection_method': 'contours',
                                'aspect_ratio': aspect_ratio,
                                'solidity': solidity,
                                'contour_area': area
                            }
                        )
                        elements.append(element)

        except Exception as e:
            logger.debug(f"Contour detection failed: {e}")

        return elements

    def _detect_with_edges(self, image: np.ndarray, page_num: int) -> List[ExtractedElement]:
        elements = []

        try:
            gray = self._ensure_grayscale(image)

            blurred = self._cv2.GaussianBlur(gray, (5, 5), 0)

            edges = self._cv2.Canny(blurred, 50, 150)

            kernel = self._cv2.getStructuringElement(self._cv2.MORPH_RECT, (3, 3))
            dilated = self._cv2.dilate(edges, kernel, iterations=2)

            contours, _ = self._cv2.findContours(dilated, self._cv2.RETR_EXTERNAL, self._cv2.CHAIN_APPROX_SIMPLE)

            for contour in contours:
                x, y, w, h = self._cv2.boundingRect(contour)

                if w > 20 and h > 10 and w < image.shape[1] * 0.7:
                    aspect_ratio = w / h

                    if 0.2 < aspect_ratio < 10:
                        bbox_data = {'x': x, 'y': y, 'width': w, 'height': h}

                        element = self.create_element(
                            text="[DETECTED_TEXT_REGION]",
                            bbox_data=bbox_data,
                            page_num=page_num,
                            confidence=0.4,
                            metadata={
                                'detection_method': 'edges',
                                'aspect_ratio': aspect_ratio
                            }
                        )
                        elements.append(element)

        except Exception as e:
            logger.debug(f"Edge detection failed: {e}")

        return elements

    def _ensure_grayscale(self, image: np.ndarray) -> np.ndarray:
        if len(image.shape) == 3:
            return self._cv2.cvtColor(image, self._cv2.COLOR_BGR2GRAY)
        return image

    def _filter_and_deduplicate(self, elements: List[ExtractedElement]) -> List[ExtractedElement]:
        if not elements:
            return elements

        elements.sort(key=lambda e: e.confidence, reverse=True)

        filtered = []
        for element in elements:
            is_duplicate = False

            for existing in filtered:
                if element.bbox and existing.bbox:
                    overlap = self._calculate_overlap(element.bbox, existing.bbox)
                    if overlap > 0.5:
                        is_duplicate = True
                        break

            if not is_duplicate:
                filtered.append(element)

        return filtered[:50]

    def _calculate_overlap(self, bbox1, bbox2) -> float:
        try:
            x1 = max(bbox1.x, bbox2.x)
            y1 = max(bbox1.y, bbox2.y)
            x2 = min(bbox1.x + bbox1.width, bbox2.x + bbox2.width)
            y2 = min(bbox1.y + bbox1.height, bbox2.y + bbox2.height)

            if x2 <= x1 or y2 <= y1:
                return 0.0

            intersection = (x2 - x1) * (y2 - y1)
            area1 = bbox1.width * bbox1.height
            area2 = bbox2.width * bbox2.height

            return intersection / min(area1, area2)

        except:
            return 0.0

    def get_engine_info(self) -> Dict[str, Any]:
        info = {
            'engine_name': 'OpenCV Text Detection',
            'version': 'Unknown',
            'capabilities': [
                'Text region detection',
                'Edge detection',
                'Contour analysis',
                'MSER detection'
            ],
            'limitations': [
                'No actual text recognition',
                'Only detects potential text regions',
                'Requires other OCR for text extraction'
            ],
            'use_case': 'Fallback when other OCR engines fail'
        }

        if self._cv2:
            try:
                info['version'] = self._cv2.__version__
            except:
                pass

        return info


def create_opencv_engine() -> OpenCVEngine:
    return OpenCVEngine()