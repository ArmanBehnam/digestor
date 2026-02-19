"""
PDF.js fast-path processing.
Takes browser-extracted text and runs it through the LLM registry directly (no worker queue).

Returns results in the AnalysisResult[] format expected by the frontend:
[
  {
    "category": "Building Code",
    "question": "What is the building code and its version year?",
    "pairs": [
      {
        "answer": "IBC 2021",
        "reference": "Page 1",
        "confidence": 0.95,
        "feedback": "up"
      }
    ]
  },
  ...
]
"""

import asyncio
import structlog
from typing import Optional

from llm.llm_engines.llm_registry import LLMRegistry
from config.config_loader import load_config

logger = structlog.get_logger()

# Load engineering questions from config
config = load_config()
QUESTIONS = config.get("questions", [])

# Question-to-category mapping matching the frontend's QUESTIONS array
# Each entry maps Q index (0-based) to {category, question} matching the Supabase original
QUESTION_METADATA = [
    # Building Code (Q1-Q2)
    {"category": "Building Code", "question": "What is the building code and its version year?"},
    {"category": "Building Code", "question": "Is ASCE 7-XX referred?"},
    # Deflection Criteria (Q3-Q8)
    {"category": "Deflection Criteria", "question": "What are the exterior wall deflection limits?"},
    {"category": "Deflection Criteria", "question": "What is the interior wall deflection limit?"},
    {"category": "Deflection Criteria", "question": "What is the floor joist framing deflection limit?"},
    {"category": "Deflection Criteria", "question": "What is the roof rafter framing deflection limit?"},
    {"category": "Deflection Criteria", "question": "What is the ceiling joist framing deflection limit?"},
    {"category": "Deflection Criteria", "question": "Maximum primary structure vertical deflection due to live load?"},
    # Wind Load Criteria (Q9-Q12)
    {"category": "Wind Load Criteria", "question": "What is the basic wind speed (Vult)?"},
    {"category": "Wind Load Criteria", "question": "What is the building risk category?"},
    {"category": "Wind Load Criteria", "question": "What is the exposure category?"},
    {"category": "Wind Load Criteria", "question": "What is the internal pressure coefficient (GCpi)?"},
    # Gravity Loads (Q13-Q14)
    {"category": "Gravity Loads", "question": "What is the roof live load?"},
    {"category": "Gravity Loads", "question": "What is the roof dead load?"},
    # Snow Load Criteria (Q15-Q19)
    {"category": "Snow Load Criteria", "question": "What is the ground snow load (Pg)?"},
    {"category": "Snow Load Criteria", "question": "What is the snow load importance factor (Is)?"},
    {"category": "Snow Load Criteria", "question": "What is the snow exposure factor (Ce)?"},
    {"category": "Snow Load Criteria", "question": "What is the thermal factor (Ct)?"},
    {"category": "Snow Load Criteria", "question": "What is the flat roof snow load (Pf)?"},
    # Seismic Load Criteria (Q20-Q25)
    {"category": "Seismic Load Criteria", "question": "What is the seismic design category?"},
    {"category": "Seismic Load Criteria", "question": "What is the seismic importance factor (Ie)?"},
    {"category": "Seismic Load Criteria", "question": "What is the component importance factor (Ip)?"},
    {"category": "Seismic Load Criteria", "question": "What is the site class?"},
    {"category": "Seismic Load Criteria", "question": "What is the SDS value?"},
    {"category": "Seismic Load Criteria", "question": "What is the SD1 value?"},
]


