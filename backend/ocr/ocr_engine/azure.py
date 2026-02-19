import logging
from typing import List, Dict, Any, Tuple, Optional
import numpy as np
import cv2

from ocr.ocr_engine.base import BaseOCREngine
from ocr.core.models import ExtractedElement, BoundingBox, ElementType
from ocr.core.exceptions import OCRCredentialsError, OCRConfigurationError, OCRExtractionError, DependencyError
from azure.ai.formrecognizer import DocumentAnalysisClient
from azure.core.credentials import AzureKeyCredential
from azure.ai.formrecognizer import DocumentAnalysisClient
from azure.core.credentials import AzureKeyCredential



logger = logging.getLogger(__name__)


class AzureOCREngine(BaseOCREngine):

    def __init__(self):
        super().__init__("azure_ocr", priority=50)
        self._azure_client = None
        self._initialize_client()

    def _initialize_client(self) -> None:
        try:
            import os
            import ssl
            import urllib3
            import requests
            from azure.ai.formrecognizer import DocumentAnalysisClient
            from azure.core.credentials import AzureKeyCredential
            from azure.core.pipeline.transport import RequestsTransport

            # Global SSL bypass
            os.environ['PYTHONHTTPSVERIFY'] = '0'
            os.environ['CURL_CA_BUNDLE'] = ''
            os.environ['REQUESTS_CA_BUNDLE'] = ''
            ssl._create_default_https_context = ssl._create_unverified_context
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

            endpoint = self.config.get('ocr.azure_endpoint')
            api_key = self.config.get('ocr.azure_api_key')

            if not endpoint or not api_key:
                logger.warning("Azure OCR endpoint or API key not configured")
                self._is_configured = False
                return

            # Create custom session with SSL verification disabled
            session = requests.Session()
            session.verify = False
            session.trust_env = False

            # Custom SSL context
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE

            # Custom adapter with SSL bypass
            class NoSSLAdapter(requests.adapters.HTTPAdapter):
                def init_poolmanager(self, *args, **kwargs):
                    kwargs['ssl_context'] = ssl_context
                    return super().init_poolmanager(*args, **kwargs)

            session.mount('https://', NoSSLAdapter())

            # Create transport with custom session
            transport = RequestsTransport(session=session)

            self._azure_client = DocumentAnalysisClient(
                endpoint=endpoint,
                credential=AzureKeyCredential(api_key),
                transport=transport
            )

            self._is_configured = True
            logger.info("Azure Document Intelligence client initialized successfully")

        except ImportError:
            logger.error("Azure SDK not found. Install with: pip install azure-ai-formrecognizer")
            raise DependencyError("azure-ai-formrecognizer", "pip install azure-ai-formrecognizer")
        except Exception as e:
            logger.error(f"Failed to initialize Azure client: {e}")
            self._is_configured = False


    def _check_availability(self) -> Tuple[bool, str]:
        if not self._is_configured or not self._azure_client:
            return False, "Azure client not initialized"

        try:
            if hasattr(self._azure_client, '_endpoint'):
                return True, "Azure Document Intelligence available"
            else:
                return False, "Azure client not properly configured"

        except Exception as e:
            error_str = str(e).lower()
            if "unauthorized" in error_str or "invalid key" in error_str:
                return False, "Invalid Azure API key"
            else:
                return False, f"Azure connection failed: {e}"

    def _extract_text_impl(self, image: np.ndarray, page_num: int, **kwargs) -> List[ExtractedElement]:

        processed_image = self._prepare_image_for_azure(image)
        if processed_image is None:
            raise OCRExtractionError(self.name, page_num, "Image preprocessing failed")

        success, buffer = cv2.imencode('.png', processed_image)
        if not success:
            raise OCRExtractionError(self.name, page_num, "Failed to encode image")

        image_bytes = buffer.tobytes()

        if len(image_bytes) > 4 * 1024 * 1024:  # 4MB threshold
            logger.warning(f"Large image ({len(image_bytes) / 1024 / 1024:.1f}MB) - may be slow")

        try:
            poller = self._azure_client.begin_analyze_document(
                model_id="prebuilt-document",
                document=image_bytes
            )

            result = poller.result()

            # Process response
            elements = self._process_azure_response(result, processed_image.shape, page_num)

            logger.debug(f"Azure OCR extracted {len(elements)} elements from page {page_num}")
            return elements

        except Exception as e:
            error_msg = str(e)
            if "InvalidRequest" in error_msg:
                raise OCRExtractionError(self.name, page_num, f"Invalid image format: {error_msg}")
            elif "QuotaExceeded" in error_msg:
                raise OCRExtractionError(self.name, page_num, "Azure OCR quota exceeded")
            elif "Unauthorized" in error_msg:
                raise OCRCredentialsError("Azure Document Intelligence", "Invalid API key or endpoint")
            else:
                raise OCRExtractionError(self.name, page_num, f"Azure API error: {error_msg}")

    def _prepare_image_for_azure(self, image: np.ndarray) -> Optional[np.ndarray]:
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

            if height < 50 or width < 50:
                logger.warning(f"Image too small for Azure: {width}x{height}")
                return None

            max_dimension = 10000
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

    def _process_azure_response(self, result, image_shape: Tuple[int, int], page_num: int) -> List[ExtractedElement]:
        elements = []
        height, width = image_shape[:2]

        for page in result.pages:
            for line in page.lines:
                if not line.content.strip():
                    continue

                confidence = getattr(line, 'confidence', 0.9)

                # Extract bounding box
                if line.polygon and len(line.polygon) >= 4:
                    x_coords = [point.x for point in line.polygon]
                    y_coords = [point.y for point in line.polygon]

                    bbox = BoundingBox(
                        x=int(min(x_coords) * width),
                        y=int(min(y_coords) * height),
                        width=int((max(x_coords) - min(x_coords)) * width),
                        height=int((max(y_coords) - min(y_coords)) * height),
                        confidence=confidence
                    )
                else:
                    continue

                metadata = {
                    'provider': 'azure_document_intelligence',
                    'line_id': getattr(line, 'id', None),
                    'azure_confidence': confidence,
                    'page_angle': getattr(page, 'angle', 0),
                    'language': getattr(page, 'language', 'en')
                }

                if line.polygon:
                    metadata['polygon'] = [
                        {'x': point.x * width, 'y': point.y * height}
                        for point in line.polygon
                    ]

                element = ExtractedElement(
                    text=line.content,
                    element_type=ElementType.TEXT,
                    page_number=page_num,
                    confidence=confidence,
                    bbox=bbox,
                    metadata=metadata
                )
                elements.append(element)

        return elements


    def _process_azure_tables(self, result, image_shape: Tuple[int, int], page_num: int) -> List[Dict[str, Any]]:
        tables = []
        height, width = image_shape[:2]

        for table in result.tables:
            try:
                # Build table structure
                max_row = max(cell.row_index for cell in table.cells) + 1
                max_col = max(cell.column_index for cell in table.cells) + 1

                table_rows = [[''] * max_col for _ in range(max_row)]

                for cell in table.cells:
                    table_rows[cell.row_index][cell.column_index] = cell.content

                # Extract bounding box
                if table.bounding_regions:
                    region = table.bounding_regions[0]
                    polygon = region.polygon

                    x_coords = [point.x for point in polygon]
                    y_coords = [point.y for point in polygon]

                    table_bbox = {
                        'x': int(min(x_coords) * width),
                        'y': int(min(y_coords) * height),
                        'width': int((max(x_coords) - min(x_coords)) * width),
                        'height': int((max(y_coords) - min(y_coords)) * height)
                    }
                else:
                    table_bbox = {'x': 0, 'y': 0, 'width': width, 'height': height}

                table_data = {
                    'page_number': page_num,
                    'bbox': table_bbox,
                    'rows': table_rows,
                    'headers': table_rows[0] if table_rows else [],
                    'confidence': getattr(table, 'confidence', 0.9),
                    'table_id': f"azure_table_{len(tables)}",
                    'cell_count': len(table.cells),
                    'row_count': max_row,
                    'column_count': max_col,
                    'provider': 'azure_document_intelligence'
                }

                tables.append(table_data)

            except Exception as e:
                logger.error(f"Error processing Azure table: {e}")
                continue

        return tables

    def get_supported_languages(self) -> List[str]:
        return [
            'en', 'es', 'fr', 'de', 'it', 'pt', 'nl', 'da', 'fi', 'no', 'sv',
            'zh-Hans', 'zh-Hant', 'ja', 'ko', 'ar', 'hi', 'th', 'vi', 'ru',
            'pl', 'cs', 'hu', 'tr', 'he', 'ro', 'bg', 'hr', 'sr', 'sk', 'sl'
        ]

    def get_service_info(self) -> Dict[str, Any]:
        return {
            'service_name': 'Azure Document Intelligence',
            'endpoint': self.config.get('ocr.azure_endpoint', 'Not configured'),
            'supports_tables': True,
            'supports_layout': True,
            'supports_forms': True,
            'max_file_size': '500MB',
            'supported_formats': ['PDF', 'JPEG', 'PNG', 'BMP', 'TIFF', 'HEIF'],
            'pricing_model': 'pay-per-page',
            'rate_limits': True,
            'supported_languages': len(self.get_supported_languages())
        }


def create_azure_ocr_engine() -> AzureOCREngine:
    return AzureOCREngine()