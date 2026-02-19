"""
Intelligent fallback detector - evaluates PDF.js results quality
and decides whether to escalate to the AWS OCR+LLM pipeline.

Results are in AnalysisResult[] format:
[{"category": "...", "question": "...", "pairs": [{"answer": "...", "confidence": 0.95}]}]
"""

import structlog
from typing import Dict, List, Tuple

logger = structlog.get_logger()

# Thresholds
CONFIDENCE_THRESHOLD = 0.70
NOT_FOUND_THRESHOLD = 5
GARBAGE_RATIO_THRESHOLD = 0.15
MIN_WORD_COUNT = 50


class FallbackDetector:
    """Evaluates PDF.js extraction quality to decide if AWS fallback is needed."""

    def should_fallback_to_aws(
        self,
        pdfjs_results: List[Dict],
        text_quality: Dict,
    ) -> Tuple[bool, str]:
        """
        Evaluate if PDF.js results are good enough or need AWS pipeline.

        Args:
            pdfjs_results: List of AnalysisResult dicts from PDF.js LLM processing
                           Format: [{category, question, pairs: [{answer, reference, confidence}]}]
            text_quality: Text quality metrics from _analyze_text_quality()

        Returns:
            (should_fallback: bool, reason: str)
        """
        # Check 1: Empty or no results
        if not pdfjs_results:
            return True, "No answers extracted from PDF.js"

        # Check 2: Scanned/image-based PDF
        if text_quality.get("is_scanned", False):
            return True, "Scanned/image-based PDF detected - OCR required"

        # Check 3: High garbage text ratio
        garbage_ratio = text_quality.get("garbage_ratio", 0)
        if garbage_ratio > GARBAGE_RATIO_THRESHOLD:
            return True, f"High garbage text ratio: {garbage_ratio:.1%} (>{GARBAGE_RATIO_THRESHOLD:.0%})"

        # Extract answers from AnalysisResult[] format
        answers = self._extract_answers(pdfjs_results)

        # Check 4: Too many "Not Found" answers
        not_found_count = sum(
            1 for a in answers if self._is_not_found(a["answer"])
        )
        if not_found_count > NOT_FOUND_THRESHOLD:
            return True, f"{not_found_count} answers missing (>{NOT_FOUND_THRESHOLD} threshold)"

        # Check 5: Low average confidence
        confidences = [
            a["confidence"]
            for a in answers
            if a["confidence"] is not None and a["confidence"] > 0
            and not self._is_not_found(a["answer"])
        ]
        if confidences:
            avg_confidence = sum(confidences) / len(confidences)
            if avg_confidence < CONFIDENCE_THRESHOLD:
                return True, f"Low confidence: {avg_confidence:.2%} (<{CONFIDENCE_THRESHOLD:.0%})"

        # Check 6: Complex tables detected but poorly extracted
        if text_quality.get("has_complex_tables", False):
            deflection_results = [
                r for r in pdfjs_results
                if r.get("category", "") == "Deflection Criteria"
            ]
            deflection_not_found = sum(
                1 for r in deflection_results
                if r.get("pairs") and self._is_not_found(r["pairs"][0].get("answer", ""))
            )
            if deflection_not_found >= 3:
                return True, "Complex tables detected but poorly extracted"

        # All checks passed
        logger.info(
            "pdfjs_quality_sufficient",
            not_found=not_found_count,
            avg_confidence=f"{sum(confidences)/len(confidences):.2%}" if confidences else "N/A",
        )
        return False, "PDF.js results sufficient"

    @staticmethod
    def _extract_answers(results: List[Dict]) -> List[Dict]:
        """Extract flat answer list from AnalysisResult[] format."""
        answers = []
        for r in results:
            pairs = r.get("pairs", [])
            if pairs:
                pair = pairs[0]  # Primary answer
                answers.append({
                    "answer": pair.get("answer", "Not Found"),
                    "confidence": pair.get("confidence", 0),
                })
            else:
                answers.append({"answer": "Not Found", "confidence": 0})
        return answers

    @staticmethod
    def _is_not_found(answer: str) -> bool:
        """Check if an answer indicates 'not found'."""
        if not answer:
            return True
        normalized = answer.strip().lower()
        return normalized in (
            "not found", "n/a", "na", "none", "not specified",
            "not available", "not provided", "unknown", "",
        )