async def run_pdfjs_processing(
    extracted_text: str,
    text_positions: Optional[list] = None,
    doc_id: str = "",
) -> tuple[list, dict]:
    """
    Process extracted text through LLM to answer engineering questions.

    Uses the existing LLMRegistry.answer_questions_with_fallback() which is
    synchronous, so we run it in a thread executor.

    Returns:
        (results: list[dict], text_quality: dict)
        results is in AnalysisResult[] format: [{category, question, pairs: [{answer, reference, confidence, feedback}]}]
    """
    logger.info("pdfjs_processing_start", doc_id=doc_id, text_len=len(extracted_text))

    # Analyze text quality
    text_quality = _analyze_text_quality(extracted_text)

    # If text is too short or garbage, return early
    if text_quality.get("is_empty", False):
        return [], {"is_empty": True, "garbage_ratio": 1.0}

    # Chunk text for LLM processing
    chunks = _chunk_text(extracted_text, max_chars=40000, overlap=2000)
    logger.info("pdfjs_chunks_created", doc_id=doc_id, chunk_count=len(chunks))

    # Process each chunk through LLM using the existing registry
    llm_registry = LLMRegistry(config)
    # Best answer per question key (Q1, Q2, ...) across all chunks
    all_answers = {}

    for i, chunk in enumerate(chunks):
        try:
            # answer_questions_with_fallback is synchronous — run in executor
            loop = asyncio.get_event_loop()
            answers = await loop.run_in_executor(
                None,
                llm_registry.answer_questions_with_fallback,
                chunk,
                QUESTIONS,
            )

            # answers is Dict[str, Dict[str, Any]] like {"Q1": {"answer": ..., "confidence": ..., "page": ..., "source": ...}, ...}
            for key, answer_data in answers.items():
                if isinstance(answer_data, dict):
                    existing = all_answers.get(key)
                    answer_conf = _normalize_confidence(answer_data.get("confidence", 0))
                    if not existing or answer_conf > existing.get("_raw_confidence", 0):
                        answer_data["_raw_confidence"] = answer_conf
                        all_answers[key] = answer_data

        except Exception as e:
            logger.error("pdfjs_chunk_failed", doc_id=doc_id, chunk=i, error=str(e))

    # Transform LLM output into AnalysisResult[] format
    results = _transform_to_analysis_results(all_answers)

    logger.info(
        "pdfjs_processing_complete",
        doc_id=doc_id,
        answers_found=len(results),
    )

    return results, text_quality


def _normalize_confidence(conf) -> float:
    """
    Normalize confidence to 0.0-1.0 scale.
    LLM engines return confidence as int 0-100. Convert to 0.0-1.0.
    """
    if isinstance(conf, str):
        try:
            conf = float(conf)
        except (ValueError, TypeError):
            return 0.0
    if isinstance(conf, (int, float)):
        if conf > 1.0:
            # It's on 0-100 scale, convert to 0.0-1.0
            return min(conf / 100.0, 1.0)
        return max(0.0, min(float(conf), 1.0))
    return 0.0


def _transform_to_analysis_results(all_answers: dict) -> list:
    """
    Transform LLM output (keyed by Q1, Q2, ...) into AnalysisResult[] format
    expected by the frontend.

    Input:  {"Q1": {"answer": "IBC 2021", "confidence": 95, "page": "1", "source": "openai_gpt4o"}, ...}
    Output: [{"category": "Building Code", "question": "...", "pairs": [{"answer": "...", "reference": "...", "confidence": 0.95}]}, ...]
    """
    results = []

    for i, meta in enumerate(QUESTION_METADATA):
        qid = f"Q{i + 1}"
        answer_data = all_answers.get(qid, {})

        raw_answer = answer_data.get("answer", "Not Found")
        raw_confidence = _normalize_confidence(answer_data.get("_raw_confidence", answer_data.get("confidence", 0)))
        raw_page = answer_data.get("page", "unknown")
        source = answer_data.get("source", "")

        # Format reference like the Supabase version: "filename.pdf, Page X" or "Page X"
        if raw_page and raw_page not in ("unknown", "N/A", ""):
            reference = f"Page {raw_page}" if not str(raw_page).startswith("Page") else str(raw_page)
        else:
            reference = "Not Found"

        results.append({
            "category": meta["category"],
            "question": meta["question"],
            "pairs": [
                {
                    "answer": raw_answer,
                    "reference": reference,
                    "confidence": raw_confidence,
                    "feedback": "up",  # Default "Like by Default" workflow matching Supabase behavior
                }
            ],
        })

    return results


def _analyze_text_quality(text: str) -> dict:
    """Analyze extracted text for quality indicators."""
    if not text or len(text.strip()) < 50:
        return {"is_empty": True, "garbage_ratio": 1.0, "is_scanned": True}

    total_chars = len(text)
    # Count non-printable / garbage characters
    garbage_chars = sum(1 for c in text if ord(c) > 127 and not c.isalpha())
    garbage_ratio = garbage_chars / total_chars if total_chars > 0 else 0

    # Detect scanned PDFs (very low text extraction)
    words = text.split()
    is_scanned = len(words) < 50

    # Detect complex tables (lots of pipe/tab characters)
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


def _chunk_text(text: str, max_chars: int = 40000, overlap: int = 2000) -> list[str]:
    """Split text into overlapping chunks."""
    if len(text) <= max_chars:
        return [text]

    chunks = []
    start = 0
    while start < len(text):
        end = start + max_chars
        # Try to break at paragraph boundary
        if end < len(text):
            newline_pos = text.rfind("\n\n", start + max_chars - overlap, end)
            if newline_pos > start:
                end = newline_pos
        chunks.append(text[start:end])
        start = end - overlap

    return chunks
