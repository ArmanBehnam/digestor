import logging
from typing import List, Dict, Any, Tuple, Optional
import numpy as np
import base64
import boto3
import json
import io
from PIL import Image

from ocr_tools.ocr_engine.base import BaseOCREngine
from ocr_tools.core.models import ExtractedElement, BoundingBox, ElementType
from ocr_tools.core.exceptions import OCRCredentialsError, OCRConfigurationError, OCRExtractionError, DependencyError

logger = logging.getLogger(__name__)


class ClaudeOCREngine(BaseOCREngine):
    def __init__(self):
        super().__init__("claude_ocr", priority=8)
        self._client = None
        self._initialize_client()

    def _initialize_client(self) -> None:
        try:
            region = self.config.get("ocr.aws_region", "us-east-1")
            access_key = self.config.get("ocr.aws_access_key_id")
            secret_key = self.config.get("ocr.aws_secret_access_key")
            session_token = self.config.get("ocr.aws_session_token")

            if not access_key or not secret_key:
                logger.warning("AWS credentials not configured for Claude OCR")
                self._is_configured = False
                return

            kwargs = {
                "region_name": region,
                "aws_access_key_id": access_key,
                "aws_secret_access_key": secret_key,
            }

            if session_token:
                kwargs["aws_session_token"] = session_token

            self._client = boto3.client("bedrock-runtime", **kwargs)
            self._is_configured = True
            logger.info("Claude OCR (Bedrock) client initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize Claude OCR client: {e}")
            self._is_configured = False
            raise OCRCredentialsError("Claude OCR", str(e))

    def _check_availability(self) -> Tuple[bool, str]:
        if not self._is_configured or not self._client:
            return False, "Claude OCR client not initialized"

        try:
            response = self._client.list_foundation_models()
            return True, "Claude OCR available via Bedrock"
        except Exception as e:
            error_str = str(e).lower()
            if "credentials" in error_str or "unauthorized" in error_str:
                return False, "Invalid AWS credentials for Bedrock"
            elif "not authorized" in error_str:
                return False, "Not authorized to access Bedrock"
            else:
                return False, f"Bedrock connection failed: {e}"

    def _extract_text_impl(self, image: np.ndarray, page_num: int, **kwargs) -> List[ExtractedElement]:
        try:
            pil_img = Image.fromarray(image)
            buffer = io.BytesIO()
            pil_img.save(buffer, format="PNG")
            base64_img = base64.b64encode(buffer.getvalue()).decode("utf-8")

            body = {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 4000,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/png",
                                    "data": base64_img
                                }
                            },
                            {
                                "type": "text",
                                "text": "Extract all visible text from this image. Focus on:\n" +
                                        "- All printed text including headers, labels, and captions\n" +
                                        "- Technical specifications and measurements\n" +
                                        "- Building codes and standards references\n" +
                                        "- Material specifications\n" +
                                        "Return the raw text only, maintaining original formatting where possible."
                            }
                        ]
                    }
                ]
            }

            response = self._client.invoke_model(
                modelId="anthropic.claude-sonnet-4-20250514-v1:0",
                contentType="application/json",
                accept="application/json",
                body=json.dumps(body)
            )

            response_body = json.loads(response["body"].read())

            if "content" in response_body and response_body["content"]:
                text = response_body["content"][0]["text"]
            else:
                logger.warning(f"No content in Claude response for page {page_num}")
                text = ""

            height, width = image.shape[:2]
            bbox = BoundingBox(
                x=0,
                y=0,
                width=width,
                height=height,
                confidence=0.85
            )

            metadata = {
                'provider': 'claude_sonnet_bedrock',
                'model': 'anthropic.claude-3-sonnet-20240229-v1:0',
                'usage': response_body.get('usage', {}),
                'full_page_extraction': True
            }

            element = ExtractedElement(
                text=text.strip(),
                element_type=ElementType.TEXT,
                page_number=page_num,
                confidence=0.85,
                bbox=bbox,
                metadata=metadata
            )

            return [element]

        except Exception as e:
            error_msg = str(e)
            if "ThrottlingException" in error_msg:
                raise OCRExtractionError(self.name, page_num, "Claude API rate limit exceeded")
            elif "ValidationException" in error_msg:
                raise OCRExtractionError(self.name, page_num, f"Invalid request: {error_msg}")
            elif "AccessDeniedException" in error_msg:
                raise OCRCredentialsError("Claude OCR", "Access denied to Bedrock model")
            else:
                raise OCRExtractionError(self.name, page_num, f"Claude API error: {error_msg}")

    def extract_structured_data(self, image: np.ndarray, page_num: int,
                                extraction_type: str = "engineering") -> Dict[str, Any]:
        try:
            pil_img = Image.fromarray(image)
            buffer = io.BytesIO()
            pil_img.save(buffer, format="PNG")
            base64_img = base64.b64encode(buffer.getvalue()).decode("utf-8")

            prompts = {
                "engineering": (
                    "Analyze this engineering document and extract structured information:\n"
                    "- Building codes and standards (IBC, ASCE, etc.)\n"
                    "- Material specifications (steel grades, dimensions)\n"
                    "- Load requirements and criteria\n"
                    "- Dimensions and measurements\n"
                    "- Fire protection requirements\n"
                    "Return as JSON with categories and values."
                ),
                "construction": (
                    "Extract construction specification data:\n"
                    "- CSI sections and divisions\n"
                    "- Material types and grades\n"
                    "- Installation requirements\n"
                    "- Quality control measures\n"
                    "Return as JSON with organized categories."
                )
            }

            prompt = prompts.get(extraction_type, prompts["engineering"])

            body = {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 4000,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/png",
                                    "data": base64_img
                                }
                            },
                            {"type": "text", "text": prompt}
                        ]
                    }
                ]
            }

            response = self._client.invoke_model(
                modelId="anthropic.claude-sonnet-4-20250514-v1:0",
                contentType="application/json",
                accept="application/json",
                body=json.dumps(body)
            )

            response_body = json.loads(response["body"].read())
            text_response = response_body["content"][0]["text"]

            try:
                structured_data = json.loads(text_response)
            except json.JSONDecodeError:
                # If not valid JSON, return the text response
                structured_data = {"raw_analysis": text_response}

            return structured_data

        except Exception as e:
            logger.warning(f"Structured extraction failed: {e}")
            return {}

    def get_supported_features(self) -> List[str]:
        return [
            "text_extraction",
            "structured_analysis",
            "technical_document_understanding",
            "multi_language_support",
            "reasoning_based_extraction"
        ]

    def get_service_info(self) -> Dict[str, Any]:
        return {
            'service_name': 'Claude 3 Sonnet via AWS Bedrock',
            'model_id': 'anthropic.claude-3-sonnet-20240229-v1:0',
            'region': self.config.get('ocr.aws_region', 'us-east-1'),
            'supports_reasoning': True,
            'supports_structured_extraction': True,
            'supports_tables': False,  # No bbox extraction
            'supports_layout': False,
            'max_image_size': '20MB',
            'supported_formats': ['JPEG', 'PNG', 'GIF', 'WebP'],
            'pricing_model': 'per-token',
            'rate_limits': True,
            'strengths': [
                'Technical document understanding',
                'Engineering terminology recognition',
                'Reasoning-based extraction',
                'Multi-language support'
            ]
        }

    def validate_configuration(self) -> Dict[str, List[str]]:
        issues = []

        if not self.config.get("ocr.aws_access_key_id"):
            issues.append("AWS access key not configured")

        if not self.config.get("ocr.aws_secret_access_key"):
            issues.append("AWS secret key not configured")

        region = self.config.get("ocr.aws_region", "us-east-1")
        if region not in ["us-east-1", "us-west-2", "ap-southeast-1", "eu-central-1"]:
            issues.append(f"Region {region} may not support Claude models")

        return {"claude_ocr": issues}


def create_claude_ocr_engine() -> ClaudeOCREngine:
    return ClaudeOCREngine()