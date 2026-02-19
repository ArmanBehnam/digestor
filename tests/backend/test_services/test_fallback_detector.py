"""
Tests for the FallbackDetector service.
Verifies the intelligent PDF.js → AWS fallback logic.
"""

import pytest
from services.fallback_detector import FallbackDetector


@pytest.fixture
def detector():
    return FallbackDetector()


class TestFallbackDetector:
    """Test FallbackDetector.should_fallback_to_aws()"""

    def test_good_results_no_fallback(self, detector, sample_pdfjs_results, sample_text_quality_good):
        """High-confidence results with good text quality should NOT trigger fallback."""
        should_fallback, reason = detector.should_fallback_to_aws(
            sample_pdfjs_results, sample_text_quality_good
        )
        assert should_fallback is False
        assert "sufficient" in reason.lower() or "no fallback" in reason.lower() or not should_fallback

    def test_empty_results_triggers_fallback(self, detector, sample_text_quality_good):
        """Empty results should trigger fallback."""
        should_fallback, reason = detector.should_fallback_to_aws(
            [], sample_text_quality_good
        )
        assert should_fallback is True

    def test_too_many_not_found_triggers_fallback(self, detector, sample_text_quality_good):
        """More than 5 'Not Found' answers should trigger fallback."""
        results = [
            {"question": f"Q{i}", "answer": "Not Found", "confidence": 0.0}
            for i in range(6)
        ] + [
            {"question": "Q7", "answer": "IBC 2021", "confidence": 0.95}
        ]
        should_fallback, reason = detector.should_fallback_to_aws(
            results, sample_text_quality_good
        )
        assert should_fallback is True
        assert "missing" in reason.lower() or "not found" in reason.lower() or "threshold" in reason.lower()

    def test_low_confidence_triggers_fallback(self, detector, sample_text_quality_good):
        """Average confidence below 70% should trigger fallback."""
        results = [
            {"question": f"Q{i}", "answer": f"Answer {i}", "confidence": 0.50}
            for i in range(10)
        ]
        should_fallback, reason = detector.should_fallback_to_aws(
            results, sample_text_quality_good
        )
        assert should_fallback is True
        assert "confidence" in reason.lower()

    def test_high_garbage_ratio_triggers_fallback(self, detector, sample_pdfjs_results):
        """High garbage text ratio (>15%) should trigger fallback."""
        poor_quality = {
            "is_empty": False,
            "garbage_ratio": 0.25,
            "is_scanned": False,
            "has_complex_tables": False,
            "word_count": 100,
            "char_count": 600,
        }
        should_fallback, reason = detector.should_fallback_to_aws(
            sample_pdfjs_results, poor_quality
        )
        assert should_fallback is True
        assert "garbage" in reason.lower()

    def test_scanned_pdf_triggers_fallback(self, detector, sample_pdfjs_results):
        """Scanned/image-based PDF should trigger fallback."""
        scanned_quality = {
            "is_empty": False,
            "garbage_ratio": 0.05,
            "is_scanned": True,
            "has_complex_tables": False,
            "word_count": 50,
            "char_count": 300,
        }
        should_fallback, reason = detector.should_fallback_to_aws(
            sample_pdfjs_results, scanned_quality
        )
        assert should_fallback is True
        assert "scanned" in reason.lower() or "image" in reason.lower()

    def test_complex_tables_triggers_fallback(self, detector, sample_pdfjs_results):
        """Complex tables with poor extraction should trigger fallback."""
        table_quality = {
            "is_empty": False,
            "garbage_ratio": 0.05,
            "is_scanned": False,
            "has_complex_tables": True,
            "word_count": 100,
            "char_count": 600,
        }
        should_fallback, reason = detector.should_fallback_to_aws(
            sample_pdfjs_results, table_quality
        )
        assert should_fallback is True
        assert "table" in reason.lower()

    def test_borderline_confidence_no_fallback(self, detector, sample_text_quality_good):
        """Confidence at exactly 70% should NOT trigger fallback."""
        results = [
            {"question": f"Q{i}", "answer": f"Answer {i}", "confidence": 0.70}
            for i in range(10)
        ]
        should_fallback, _reason = detector.should_fallback_to_aws(
            results, sample_text_quality_good
        )
        assert should_fallback is False

    def test_exactly_5_not_found_no_fallback(self, detector, sample_text_quality_good):
        """Exactly 5 'Not Found' should NOT trigger fallback (threshold is >5)."""
        results = [
            {"question": f"Q{i}", "answer": "Not Found", "confidence": 0.0}
            for i in range(5)
        ] + [
            {"question": f"Q{i}", "answer": f"Answer {i}", "confidence": 0.85}
            for i in range(5, 26)
        ]
        should_fallback, _reason = detector.should_fallback_to_aws(
            results, sample_text_quality_good
        )
        assert should_fallback is False

    def test_mixed_quality_below_threshold(self, detector):
        """Mixed results with overall low confidence triggers fallback."""
        results = [
            {"question": "Q1", "answer": "IBC 2021", "confidence": 0.95},
            {"question": "Q2", "answer": "ASCE 7-22", "confidence": 0.90},
            {"question": "Q3", "answer": "Not Found", "confidence": 0.0},
            {"question": "Q4", "answer": "Not Found", "confidence": 0.0},
            {"question": "Q5", "answer": "Maybe 50 psf", "confidence": 0.30},
            {"question": "Q6", "answer": "Not Found", "confidence": 0.0},
        ]
        quality = {
            "is_empty": False,
            "garbage_ratio": 0.08,
            "is_scanned": False,
            "has_complex_tables": False,
            "word_count": 80,
            "char_count": 500,
        }
        should_fallback, _reason = detector.should_fallback_to_aws(results, quality)
        # Average confidence: (0.95+0.90+0+0+0.30+0) / 6 = 0.358 → should fallback
        assert should_fallback is True
