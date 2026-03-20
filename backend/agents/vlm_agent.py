# agents/vlm_agent.py
"""
Tier 3 Agent: Vision Language Model (Gemini Flash) for answering
questions from PDF page images when OCR+LLM (Tier 2) still has gaps.

Only processes questions that remain unanswered after Tier 2.
Converts PDF pages to images and sends them to Gemini with the
missing questions.
"""

import io
import logging
from typing import Any, Dict, List
from pathlib import Path

from .base import Talk2DrawingsBaseAgent

logger = logging.getLogger(__name__)

NOT_FOUND_THRESHOLD = 5


class VLMAgent(Talk2DrawingsBaseAgent):
    """Tier 3 agent: Use Gemini VLM to answer remaining questions from page images."""

    def __init__(self, config: Dict[str, Any] = None, blackboard=None):
        super().__init__("VLM_Agent", blackboard=blackboard)
        self.config = config or {}
        self.vlm_engine = None

        try:
            from llm.vlm_engine import VLMEngine
            self.vlm_engine = VLMEngine()
            if not self.vlm_engine.is_available:
                logger.warning(f"{self.name}: VLM engine not available (no GEMINI_API_KEY)")
                self.vlm_engine = None
                self.is_available = False
            else:
                logger.info(f"{self.name}: VLM engine initialized")
        except Exception as e:
            logger.warning(f"{self.name}: Could not load VLM engine: {e}")
            self.is_available = False

    def validate_input(self, input_data: Any) -> bool:
        return isinstance(input_data, dict) and 'pdf_path' in input_data

    def _is_not_found(self, answer: str) -> bool:
        """Check if an answer indicates 'not found'."""
        if not answer:
            return True
        normalized = answer.strip().lower()
        return normalized in (
            "not found", "n/a", "na", "none", "not specified",
            "not available", "not provided", "unknown", "",
        )

    def _find_missing_questions(self, analysis_results: List[Dict]) -> List[Dict]:
        """Identify which questions are still unanswered."""
        missing = []
        for i, r in enumerate(analysis_results):
            pairs = r.get("pairs", [])
            if pairs and self._is_not_found(pairs[0].get("answer", "")):
                missing.append({
                    "index": i,
                    "category": r.get("category", ""),
                    "question": r.get("question", ""),
                })
        return missing

    def should_run(self, analysis_results: List[Dict]) -> tuple:
        """Determine if VLM processing is needed.

        Returns (should_run: bool, missing_questions: list, reason: str)
        """
        missing = self._find_missing_questions(analysis_results)
        if len(missing) > NOT_FOUND_THRESHOLD:
            return True, missing, f"{len(missing)} questions still unanswered after Tier 2"
        return False, missing, f"Only {len(missing)} missing (threshold: {NOT_FOUND_THRESHOLD})"

    def _convert_pdf_to_images(self, pdf_path: str) -> List[Dict]:
        """Convert PDF pages to images for VLM processing."""
        try:
            import fitz
        except ImportError:
            raise RuntimeError("PyMuPDF (fitz) not installed")

        doc = fitz.open(pdf_path)
        page_images = []
        for page_num in range(len(doc)):
            pix = doc[page_num].get_pixmap(dpi=150)
            page_images.append({
                "page_number": page_num + 1,
                "image_bytes": pix.tobytes("png"),
                "width": pix.width,
                "height": pix.height,
            })
        doc.close()
        return page_images

    def _merge_vlm_answers(self, analysis_results: List[Dict],
                           vlm_answers: List[Dict]) -> List[Dict]:
        """Merge VLM answers into the existing analysis_results."""
        filled = 0
        for va in vlm_answers:
            idx = va.get("index")
            if idx is not None and idx < len(analysis_results):
                pairs = analysis_results[idx].get("pairs", [])
                if pairs:
                    pairs[0]["answer"] = va["answer"]
                    pairs[0]["confidence"] = va.get("confidence", 0.7)
                    pairs[0]["reference"] = va.get("reference", "Not Found")
                    if va.get("bbox"):
                        pairs[0]["bbox"] = va["bbox"]
                    filled += 1

        logger.info(f"{self.name}: Filled {filled}/{len(vlm_answers)} answers with VLM")
        return analysis_results

    async def process(self, input_data: Dict[str, Any],
                      context: Dict[str, Any] = None) -> Dict[str, Any]:
        """Run VLM on missing questions using PDF page images."""
        if not self.vlm_engine:
            raise Exception("VLM engine not available")

        pdf_path = input_data.get('pdf_path', '')
        analysis_results = input_data.get('analysis_results', [])
        missing_questions = input_data.get('missing_questions', [])

        if not missing_questions:
            missing_questions = self._find_missing_questions(analysis_results)

        if not missing_questions:
            return {
                'success': True,
                'agent': self.name,
                'tier': 3,
                'vlm_answers': [],
                'analysis_results': analysis_results,
                'questions_filled': 0,
            }

        self.log_decision(
            f"Processing {len(missing_questions)} missing questions with VLM",
            f"Using Gemini Flash on page images from {Path(pdf_path).name}",
            decision_type="escalation_triggered"
        )

        # Convert PDF to images
        logger.info(f"{self.name}: Converting {Path(pdf_path).name} to page images")
        page_images = self._convert_pdf_to_images(pdf_path)
        logger.info(f"{self.name}: Sending {len(page_images)} pages + "
                     f"{len(missing_questions)} questions to Gemini VLM")

        # Call VLM
        vlm_answers = self.vlm_engine.answer_questions_from_images(
            page_images, missing_questions)

        # Merge into analysis results
        updated_results = self._merge_vlm_answers(
            [dict(r) for r in analysis_results],  # shallow copy
            vlm_answers
        )

        self.log_decision(
            f"VLM returned {len(vlm_answers)} answers",
            f"Merged into analysis results",
            decision_type="quality_threshold_met"
        )

        return {
            'success': True,
            'agent': self.name,
            'tier': 3,
            'vlm_answers': vlm_answers,
            'analysis_results': updated_results,
            'questions_filled': len(vlm_answers),
        }
