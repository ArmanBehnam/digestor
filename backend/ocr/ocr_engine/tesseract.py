import logging
import os
import platform
from typing import List, Dict, Any, Tuple
import numpy as np
import cv2
from ocr.utils.text_utils import TextProcessor
from ocr.ocr_engine.base import BaseOCREngine
from ocr.core.models import ExtractedElement
from ocr.core.exceptions import OCRExtractionError, DependencyError

logger = logging.getLogger(__name__)


class TesseractEngine(BaseOCREngine):

    def __init__(self):
        super().__init__("tesseract", priority=2)
        self._pytesseract = None
        self._initialize_tesseract()

    def _initialize_tesseract(self) -> None:
        try:
            import pytesseract
            self._pytesseract = pytesseract

            tesseract_cmd = self.config.get('ocr.tesseract_cmd')
            if tesseract_cmd:
                pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
            else:
                self._auto_detect_tesseract_path()

            try:
                version = pytesseract.get_tesseract_version()
                logger.info(f"Tesseract OCR initialized successfully (version: {version})")
                self._is_configured = True
            except Exception as e:
                logger.error(f"Tesseract is installed but not working: {e}")
                self._is_configured = False

        except ImportError:
            logger.error("pytesseract library not found. Install with: pip install pytesseract")
            raise DependencyError("pytesseract", "pip install pytesseract")

    def _auto_detect_tesseract_path(self) -> None:
        system = platform.system().lower()

        possible_paths = []

        if system == "windows":
            possible_paths = [
                r"C:\Program Files\Tesseract-OCR\tesseract.exe",
                r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
                r"C:\Users\{}\AppData\Local\Tesseract-OCR\tesseract.exe".format(os.getenv('USERNAME', '')),
                "tesseract.exe"
            ]
        elif system == "darwin":  # macOS
            possible_paths = [
                "/usr/local/bin/tesseract",
                "/opt/homebrew/bin/tesseract",
                "/usr/bin/tesseract",
                "tesseract"
            ]

        for path in possible_paths:
            try:
                if os.path.exists(path) or path == "tesseract" or path == "tesseract.exe":
                    self._pytesseract.pytesseract.tesseract_cmd = path
                    self._pytesseract.get_tesseract_version()
                    logger.info(f"Auto-detected Tesseract at: {path}")
                    return
            except:
                continue

        logger.warning("Could not auto-detect Tesseract installation")

    def _check_availability(self) -> Tuple[bool, str]:
        if not self._is_configured or not self._pytesseract:
            return False, "Tesseract not initialized"

        try:
            version = self._pytesseract.get_tesseract_version()
            return True, f"Tesseract version {version}"
        except Exception as e:
            return False, f"Tesseract not working: {e}"

    def _extract_text_impl(self, image: np.ndarray, page_num: int, **kwargs) -> List[ExtractedElement]:

        configs = self.config.get('ocr.tesseract_configs', self._get_default_configs())

        best_elements = []
        best_confidence = 0

        for config in configs:
            try:
                logger.debug(f"Trying Tesseract config: {config}")
                elements = self._extract_with_config(image, page_num, config)

                if elements:
                    avg_confidence = sum(e.confidence for e in elements) / len(elements)
                    if avg_confidence > best_confidence:
                        best_confidence = avg_confidence
                        best_elements = elements

            except Exception as e:
                logger.debug(f"Tesseract config failed: {config}, error: {e}")
                continue

        if not best_elements:
            logger.debug("All configs failed, trying basic extraction")
            best_elements = self._extract_basic(image, page_num)

        logger.debug(f"Tesseract extracted {len(best_elements)} elements from page {page_num}")
        return best_elements

    def _get_default_configs(self) -> List[str]:
        return [
            # '--psm 6 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789.,;:!?()[]{}/-" ',
            # '--psm 4 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789.,;:!?()[]{}/-" ',
            '--psm 3'
            # '--psm 11',
            # '--psm 8',
            # '--psm 13'
        ]

    def _extract_with_config(self, image: np.ndarray, page_num: int, config: str) -> List[ExtractedElement]:
        try:
            data = self._pytesseract.image_to_data(
                image,
                output_type=self._pytesseract.Output.DICT,
                config=config
            )

            return self._process_tesseract_data(data, page_num)

        except Exception as e:
            raise OCRExtractionError(self.name, page_num, f"Tesseract extraction failed: {e}")

    def _extract_basic(self, image: np.ndarray, page_num: int) -> List[ExtractedElement]:
        try:
            text = self._pytesseract.image_to_string(image, config='--psm 3')

            if text.strip():
                element = self.create_element(
                    text=text.strip(),
                    bbox_data={'x': 0, 'y': 0, 'width': image.shape[1], 'height': image.shape[0]},
                    page_num=page_num,
                    confidence=0.5,
                    metadata={'extraction_method': 'basic_text_extraction'}
                )
                return [element]

            return []

        except Exception as e:
            logger.error(f"Basic Tesseract extraction failed: {e}")
            return []

    def _process_tesseract_data(self, data: Dict[str, List], page_num: int) -> List[ExtractedElement]:
        elements = []

        if not data or 'text' not in data:
            return elements

        for i in range(len(data['text'])):
            text = data['text'][i].strip()
            conf = int(data['conf'][i]) if data['conf'][i] != '-1' else 0

            if not TextProcessor.is_valid_text(text, conf / 100.0):
                continue
            cleaned_text = TextProcessor.clean_text(text)

            bbox_data = {
                'x': data['left'][i],
                'y': data['top'][i],
                'width': data['width'][i],
                'height': data['height'][i]
            }

            metadata = {
                'word_num': data.get('word_num', [0])[i],
                'block_num': data.get('block_num', [0])[i],
                'par_num': data.get('par_num', [0])[i],
                'line_num': data.get('line_num', [0])[i],
                'tesseract_confidence': conf
            }

            element = self.create_element(
                text=cleaned_text,
                bbox_data=bbox_data,
                page_num=page_num,
                confidence=conf / 100.0,
                metadata=metadata
            )
            elements.append(element)

        return elements

    def _is_valid_text(self, text: str, confidence: int) -> bool:
        if not text or len(text) < 1:
            return False

        min_confidence = self.get_confidence_threshold() * 100
        if confidence < min_confidence:
            return False

        if text.isspace():
            return False

        if not text.isprintable():
            return False

        if all(c in '.-_|' for c in text):
            return False

        if len(text) == 1 and confidence < 70:
            return False

        return True

    def get_available_languages(self) -> List[str]:
        if not self.is_available():
            return []

        try:
            langs = self._pytesseract.get_languages(config='')
            return langs
        except Exception as e:
            logger.error(f"Failed to get Tesseract languages: {e}")
            return ['eng']

    def extract_with_language(self, image: np.ndarray, page_num: int, lang: str = 'eng') -> List[ExtractedElement]:
        if not self.is_available():
            return []

        try:
            config = f'-l {lang} --psm 3'
            return self._extract_with_config(image, page_num, config)
        except Exception as e:
            logger.error(f"Language-specific extraction failed for {lang}: {e}")
            return []

    def get_orientation_info(self, image: np.ndarray) -> Dict[str, Any]:
        if not self.is_available():
            return {}

        try:
            osd = self._pytesseract.image_to_osd(image, output_type=self._pytesseract.Output.DICT)
            return {
                'orientation': osd.get('orientation', 0),
                'rotate': osd.get('rotate', 0),
                'orientation_confidence': osd.get('orientation_conf', 0),
                'script': osd.get('script', 'Latin'),
                'script_confidence': osd.get('script_conf', 0)
            }
        except Exception as e:
            logger.debug(f"Failed to get orientation info: {e}")
            return {}

    def preprocess_image(self, image: np.ndarray) -> np.ndarray:

        processed = super().preprocess_image(image)

        try:

            processed = cv2.medianBlur(processed, 3)

            _, processed = cv2.threshold(processed, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 1))
            processed = cv2.morphologyEx(processed, cv2.MORPH_CLOSE, kernel)

            height, width = processed.shape
            if height < 300 or width < 300:
                # Upscale small images
                scale_factor = max(300 / height, 300 / width)
                new_height = int(height * scale_factor)
                new_width = int(width * scale_factor)
                processed = cv2.resize(processed, (new_width, new_height), interpolation=cv2.INTER_CUBIC)

            return processed

        except Exception as e:
            logger.warning(f"Enhanced preprocessing failed, using basic: {e}")
            return processed

    def get_engine_info(self) -> Dict[str, Any]:
        info = {
            'engine_name': 'Tesseract OCR',
            'version': 'Unknown',
            'languages': [],
            'installation_path': 'Unknown',
            'supports_orientation': True,
            'supports_confidence': True,
            'license': 'Apache 2.0'
        }

        if self.is_available():
            try:
                info['version'] = str(self._pytesseract.get_tesseract_version())
                info['languages'] = self.get_available_languages()
                info['installation_path'] = self._pytesseract.pytesseract.tesseract_cmd
            except Exception as e:
                logger.debug(f"Failed to get engine info: {e}")

        return info


def create_tesseract_engine() -> TesseractEngine:
    return TesseractEngine()
