"""
Vision Language Model engine for Tier 3 processing.
Uses Google Gemini Flash to answer questions from PDF page images
when OCR+LLM (Tier 2) fails to extract enough answers.
"""

import os
import io
import json
import re
import logging
from typing import List, Dict

logger = logging.getLogger(__name__)


class VLMEngine:
    """Gemini Flash VLM for answering engineering questions from page images."""

    def __init__(self):
        self.model_name = "gemini-2.0-flash"
        self.client = None
        self._initialize()

    def _initialize(self):
        api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        if not api_key:
            logger.warning("No GOOGLE_API_KEY or GEMINI_API_KEY found, VLM engine unavailable")
            return
        try:
            import google.generativeai as genai
            genai.configure(api_key=api_key)
            self.client = genai.GenerativeModel(self.model_name)
            logger.info(f"VLM engine initialized: {self.model_name}")
        except ImportError:
            logger.error("google-generativeai package not installed. Run: pip install google-generativeai")
        except Exception as e:
            logger.error(f"VLM engine init failed: {e}")

    @property
    def is_available(self) -> bool:
        return self.client is not None

    def answer_questions_from_images(
        self,
        page_images: List[Dict],
        questions: List[Dict],
        max_pages_per_request: int = 20,
    ) -> List[Dict]:
        """
        Send page images + questions to Gemini, get answers with bounding boxes.

        Args:
            page_images: [{page_number, image_bytes, width, height}]
            questions: [{index, category, question}]
            max_pages_per_request: Max pages to send in a single Gemini call

        Returns: [{index, answer, confidence, reference, bbox}]
        """
        if not self.is_available:
            raise RuntimeError("VLM engine not available")

        if not questions:
            return []

        # If too many pages, batch them
        all_results = []
        for batch_start in range(0, len(page_images), max_pages_per_request):
            batch_images = page_images[batch_start:batch_start + max_pages_per_request]
            batch_results = self._process_batch(batch_images, questions)
            all_results.extend(batch_results)

        # Deduplicate: keep highest confidence per question index
        best_by_index = {}
        for r in all_results:
            idx = r["index"]
            if idx not in best_by_index or r.get("confidence", 0) > best_by_index[idx].get("confidence", 0):
                best_by_index[idx] = r

        return list(best_by_index.values())

    def _process_batch(
        self,
        page_images: List[Dict],
        questions: List[Dict],
    ) -> List[Dict]:
        """Process a batch of page images with all questions."""
        from PIL import Image

        prompt = self._build_prompt(questions)

        # Build content parts: interleave images with page labels
        content_parts = []
        for page_data in page_images:
            img = Image.open(io.BytesIO(page_data["image_bytes"]))
            content_parts.append(img)
            content_parts.append(f"[Page {page_data['page_number']}]")

        content_parts.append(prompt)

        try:
            response = self.client.generate_content(
                content_parts,
                generation_config={
                    "temperature": 0.1,
                    "max_output_tokens": 4096,
                },
            )
            return self._parse_response(response.text, questions)
        except Exception as e:
            logger.error(f"VLM batch processing failed: {e}")
            return []

    def _build_prompt(self, questions: List[Dict]) -> str:
        """Build the VLM prompt for structural engineering document analysis."""
        q_lines = []
        for i, q in enumerate(questions):
            q_lines.append(f"{i + 1}. [{q['category']}] {q['question']}")
        q_text = "\n".join(q_lines)

        return f"""You are an expert structural engineering document analyzer.
Examine these PDF page images carefully and answer ONLY the following questions that could not be answered by text extraction.

Questions:
{q_text}

For each question you can find an answer for, provide it in this exact JSON format:
```json
{{
  "answers": [
    {{
      "question_index": <0-based index from the question list above>,
      "answer": "<precise answer value>",
      "confidence": <0-100 integer>,
      "page": <page number where the answer was found>,
      "bbox": {{
        "x": <normalized 0.0-1.0 x coordinate of answer location on the page>,
        "y": <normalized 0.0-1.0 y coordinate>,
        "width": <normalized 0.0-1.0 width of the answer region>,
        "height": <normalized 0.0-1.0 height of the answer region>
      }}
    }}
  ]
}}
```

Important rules:
- Only answer questions where you can clearly find the information in the images
- For values like wind speed, snow load, etc., include the units
- Bounding box coordinates should be normalized to 0.0-1.0 range relative to the page dimensions
- The bbox should encompass the text region where the answer is found
- Confidence: 90+ for clearly visible values, 70-89 for values requiring interpretation, below 70 for uncertain
- If you cannot find an answer, do NOT include it in the response
- Return ONLY the JSON, no additional text"""

    def _parse_response(self, response_text: str, questions: List[Dict]) -> List[Dict]:
        """Parse Gemini's JSON response into structured results."""
        try:
            # Extract JSON from response (may be wrapped in markdown code block)
            json_match = re.search(r'\{[\s\S]*\}', response_text)
            if not json_match:
                logger.warning("No JSON found in VLM response")
                return []

            data = json.loads(json_match.group())
            results = []

            for ans in data.get("answers", []):
                q_idx = ans.get("question_index")
                if q_idx is None or q_idx >= len(questions):
                    continue

                # Map back to original index in the full analysis_results array
                original_index = questions[q_idx]["index"]
                answer_text = ans.get("answer", "").strip()

                if not answer_text or answer_text.lower() in ("not found", "n/a", "not available"):
                    continue

                result = {
                    "index": original_index,
                    "answer": answer_text,
                    "confidence": min(ans.get("confidence", 0) / 100.0, 1.0),
                    "reference": f"Page {ans.get('page', 'N/A')}",
                }

                # Add bbox if provided
                bbox = ans.get("bbox")
                if bbox and all(k in bbox for k in ("x", "y", "width", "height")):
                    result["bbox"] = {
                        "x": round(float(bbox["x"]), 4),
                        "y": round(float(bbox["y"]), 4),
                        "width": round(float(bbox["width"]), 4),
                        "height": round(float(bbox["height"]), 4),
                    }

                results.append(result)

            logger.info(f"VLM parsed {len(results)} answers from Gemini response")
            return results

        except json.JSONDecodeError as e:
            logger.error(f"VLM response JSON parse failed: {e}")
            return []
        except Exception as e:
            logger.error(f"VLM response parse failed: {e}")
            return []
