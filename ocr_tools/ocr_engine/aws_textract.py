import logging
from typing import List, Dict, Any, Tuple, Optional
import numpy as np
import cv2

from ocr_tools.ocr_engine.base import BaseOCREngine
from ocr_tools.core.models import ExtractedElement, BoundingBox
from ocr_tools.core.exceptions import OCRCredentialsError, OCRConfigurationError, OCRExtractionError, DependencyError

logger = logging.getLogger(__name__)


class AWSTextractEngine(BaseOCREngine):

    def __init__(self):
        super().__init__("aws_textract", priority=1)  # High priority
        self._textract_client = None
        self._initialize_client()

    def _initialize_client(self) -> None:
        try:
            import boto3
            from botocore.exceptions import NoCredentialsError, ClientError

            region = self.config.get('ocr.aws_region', 'us-east-1')
            access_key = self.config.get('ocr.aws_access_key_id')
            secret_key = self.config.get('ocr.aws_secret_access_key')
            # $env: AWS_ACCESS_KEY_ID = "key"
            # $env: AWS_SECRET_ACCESS_KEY = "key"

            session_token = self.config.get('ocr.aws_session_token')

            if access_key and secret_key:
                kwargs = {
                    'region_name': region,
                    'aws_access_key_id': access_key,
                    'aws_secret_access_key': secret_key
                }
                if session_token:
                    kwargs['aws_session_token'] = session_token

                self._textract_client = boto3.client('textract', **kwargs)
            else:
                self._textract_client = boto3.client('textract', region_name=region)

            self._is_configured = True
            logger.info("AWS Textract client initialized successfully")

        except ImportError:
            logger.error("boto3 library not found. Install with: pip install boto3")
            raise DependencyError("boto3", "pip install boto3")

        except NoCredentialsError:
            logger.error("AWS credentials not found")
            raise OCRCredentialsError("AWS Textract", "AWS credentials not configured")

        except Exception as e:
            logger.error(f"Failed to initialize AWS Textract client: {e}")
            self._is_configured = False

    def _check_availability(self) -> Tuple[bool, str]:
        if not self._is_configured or not self._textract_client:
            return False, "AWS Textract client not initialized"

        try:
            self._textract_client.get_document_analysis(JobId="test-job-id")
        except Exception as e:
            error_str = str(e).lower()
            if "credentials" in error_str or "access denied" in error_str:
                return False, "Invalid AWS credentials"
            elif "invalidjobidexception" in error_str or "invalid job id" in error_str:
                return True, ""
            else:
                return False, f"AWS Textract connection failed: {e}"

        return True, ""

    def _extract_text_impl(self, image: np.ndarray, page_num: int, **kwargs) -> List[ExtractedElement]:

        processed_image = self._prepare_image_for_textract(image)
        if processed_image is None:
            raise OCRExtractionError(self.name, page_num, "Image preprocessing failed")

        success, buffer = cv2.imencode('.png', processed_image)
        if not success:
            raise OCRExtractionError(self.name, page_num, "Failed to encode image")

        image_bytes = buffer.tobytes()

        if len(image_bytes) > 10 * 1024 * 1024:
            raise OCRExtractionError(
                self.name, page_num,
                f"Image too large: {len(image_bytes) / 1024 / 1024:.1f}MB (max: 10MB)"
            )

        try:
            response = self._textract_client.detect_document_text(
                Document={'Bytes': image_bytes}
            )

            elements = self._process_textract_response(response, processed_image.shape, page_num)

            logger.debug(f"AWS Textract extracted {len(elements)} elements from page {page_num}")
            return elements

        except Exception as e:
            error_msg = str(e)
            if "InvalidParameterException" in error_msg:
                raise OCRExtractionError(self.name, page_num, f"Invalid image format: {error_msg}")
            elif "ProvisionedThroughputExceededException" in error_msg:
                raise OCRExtractionError(self.name, page_num, "AWS Textract rate limit exceeded")
            elif "AccessDeniedException" in error_msg:
                raise OCRCredentialsError("AWS Textract", "Access denied - check credentials and permissions")
            else:
                raise OCRExtractionError(self.name, page_num, f"Textract API error: {error_msg}")

    def _prepare_image_for_textract(self, image: np.ndarray) -> Optional[np.ndarray]:
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
                logger.warning(f"Image too small for Textract: {width}x{height}")
                return None

            if height > 10000 or width > 10000:
                scale = min(10000 / width, 10000 / height)
                new_width = int(width * scale)
                new_height = int(height * scale)
                image_rgb = cv2.resize(image_rgb, (new_width, new_height), interpolation=cv2.INTER_AREA)
                logger.info(f"Resized image from {width}x{height} to {new_width}x{new_height}")

            estimated_size = height * width * 3 * 2
            if estimated_size > 8 * 1024 * 1024:
                scale = (8 * 1024 * 1024 / estimated_size) ** 0.5
                new_width = int(width * scale)
                new_height = int(height * scale)
                image_rgb = cv2.resize(image_rgb, (new_width, new_height), interpolation=cv2.INTER_AREA)
                logger.info(f"Resized for file size: {new_width}x{new_height}")

            return image_rgb

        except Exception as e:
            logger.error(f"Image preparation failed: {e}")
            return None

    def _process_textract_response(self, response: Dict[str, Any],
                                   image_shape: Tuple[int, int], page_num: int) -> List[ExtractedElement]:
        elements = []
        height, width = image_shape[:2]

        for block in response.get('Blocks', []):
            if block['BlockType'] == 'WORD':
                text = block['Text']
                confidence = block['Confidence'] / 100.0  # Convert to 0-1 range

                bbox_data = block['Geometry']['BoundingBox']
                bbox = {
                    'x': int(bbox_data['Left'] * width),
                    'y': int(bbox_data['Top'] * height),
                    'width': int(bbox_data['Width'] * width),
                    'height': int(bbox_data['Height'] * height)
                }

                metadata = {
                    'block_id': block['Id'],
                    'textract_confidence': block['Confidence'],
                    'block_type': block['BlockType']
                }

                if 'Polygon' in block['Geometry']:
                    polygon = []
                    for point in block['Geometry']['Polygon']:
                        polygon.append({
                            'x': point['X'] * width,
                            'y': point['Y'] * height
                        })
                    metadata['polygon'] = polygon

                element = self.create_element(text, bbox, page_num, confidence, metadata)
                elements.append(element)

        return elements

    def _process_table_response(self, response: Dict[str, Any],
                                image_shape: Tuple[int, int], page_num: int) -> List[Dict[str, Any]]:
        tables = []
        height, width = image_shape[:2]

        blocks = {block['Id']: block for block in response.get('Blocks', [])}

        for block in response.get('Blocks', []):
            if block['BlockType'] == 'TABLE':
                table_data = self._extract_table_data(block, blocks, width, height, page_num)
                if table_data:
                    tables.append(table_data)

        return tables

    def _extract_table_data(self, table_block: Dict[str, Any], all_blocks: Dict[str, Any],
                            width: int, height: int, page_num: int) -> Optional[Dict[str, Any]]:
        try:
            bbox_data = table_block['Geometry']['BoundingBox']
            table_bbox = {
                'x': int(bbox_data['Left'] * width),
                'y': int(bbox_data['Top'] * height),
                'width': int(bbox_data['Width'] * width),
                'height': int(bbox_data['Height'] * height)
            }

            cells = []
            if 'Relationships' in table_block:
                for relationship in table_block['Relationships']:
                    if relationship['Type'] == 'CHILD':
                        for child_id in relationship['Ids']:
                            child_block = all_blocks.get(child_id)
                            if child_block and child_block['BlockType'] == 'CELL':
                                cell_data = self._extract_cell_data(child_block, all_blocks, width, height)
                                if cell_data:
                                    cells.append(cell_data)

            if not cells:
                return None

            max_row = max(cell['row_index'] for cell in cells)
            max_col = max(cell['column_index'] for cell in cells)

            table_rows = []
            for row in range(max_row + 1):
                table_row = [''] * (max_col + 1)
                for cell in cells:
                    if cell['row_index'] == row:
                        table_row[cell['column_index']] = cell['text']
                table_rows.append(table_row)

            return {
                'page_number': page_num,
                'bbox': table_bbox,
                'rows': table_rows,
                'headers': table_rows[0] if table_rows else [],
                'confidence': table_block.get('Confidence', 0) / 100.0,
                'table_id': table_block['Id'],
                'cell_count': len(cells)
            }

        except Exception as e:
            logger.error(f"Error extracting table data: {e}")
            return None

    def _extract_cell_data(self, cell_block: Dict[str, Any], all_blocks: Dict[str, Any],
                           width: int, height: int) -> Optional[Dict[str, Any]]:
        try:
            cell_text = ""
            if 'Relationships' in cell_block:
                for relationship in cell_block['Relationships']:
                    if relationship['Type'] == 'CHILD':
                        word_texts = []
                        for child_id in relationship['Ids']:
                            child_block = all_blocks.get(child_id)
                            if child_block and child_block['BlockType'] == 'WORD':
                                word_texts.append(child_block['Text'])
                        cell_text = ' '.join(word_texts)

            row_index = cell_block.get('RowIndex', 0)
            column_index = cell_block.get('ColumnIndex', 0)

            bbox_data = cell_block['Geometry']['BoundingBox']
            cell_bbox = {
                'x': int(bbox_data['Left'] * width),
                'y': int(bbox_data['Top'] * height),
                'width': int(bbox_data['Width'] * width),
                'height': int(bbox_data['Height'] * height)
            }

            return {
                'text': cell_text.strip(),
                'row_index': row_index,
                'column_index': column_index,
                'bbox': cell_bbox,
                'confidence': cell_block.get('Confidence', 0) / 100.0,
                'cell_id': cell_block['Id']
            }

        except Exception as e:
            logger.error(f"Error extracting cell data: {e}")
            return None

    def get_service_info(self) -> Dict[str, Any]:
        return {
            'service_name': 'Amazon Textract',
            'region': self.config.get('ocr.aws_region', 'us-east-1'),
            'supports_tables': True,
            'supports_forms': True,
            'max_file_size': '10MB',
            'supported_formats': ['PNG', 'JPEG', 'PDF', 'TIFF'],
            'pricing_model': 'pay-per-use',
            'rate_limits': True
        }


def create_aws_textract_engine() -> AWSTextractEngine:
    return AWSTextractEngine()