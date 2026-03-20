# agents/pdfjs_agent.py
"""
Tier 1 Agent: PDF.js text extraction + LLM question answering.

Extracts text from PDF using PyMuPDF (server-side equivalent of browser PDF.js),
then runs it through the LLM registry to answer engineering questions.
This is the fastest path and avoids expensive OCR API calls.

Fallback trigger: >5 unanswered or <70% avg confidence -> escalate to Tier 2 (OCR).
"""

import logging
from typing import Any, Dict, List, Optional
from pathlib import Path

from .base import Talk2DrawingsBaseAgent

logger = logging.getLogger(__name__)

# Thresholds matching Week32 FallbackDetector
NOT_FOUND_THRESHOLD = 5
CONFIDENCE_THRESHOLD = 0.70
GARBAGE_RATIO_THRESHOLD = 0.15
MIN_WORD_COUNT = 50

# Question metadata matching the frontend's AnalysisResult[] format
QUESTION_METADATA = [
    {"category": "Building Code", "question": "What is the building code and its version year?"},
    {"category": "Building Code", "question": "Is ASCE 7-XX referred?"},
    {"category": "Deflection Criteria", "question": "What are the exterior wall deflection limits?"},
    {"category": "Deflection Criteria", "question": "What is the interior wall deflection limit?"},
    {"category": "Deflection Criteria", "question": "What is the floor joist framing deflection limit?"},
    {"category": "Deflection Criteria", "question": "What is the roof rafter framing deflection limit?"},
    {"category": "Deflection Criteria", "question": "What is the ceiling joist framing deflection limit?"},
    {"category": "Deflection Criteria", "question": "Maximum primary structure vertical deflection due to live load?"},
    {"category": "Wind Load Criteria", "question": "What is the basic wind speed (Vult)?"},
    {"category": "Wind Load Criteria", "question": "What is the building risk category?"},
    {"category": "Wind Load Criteria", "question": "What is the exposure category?"},
    {"category": "Wind Load Criteria", "question": "What is the internal pressure coefficient (GCpi)?"},
    {"category": "Gravity Loads", "question": "What is the roof live load?"},
    {"category": "Gravity Loads", "question": "What is the roof dead load?"},
    {"category": "Snow Load Criteria", "question": "What is the ground snow load (Pg)?"},
    {"category": "Snow Load Criteria", "question": "What is the snow load importance factor (Is)?"},
    {"category": "Snow Load Criteria", "question": "What is the snow exposure factor (Ce)?"},
    {"category": "Snow Load Criteria", "question": "What is the thermal factor (Ct)?"},
    {"category": "Snow Load Criteria", "question": "What is the flat roof snow load (Pf)?"},
    {"category": "Seismic Load Criteria", "question": "What is the seismic design category?"},
    {"category": "Seismic Load Criteria", "question": "What is the seismic importance factor (Ie)?"},
    {"category": "Seismic Load Criteria", "question": "What is the component importance factor (Ip)?"},
    {"category": "Seismic Load Criteria", "question": "What is the site class?"},
    {"category": "Seismic Load Criteria", "question": "What is the SDS value?"},
    {"category": "Seismic Load Criteria", "question": "What is the SD1 value?"},
]


