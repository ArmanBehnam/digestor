/**
 * Applies confidence override for "Not Available" answers
 * If an answer is "Not Found", "Not Available", "N/A", or empty, and confidence is low,
 * it means we're confident the information doesn't exist - set to 95%
 */
export function normalizeConfidence(answer: string | null | undefined, confidence: number | null | undefined): number {
  const answerStr = (answer?.toString().trim().toLowerCase() || '');
  // Check for both internal "not found" and display "not available"
  const isNotAvailable = answerStr === 'not found' || answerStr === 'not available' || answerStr === 'n/a' || answerStr === '';
  const conf = confidence ?? 0;
  
  // If it's a "Not Available" type answer with low confidence, override to 95%
  // This represents: "I'm 95% confident this information is not in the document"
  if (isNotAvailable && conf < 0.85) {
    return 0.95;
  }
  
  return conf;
}

/**
 * Format confidence as percentage string
 */
export function formatConfidence(answer: string | null | undefined, confidence: number | null | undefined): string {
  const normalizedConfidence = normalizeConfidence(answer, confidence);
  return `${Math.round(normalizedConfidence * 100)}%`;
}
