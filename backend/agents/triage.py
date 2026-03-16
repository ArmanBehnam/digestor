# backend/agents/triage.py
"""Document Triage Agent — classifies documents and identifies relevant pages."""

import logging
from typing import Any, Dict, List
from pathlib import Path

from .base import Talk2DrawingsBaseAgent

logger = logging.getLogger(__name__)

# Keywords that indicate page relevance per document type
CATEGORY_KEYWORDS = {
    'structural_drawings': [
        'general notes', 'structural notes', 'design criteria',
        'seismic', 'wind', 'snow', 'load', 'deflection',
        'building code', 'ibc', 'asce', 'aci', 'aisc',
    ],
    'specifications': [
        'section', 'specification', 'division', 'part 1',
        'scope', 'submittals', 'quality assurance',
    ],
    'general_notes': [
        'general notes', 'design criteria', 'abbreviations',
        'symbols', 'legend', 'typical details',
    ],
}

# Classification keywords to determine overall document type
DOC_TYPE_KEYWORDS = {
    'structural_drawings': [
        'S-', 'S1', 'S2', 'structural', 'framing plan',
        'foundation', 'detail', 'elevation', 'section',
    ],
    'specifications': [
        'specification', 'division', 'section 01', 'section 05',
        'part 1', 'part 2', 'part 3',
    ],
    'general_notes': [
        'general notes', 'design criteria', 'abbreviations',
    ],
}


class TriageAgent(Talk2DrawingsBaseAgent):
    """Pre-processes documents before the main pipeline.

    Classifies document type, identifies relevant pages, and estimates
    processing complexity so downstream agents can make better decisions.
    """

    def __init__(self, config: Dict[str, Any] = None, blackboard=None):
        super().__init__("Triage_Agent", blackboard=blackboard)
        self.config = config or {}

    def validate_input(self, input_data: Any) -> bool:
        if isinstance(input_data, (str, Path)):
            return True
        return isinstance(input_data, dict) and 'pdf_path' in input_data

    async def process(self, input_data: Any, context: Dict[str, Any] = None) -> Dict[str, Any]:
        if isinstance(input_data, (str, Path)):
            pdf_path = str(input_data)
        else:
            pdf_path = input_data.get('pdf_path', '')

        if not pdf_path:
            raise ValueError("No pdf_path provided to triage agent")

        doc_type = self.classify_document(pdf_path)
        relevant_pages = self.identify_relevant_pages(pdf_path, doc_type)
        complexity = self.estimate_complexity(pdf_path, doc_type, relevant_pages)

        self.log_decision(
            f"Classified as '{doc_type}', {len(relevant_pages)} relevant pages, "
            f"complexity={complexity['level']}",
            f"Page count and keyword analysis",
            decision_type="document_triage"
        )

        return {
            'success': True,
            'agent': self.name,
            'document_type': doc_type,
            'relevant_pages': relevant_pages,
            'complexity': complexity,
            'recommended_tier': complexity['recommended_tier'],
            'page_scores': relevant_pages,
        }

    def classify_document(self, pdf_path: str) -> str:
        """Classify document type using keyword scanning."""
        try:
            import fitz  # PyMuPDF
        except ImportError:
            logger.warning("PyMuPDF not available, defaulting to 'mixed'")
            return 'mixed'

        scores = {dtype: 0 for dtype in DOC_TYPE_KEYWORDS}

        try:
            doc = fitz.open(pdf_path)
            # Sample first 5 pages and last 2 for classification
            sample_pages = list(range(min(5, len(doc)))) + list(range(max(0, len(doc) - 2), len(doc)))
            sample_pages = sorted(set(sample_pages))

            for page_idx in sample_pages:
                page = doc[page_idx]
                text = page.get_text().lower()
                for dtype, keywords in DOC_TYPE_KEYWORDS.items():
                    for kw in keywords:
                        if kw.lower() in text:
                            scores[dtype] += 1
            doc.close()
        except Exception as e:
            logger.warning(f"Error classifying document: {e}")
            return 'mixed'

        if max(scores.values()) == 0:
            return 'mixed'

        return max(scores, key=scores.get)

    def identify_relevant_pages(self, pdf_path: str, doc_type: str) -> List[Dict[str, Any]]:
        """Score each page by relevance to engineering questions."""
        try:
            import fitz
        except ImportError:
            return []

        # Combine category keywords with engineering-specific terms
        target_keywords = CATEGORY_KEYWORDS.get(doc_type, []) + [
            'wind speed', 'snow load', 'seismic', 'deflection', 'l/',
            'risk category', 'site class', 'sds', 'sd1', 'importance factor',
            'ibc', 'asce 7', 'building code', 'exposure', 'ground snow',
            'dead load', 'live load', 'roof load', 'psf', 'mph', 'ksi',
        ]

        page_scores = []
        try:
            doc = fitz.open(pdf_path)
            for i, page in enumerate(doc):
                text = page.get_text().lower()
                score = 0
                matched_keywords = []
                for kw in target_keywords:
                    if kw.lower() in text:
                        score += 1
                        matched_keywords.append(kw)

                page_scores.append({
                    'page_index': i,
                    'page_number': i + 1,
                    'relevance_score': score,
                    'matched_keywords': matched_keywords[:10],  # cap for serialization
                    'text_length': len(text),
                })
            doc.close()
        except Exception as e:
            logger.warning(f"Error scanning pages: {e}")
            return []

        # Sort by relevance score descending
        page_scores.sort(key=lambda p: p['relevance_score'], reverse=True)
        return page_scores

    def estimate_complexity(self, pdf_path: str, doc_type: str,
                            page_scores: List[Dict]) -> Dict[str, Any]:
        """Estimate processing complexity and recommend a processing tier."""
        try:
            import fitz
            doc = fitz.open(pdf_path)
            page_count = len(doc)
            file_size_mb = Path(pdf_path).stat().st_size / (1024 * 1024)
            doc.close()
        except Exception:
            page_count = len(page_scores) if page_scores else 0
            file_size_mb = 0

        relevant_count = sum(1 for p in page_scores if p.get('relevance_score', 0) > 0)

        # Complexity heuristic
        if page_count <= 5 and file_size_mb < 5:
            level = 'low'
            recommended_tier = 'tier1_fast'  # PDF.js fast path
        elif page_count <= 30 and relevant_count <= 15:
            level = 'medium'
            recommended_tier = 'tier2_standard'  # AWS OCR + LLM
        else:
            level = 'high'
            recommended_tier = 'tier3_deep'  # Full OCR + VLM fallback

        return {
            'level': level,
            'page_count': page_count,
            'file_size_mb': round(file_size_mb, 2),
            'relevant_pages': relevant_count,
            'recommended_tier': recommended_tier,
        }
