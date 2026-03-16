# backend/agents/memory.py
"""Memory Agent — learns from past document processing to improve future runs."""

import hashlib
import json
import logging
import os
from typing import Any, Dict, List, Optional

from .base import Talk2DrawingsBaseAgent

logger = logging.getLogger(__name__)

# TTL for memory entries (seconds) — default 30 days
DEFAULT_MEMORY_TTL = 30 * 24 * 60 * 60


class MemoryAgent(Talk2DrawingsBaseAgent):
    """Agent that maintains processing memory across documents.

    Uses Redis (if available) to store what OCR/LLM strategies worked
    for similar documents, enabling smarter defaults on future runs.
    """

    REDIS_PREFIX = "digestor:memory:"

    def __init__(self, config: Dict[str, Any] = None, blackboard=None):
        super().__init__("Memory_Agent", blackboard=blackboard)
        self.config = config or {}
        self.memory_ttl = self.config.get('memory_ttl', DEFAULT_MEMORY_TTL)
        self._redis = None

    @property
    def redis(self):
        """Lazy Redis connection."""
        if self._redis is None:
            try:
                import redis as redis_lib
                redis_url = os.environ.get(
                    'REDIS_URL',
                    self.config.get('redis_url', 'redis://localhost:6379/0')
                )
                self._redis = redis_lib.from_url(redis_url, decode_responses=True)
                self._redis.ping()
                logger.info("Memory Agent connected to Redis")
            except Exception as e:
                logger.warning(f"Redis unavailable for Memory Agent: {e}")
                self._redis = None
        return self._redis

    def validate_input(self, input_data: Any) -> bool:
        return isinstance(input_data, dict)

    async def process(self, input_data: Dict[str, Any], context: Dict[str, Any] = None) -> Dict[str, Any]:
        """Look up past strategies for similar documents."""
        doc_info = input_data.get('document_info', input_data)
        fingerprint = self.fingerprint_document(doc_info)

        suggestions = self.suggest_strategy(fingerprint, doc_info)

        if suggestions.get('no_prior_knowledge'):
            self.log_decision(
                "No prior knowledge for this document type",
                f"fingerprint={fingerprint[:16]}...",
                decision_type="memory_lookup"
            )
        else:
            self.log_decision(
                f"Found prior strategy: OCR={suggestions.get('suggested_ocr', 'N/A')}, "
                f"LLM={suggestions.get('suggested_llm', 'N/A')}",
                f"Matched {suggestions.get('match_count', 0)} similar docs",
                decision_type="memory_lookup"
            )

        return {
            'success': True,
            'agent': self.name,
            'fingerprint': fingerprint,
            'suggestions': suggestions,
        }

    def fingerprint_document(self, doc_info: Dict[str, Any]) -> str:
        """Create a content-based fingerprint for similarity matching."""
        parts = []
        # Page count bucket: 1-5, 6-20, 21-50, 50+
        page_count = doc_info.get('page_count', doc_info.get('total_pages', 0))
        if page_count <= 5:
            parts.append('pages:small')
        elif page_count <= 20:
            parts.append('pages:medium')
        elif page_count <= 50:
            parts.append('pages:large')
        else:
            parts.append('pages:xlarge')

        # Document type
        doc_type = doc_info.get('document_type', doc_info.get('type', 'unknown'))
        parts.append(f'type:{doc_type}')

        # Top keywords (sorted for determinism)
        keywords = doc_info.get('keywords', doc_info.get('matched_keywords', []))
        if isinstance(keywords, list):
            top_kw = sorted(set(kw.lower() for kw in keywords[:20]))
            parts.append(f'kw:{",".join(top_kw[:10])}')

        fingerprint_str = "|".join(parts)
        return hashlib.sha256(fingerprint_str.encode()).hexdigest()

    def suggest_strategy(self, fingerprint: str, doc_info: Dict[str, Any]) -> Dict[str, Any]:
        """Look up past successful strategies for similar documents."""
        if not self.redis:
            return {'no_prior_knowledge': True}

        try:
            # Exact fingerprint match
            key = f"{self.REDIS_PREFIX}{fingerprint}"
            data = self.redis.get(key)
            if data:
                entry = json.loads(data)
                return {
                    'suggested_ocr': entry.get('best_ocr'),
                    'suggested_llm': entry.get('best_llm'),
                    'known_patterns': entry.get('patterns', {}),
                    'prior_confidence': entry.get('confidence_avg', 0),
                    'match_type': 'exact',
                    'match_count': 1,
                }

            # Fuzzy: scan for similar fingerprints (same page bucket + type)
            similar = self.find_similar_documents(doc_info)
            if similar:
                best = similar[0]
                return {
                    'suggested_ocr': best.get('best_ocr'),
                    'suggested_llm': best.get('best_llm'),
                    'known_patterns': best.get('patterns', {}),
                    'prior_confidence': best.get('confidence_avg', 0),
                    'match_type': 'similar',
                    'match_count': len(similar),
                }
        except Exception as e:
            logger.warning(f"Memory lookup failed: {e}")

        return {'no_prior_knowledge': True}

    def find_similar_documents(self, doc_info: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Find documents with similar characteristics in memory store."""
        if not self.redis:
            return []

        try:
            # Scan for all memory entries and score by keyword overlap
            cursor = 0
            results = []
            doc_keywords = set(
                kw.lower() for kw in
                doc_info.get('keywords', doc_info.get('matched_keywords', []))[:20]
            )

            while True:
                cursor, keys = self.redis.scan(
                    cursor, match=f"{self.REDIS_PREFIX}*", count=50
                )
                for key in keys:
                    try:
                        data = self.redis.get(key)
                        if data:
                            entry = json.loads(data)
                            entry_kw = set(entry.get('keywords', []))
                            if doc_keywords and entry_kw:
                                # Jaccard similarity
                                intersection = doc_keywords & entry_kw
                                union = doc_keywords | entry_kw
                                similarity = len(intersection) / len(union) if union else 0
                                if similarity > 0.3:
                                    entry['similarity'] = similarity
                                    results.append(entry)
                    except Exception:
                        continue
                if cursor == 0:
                    break

            results.sort(key=lambda x: x.get('similarity', 0), reverse=True)
            return results[:5]
        except Exception as e:
            logger.warning(f"Similar document search failed: {e}")
            return []

    def learn_from_result(self, doc_info: Dict[str, Any],
                          processing_result: Dict[str, Any]) -> bool:
        """Store what worked for this document type."""
        if not self.redis:
            return False

        fingerprint = self.fingerprint_document(doc_info)
        keywords = doc_info.get('keywords', doc_info.get('matched_keywords', []))

        entry = {
            'fingerprint': fingerprint,
            'best_ocr': processing_result.get('ocr_engine_used',
                        processing_result.get('ocr_strategy', {}).get('primary', 'unknown')),
            'best_llm': processing_result.get('llm_used', 'unknown'),
            'confidence_avg': processing_result.get('confidence_avg',
                              processing_result.get('qa_confidence', 0)),
            'patterns': processing_result.get('answer_patterns', {}),
            'keywords': [kw.lower() for kw in keywords[:20]] if isinstance(keywords, list) else [],
            'page_count': doc_info.get('page_count', doc_info.get('total_pages', 0)),
            'document_type': doc_info.get('document_type', 'unknown'),
        }

        try:
            key = f"{self.REDIS_PREFIX}{fingerprint}"
            self.redis.setex(key, self.memory_ttl, json.dumps(entry))
            self.log_decision(
                f"Stored processing result for fingerprint {fingerprint[:16]}...",
                f"OCR={entry['best_ocr']}, LLM={entry['best_llm']}, conf={entry['confidence_avg']}",
                decision_type="memory_store"
            )
            return True
        except Exception as e:
            logger.warning(f"Failed to store memory: {e}")
            return False
