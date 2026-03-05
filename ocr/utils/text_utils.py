# ocr/utils/text_utils.py

import re
from typing import List
from ocr.core.models import ExtractedElement


class TextProcessor:

    @staticmethod
    def clean_text(text: str) -> str:
        if not text:
            return ""

        # Remove excessive whitespace
        cleaned = re.sub(r'\s+', ' ', text.strip())

        # Remove leading/trailing punctuation
        cleaned = re.sub(r'^[-–—\s]+|[-–—\s]+$', '', cleaned)

        # Skip pure punctuation
        if cleaned in ['.', ',', ';', ':', '!', '?', '-', '_', '|']:
            return ""

        return cleaned

    @staticmethod
    def is_valid_text(text: str, confidence: float = 0.0, min_length: int = 2) -> bool:
        if not text or len(text.strip()) < min_length:
            return False

        # Skip whitespace-only
        if text.isspace():
            return False

        # Skip non-printable
        if not text.isprintable():
            return False

        # Skip pure punctuation lines
        if all(c in '.-_|' for c in text):
            return False

        # Check alphanumeric ratio
        if len(text) > 0:
            alpha_ratio = sum(1 for c in text if c.isalnum()) / len(text)
            if alpha_ratio < 0.3:
                return False

        return True

    @staticmethod
    def filter_low_quality_elements(elements: List[ExtractedElement],
                                    min_confidence: float = 0.3,
                                    min_text_length: int = 2) -> List[ExtractedElement]:
        filtered = []

        for element in elements:
            # Apply confidence filter
            if element.confidence < min_confidence:
                continue

            # Clean and validate text
            cleaned_text = TextProcessor.clean_text(element.text)
            if not TextProcessor.is_valid_text(cleaned_text, element.confidence, min_text_length):
                continue

            # Update element with cleaned text
            element.text = cleaned_text
            filtered.append(element)

        return filtered