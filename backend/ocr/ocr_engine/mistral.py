import logging
import os
import tempfile
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
import numpy as np
import cv2

from ocr.ocr_engine.base import BaseOCREngine
from ocr.core.models import ExtractedElement
from ocr.core.exceptions import OCRCredentialsError, OCRExtractionError, DependencyError

logger = logging.getLogger(__name__)


class MistralOCREngine(BaseOCREngine):

    def __init__(self):
        super().__init__("mistral_ocr", priority=25)  # Medium priority
        self._mistral_client = None
        self._initialize_client()

    def _initialize_client(self) -> None:
        try:
            from mistralai import Mistral, DocumentURLChunk
            self._DocumentURLChunk = DocumentURLChunk

            api_key = self.config.get('ocr.mistral_api_key') or os.getenv('MISTRAL_API_KEY')

            if not api_key:
                logger.warning("Mistral API key not found in config or environment variables")
                self._is_configured = False
                return

            self._mistral_client = Mistral(api_key=api_key)

            self._is_configured = True
            logger.info("Mistral AI client initialized successfully")

        except ImportError:
            logger.error("Mistral AI SDK not found. Install with: pip install mistralai")
            raise DependencyError("mistralai", "pip install mistralai")

        except Exception as e:
            logger.error(f"Failed to initialize Mistral client: {e}")
            self._is_configured = False

    def _check_availability(self) -> Tuple[bool, str]:
        if not self._is_configured or not self._mistral_client:
            return False, "Mistral client not initialized"

        try:
            files = self._mistral_client.files.list()
            return True, "Mistral AI OCR available"

        except Exception as e:
            error_str = str(e).lower()
            if "unauthorized" in error_str or "invalid api key" in error_str:
                return False, "Invalid Mistral API key"
            elif "quota" in error_str or "limit" in error_str:
                return False, "Mistral API quota exceeded"
            else:
                return False, f"Mistral connection failed: {e}"

    def _extract_text_impl(self, image: np.ndarray, page_num: int, **kwargs) -> List[ExtractedElement]:
        processed_image = self._prepare_image_for_mistral(image)
        if processed_image is None:
            raise OCRExtractionError(self.name, page_num, "Image preprocessing failed")

        success, buffer = cv2.imencode('.png', processed_image)
        if not success:
            raise OCRExtractionError(self.name, page_num, "Failed to encode image")

        image_bytes = buffer.tobytes()

        max_size = 10 * 1024 * 1024
        if len(image_bytes) > max_size:
            raise OCRExtractionError(
                self.name, page_num,
                f"Image too large: {len(image_bytes) / 1024 / 1024:.1f}MB (max: 10MB)"
            )

        temp_file = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp_file:
                tmp_file.write(image_bytes)
                temp_file = Path(tmp_file.name)

            upload_file = self._mistral_client.files.upload(
                file={
                    "file_name": temp_file.stem,
                    "content": temp_file.read_bytes(),
                },
                purpose="ocr",
            )

            signed_url = self._mistral_client.files.get_signed_url(
                file_id=upload_file.id,
                expiry=1
            )

            result = self._mistral_client.ocr.process(
                document=self._DocumentURLChunk(document_url=signed_url.url),
                model="mistral-ocr-latest",
                include_image_base64=False
            )

            elements = self._process_mistral_response(result, processed_image.shape, page_num)

            try:
                self._mistral_client.files.delete(file_id=upload_file.id)
            except:
                pass

            logger.debug(f"Mistral OCR extracted {len(elements)} elements from page {page_num}")
            return elements

        except Exception as e:
            error_msg = str(e)
            if "InvalidFileFormat" in error_msg:
                raise OCRExtractionError(self.name, page_num, f"Invalid image format: {error_msg}")
            elif "QuotaExceeded" in error_msg:
                raise OCRExtractionError(self.name, page_num, "Mistral OCR quota exceeded")
            elif "Unauthorized" in error_msg:
                raise OCRCredentialsError("Mistral AI", "Invalid API key")
            else:
                raise OCRExtractionError(self.name, page_num, f"Mistral API error: {error_msg}")

        finally:
            if temp_file and temp_file.exists():
                try:
                    temp_file.unlink()
                except:
                    pass

    def _prepare_image_for_mistral(self, image: np.ndarray) -> Optional[np.ndarray]:
        try:
            if len(image.shape) == 3:
                if image.shape[2] == 3:
                    image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
                elif image.shape[2] == 4:
                    image_rgb = cv2.cvtColor(image, cv2.COLOR_BGRA2RGB)
                else:
                    image_rgb = image
            else:
                image_rgb = cv2.cvtColor(image, cv2.COLOR_GRAY2RGB)

            height, width = image_rgb.shape[:2]

            if height < 32 or width < 32:
                logger.warning(f"Image too small for Mistral: {width}x{height}")
                return None

            max_dimension = 4000
            if height > max_dimension or width > max_dimension:
                scale = min(max_dimension / width, max_dimension / height)
                new_width = int(width * scale)
                new_height = int(height * scale)
                image_rgb = cv2.resize(image_rgb, (new_width, new_height), interpolation=cv2.INTER_AREA)
                logger.info(f"Resized image from {width}x{height} to {new_width}x{new_height}")

            return image_rgb

        except Exception as e:
            logger.error(f"Image preparation failed: {e}")
            return None

    def _process_mistral_response(self, result, image_shape: Tuple[int, int], page_num: int) -> List[ExtractedElement]:
        elements = []
        height, width = image_shape[:2]

        try:
            for page in result.pages:
                for block in page.blocks:
                    if not block.text or not block.text.strip():
                        continue
                    confidence = getattr(block, 'confidence', 0.8)

                    if hasattr(block, 'bounding_box') and block.bounding_box:
                        bbox_points = block.bounding_box

                        if len(bbox_points) >= 4:
                            x_coords = [point.x for point in bbox_points]
                            y_coords = [point.y for point in bbox_points]

                            bbox_data = {
                                'x': int(min(x_coords) * width),
                                'y': int(min(y_coords) * height),
                                'width': int((max(x_coords) - min(x_coords)) * width),
                                'height': int((max(y_coords) - min(y_coords)) * height)
                            }
                        else:
                            continue
                    else:
                        bbox_data = {
                            'x': 0,
                            'y': 0,
                            'width': width,
                            'height': height // 10
                        }

                    metadata = {
                        'block_id': getattr(block, 'id', None),
                        'mistral_confidence': confidence,
                        'block_type': getattr(block, 'type', 'text'),
                        'page_index': getattr(page, 'index', page_num - 1)
                    }

                    if hasattr(block, 'bounding_box') and block.bounding_box:
                        metadata['polygon'] = [
                            {'x': point.x * width, 'y': point.y * height}
                            for point in block.bounding_box
                        ]

                    element = self.create_element(
                        text=block.text,
                        bbox_data=bbox_data,
                        page_num=page_num,
                        confidence=confidence,
                        metadata=metadata
                    )
                    elements.append(element)

        except Exception as e:
            logger.error(f"Error processing Mistral response: {e}")
            # Return partial results if any were processed

        return elements

    def _detect_tables_from_elements(self, elements: List[ExtractedElement], page_num: int) -> List[Dict[str, Any]]:

        tables = []

        if len(elements) < 4:
            return tables

        rows = {}
        for element in elements:
            if element.bbox:
                y_key = round(element.bbox.y / 20) * 20
                if y_key not in rows:
                    rows[y_key] = []
                rows[y_key].append(element)

        potential_rows = [row_elements for row_elements in rows.values() if len(row_elements) > 1]

        if len(potential_rows) >= 2:
            table_elements = [elem for row in potential_rows for elem in row]

            if table_elements:
                min_x = min(elem.bbox.x for elem in table_elements if elem.bbox)
                min_y = min(elem.bbox.y for elem in table_elements if elem.bbox)
                max_x = max(elem.bbox.x + elem.bbox.width for elem in table_elements if elem.bbox)
                max_y = max(elem.bbox.y + elem.bbox.height for elem in table_elements if elem.bbox)

                table_bbox = {
                    'x': min_x,
                    'y': min_y,
                    'width': max_x - min_x,
                    'height': max_y - min_y
                }

                table_rows = []
                for row_elements in potential_rows:
                    row_texts = [elem.text for elem in sorted(row_elements, key=lambda e: e.bbox.x if e.bbox else 0)]
                    table_rows.append(row_texts)

                table_data = {
                    'page_number': page_num,
                    'bbox': table_bbox,
                    'rows': table_rows,
                    'headers': table_rows[0] if table_rows else [],
                    'confidence': 0.6,
                    'table_id': "mistral_detected_table_0",
                    'cell_count': len(table_elements),
                    'detection_method': 'text_alignment'
                }

                tables.append(table_data)

        return tables

    def get_service_info(self) -> Dict[str, Any]:
        return {
            'service_name': 'Mistral AI OCR',
            'supports_tables': False,
            'supports_layout': True,
            'max_file_size': '10MB',
            'supported_formats': ['PNG', 'JPEG', 'PDF'],
            'pricing_model': 'pay-per-request',
            'rate_limits': True,
            'api_version': 'latest'
        }


def create_mistral_ocr_engine() -> MistralOCREngine:
    return MistralOCREngine()