class PDFJSAgent(Talk2DrawingsBaseAgent):
    """Tier 1 agent: Extract text from PDF, run LLM to answer questions."""

    def __init__(self, config: Dict[str, Any] = None, blackboard=None):
        super().__init__("PDFJS_Agent", blackboard=blackboard)
        self.config = config or {}

        try:
            from llm.llm_engines.llm_registry import LLMRegistry
            from config.config_loader import load_config
            cfg = load_config()
            self.llm_registry = LLMRegistry(cfg)
            self.questions = cfg.get("questions", [])
            logger.info(f"{self.name}: LLM registry loaded with {len(self.questions)} questions")
        except Exception as e:
            logger.warning(f"{self.name}: Could not load LLM registry: {e}")
            self.llm_registry = None
            self.questions = []
            self.is_available = False

    def validate_input(self, input_data: Any) -> bool:
        if isinstance(input_data, (str, Path)):
            path = Path(input_data)
            return path.exists() and path.suffix.lower() == '.pdf'
        return False

    def _extract_text_from_pdf(self, pdf_path: str) -> str:
        """Extract text from PDF using PyMuPDF (server-side PDF.js equivalent)."""
        try:
            import fitz
        except ImportError:
            raise RuntimeError("PyMuPDF (fitz) not installed")

        doc = fitz.open(pdf_path)
        all_text = []
        for page_num in range(len(doc)):
            page = doc[page_num]
            text = page.get_text()
            if text.strip():
                all_text.append(f"[Page {page_num + 1}]\n{text}")
        doc.close()

        return "\n\n".join(all_text)

    def _analyze_text_quality(self, text: str) -> Dict[str, Any]:
        """Analyze extracted text quality (same logic as Week32)."""
        if not text or len(text.strip()) < 50:
            return {"is_empty": True, "garbage_ratio": 1.0, "is_scanned": True,
                    "word_count": 0, "char_count": 0}

        total_chars = len(text)
        garbage_chars = sum(1 for c in text if ord(c) > 127 and not c.isalpha())
        garbage_ratio = garbage_chars / total_chars if total_chars > 0 else 0

        words = text.split()
        is_scanned = len(words) < MIN_WORD_COUNT

        table_indicators = text.count("|") + text.count("\t")
        has_complex_tables = table_indicators > 100

        return {
            "is_empty": False,
            "garbage_ratio": garbage_ratio,
            "is_scanned": is_scanned,
            "has_complex_tables": has_complex_tables,
            "word_count": len(words),
            "char_count": total_chars,
        }

    def _chunk_text(self, text: str, max_chars: int = 80000,
                    overlap: int = 2000) -> List[str]:
        """Split text into overlapping chunks (same logic as Week32)."""
        if len(text) <= max_chars:
            return [text]

        chunks = []
        start = 0
        while start < len(text):
            end = start + max_chars
            if end < len(text):
                newline_pos = text.rfind("\n\n", start + max_chars - overlap, end)
                if newline_pos > start:
                    end = newline_pos
            chunks.append(text[start:end])
            start = end - overlap

        return chunks

    def _normalize_confidence(self, conf) -> float:
        """Normalize confidence to 0.0-1.0 scale."""
        if isinstance(conf, str):
            try:
                conf = float(conf)
            except (ValueError, TypeError):
                return 0.0
        if isinstance(conf, (int, float)):
            if conf > 1.0:
                return min(conf / 100.0, 1.0)
            return max(0.0, min(float(conf), 1.0))
        return 0.0

    def _is_not_found(self, answer: str) -> bool:
        """Check if an answer indicates 'not found'."""
        if not answer:
            return True
        normalized = answer.strip().lower()
        return normalized in (
            "not found", "n/a", "na", "none", "not specified",
            "not available", "not provided", "unknown", "",
        )

    def should_fallback(self, analysis_results: List[Dict],
                        text_quality: Dict) -> tuple:
        """Determine if we should escalate to Tier 2 (OCR).

        Returns (should_fallback: bool, reason: str)
        """
        if not analysis_results:
            return True, "No answers extracted from PDF text"

        if text_quality.get("is_scanned", False):
            return True, "Scanned/image-based PDF detected - OCR required"

        garbage_ratio = text_quality.get("garbage_ratio", 0)
        if garbage_ratio > GARBAGE_RATIO_THRESHOLD:
            return True, f"High garbage text ratio: {garbage_ratio:.1%}"

        # Count not-found answers
        not_found_count = 0
        confidences = []
        for r in analysis_results:
            pairs = r.get("pairs", [])
            if pairs:
                answer = pairs[0].get("answer", "Not Found")
                conf = pairs[0].get("confidence", 0)
                if self._is_not_found(answer):
                    not_found_count += 1
                elif conf > 0:
                    confidences.append(conf)

        if not_found_count > NOT_FOUND_THRESHOLD:
            return True, f"{not_found_count} answers missing (>{NOT_FOUND_THRESHOLD} threshold)"

        if confidences:
            avg_confidence = sum(confidences) / len(confidences)
            if avg_confidence < CONFIDENCE_THRESHOLD:
                return True, f"Low confidence: {avg_confidence:.2%} (<{CONFIDENCE_THRESHOLD:.0%})"

        # Check complex tables with poor deflection extraction
        if text_quality.get("has_complex_tables", False):
            deflection_not_found = sum(
                1 for r in analysis_results
                if r.get("category") == "Deflection Criteria"
                and r.get("pairs") and self._is_not_found(r["pairs"][0].get("answer", ""))
            )
            if deflection_not_found >= 3:
                return True, "Complex tables detected but poorly extracted"

        return False, "PDF.js results sufficient"

    def _transform_to_analysis_results(self, all_answers: Dict) -> List[Dict]:
        """Transform LLM output to AnalysisResult[] format."""
        results = []
        for i, meta in enumerate(QUESTION_METADATA):
            qid = f"Q{i + 1}"
            answer_data = all_answers.get(qid, {})

            raw_answer = answer_data.get("answer", "Not Found")
            raw_confidence = self._normalize_confidence(
                answer_data.get("_raw_confidence", answer_data.get("confidence", 0)))
            raw_page = answer_data.get("page", "unknown")

            if raw_page and raw_page not in ("unknown", "N/A", ""):
                reference = f"Page {raw_page}" if not str(raw_page).startswith("Page") else str(raw_page)
            else:
                reference = "Not Found"

            results.append({
                "category": meta["category"],
                "question": meta["question"],
                "pairs": [{
                    "answer": raw_answer,
                    "reference": reference,
                    "confidence": raw_confidence,
                    "feedback": "up",
                }],
            })
        return results

    async def process(self, pdf_path: str, context: Dict[str, Any] = None) -> Dict[str, Any]:
        """Extract text from PDF and run LLM to answer engineering questions."""
        if not self.llm_registry:
            raise Exception("LLM Registry not available")

        import asyncio

        pdf_path = str(pdf_path)
        logger.info(f"{self.name}: Processing {Path(pdf_path).name}")

        # Step 1: Extract text
        extracted_text = self._extract_text_from_pdf(pdf_path)
        text_quality = self._analyze_text_quality(extracted_text)

        self.log_decision(
            f"Extracted {text_quality.get('word_count', 0)} words from PDF",
            f"scanned={text_quality.get('is_scanned')}, "
            f"garbage={text_quality.get('garbage_ratio', 0):.2%}",
            decision_type="document_assessment"
        )

        # Early exit for empty/scanned PDFs
        if text_quality.get("is_empty") or text_quality.get("is_scanned"):
            return {
                'success': True,
                'agent': self.name,
                'tier': 1,
                'analysis_results': [],
                'text_quality': text_quality,
                'should_fallback': True,
                'fallback_reason': "Scanned or empty PDF - OCR required",
            }

        # Step 2: Chunk text
        chunks = self._chunk_text(extracted_text, max_chars=80000, overlap=2000)
        MAX_CHUNKS = 5
        if len(chunks) > MAX_CHUNKS:
            chunks = chunks[:3] + chunks[-2:]

        logger.info(f"{self.name}: Processing {len(chunks)} text chunks")

        # Step 3: Process chunks through LLM
        all_answers = {}
        total_questions = len(QUESTION_METADATA)
        no_progress_count = 0
        loop = asyncio.get_event_loop()

        for i, chunk in enumerate(chunks):
            prev_answered = sum(1 for q in range(total_questions)
                                if all_answers.get(f"Q{q+1}", {}).get("_raw_confidence", 0) > 0)
            try:
                answers = await loop.run_in_executor(
                    None,
                    self.llm_registry.answer_questions_with_fallback,
                    chunk,
                    self.questions,
                )
                for key, answer_data in answers.items():
                    if isinstance(answer_data, dict):
                        existing = all_answers.get(key)
                        answer_conf = self._normalize_confidence(answer_data.get("confidence", 0))
                        if not existing or answer_conf > existing.get("_raw_confidence", 0):
                            answer_data["_raw_confidence"] = answer_conf
                            all_answers[key] = answer_data
            except Exception as e:
                logger.error(f"{self.name}: Chunk {i} failed: {e}")

            new_answered = sum(1 for q in range(total_questions)
                               if all_answers.get(f"Q{q+1}", {}).get("_raw_confidence", 0) > 0)

            # Early stop: all questions answered with high confidence
            all_high = sum(1 for q in range(total_questions)
                           if all_answers.get(f"Q{q+1}", {}).get("_raw_confidence", 0) >= 0.8)
            if all_high >= total_questions:
                logger.info(f"{self.name}: Early stop - all questions answered")
                break

            # No-progress stop
            if new_answered <= prev_answered:
                no_progress_count += 1
                if no_progress_count >= 2 and i >= 2:
                    logger.info(f"{self.name}: Early stop - no progress")
                    break
            else:
                no_progress_count = 0

        # Step 4: Transform to AnalysisResult[] format
        analysis_results = self._transform_to_analysis_results(all_answers)

        # Step 5: Check if fallback is needed
        should_fb, reason = self.should_fallback(analysis_results, text_quality)

        self.log_decision(
            f"Tier 1 complete: fallback={'YES' if should_fb else 'NO'}",
            reason,
            decision_type="quality_threshold_met" if not should_fb else "escalation_triggered"
        )

        return {
            'success': True,
            'agent': self.name,
            'tier': 1,
            'analysis_results': analysis_results,
            'text_quality': text_quality,
            'extracted_text': extracted_text,
            'should_fallback': should_fb,
            'fallback_reason': reason,
        }
