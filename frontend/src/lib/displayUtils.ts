/**
 * Display utility functions for transforming internal values to user-facing labels
 * Internal logic may use "Not Found" but UI should always show "Not Available"
 */

/**
 * Transform answer for display - converts "Not Found" to "Not Available"
 */
export function displayAnswer(answer: string | null | undefined): string {
  if (!answer) return "Not Available";
  const trimmed = answer.trim();
  if (trimmed.toLowerCase() === "not found") return "Not Available";
  return trimmed;
}

/**
 * Check if an answer represents a "not available" state
 * Used for conditional logic while keeping internal values unchanged
 */
export function isNotAvailable(answer: string | null | undefined): boolean {
  const answerStr = (answer?.toString().trim().toLowerCase() || '');
  return answerStr === 'not found' || answerStr === 'not available' || answerStr === 'n/a' || answerStr === '';
}

/**
 * Transform answer for export (CSV/JSON) - converts "Not Found" to "Not Available"
 */
export function exportAnswer(answer: string | null | undefined): string {
  if (!answer) return "Not Available";
  const trimmed = answer.trim();
  if (trimmed.toLowerCase() === "not found") return "Not Available";
  return trimmed;
}
