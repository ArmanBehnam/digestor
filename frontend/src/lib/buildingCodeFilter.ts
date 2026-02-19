/**
 * Building Code Filter Utility
 * 
 * For Question 1 (Building Code & Year), applies HARD filtering rules:
 * - Only allows IBC or State/City Building Codes WITH a year
 * - Completely excludes all other codes (NEC, IFC, IFGC, ICC/ANSI, etc.)
 * 
 * This filter should be applied:
 * 1. At extraction time (backend) - primary filter
 * 2. At display time (frontend) - safety net for old data
 * 3. At export time (CSV/JSON) - ensure clean exports
 */

// HARD BLACKLIST - These codes must NEVER appear for Question 1
const BLACKLIST_PATTERNS = [
  // Electrical codes
  /\bN\.?E\.?C\.?\b/i,
  /\bNational\s*Electrical\s*Code\b/i,
  /\bElectric(al)?\s*Code\b/i,
  /\bArticle\s*\d+/i, // NEC Article references
  /\bNFPA\s*70\b/i,
  // Fire codes
  /\bIFC\b/i,
  /\bInternational\s*Fire\s*Code\b/i,
  /\bFire\s*Code\b/i,
  // Fuel gas codes
  /\bIFGC\b/i,
  /\bInternational\s*Fuel\s*Gas\s*Code\b/i,
  /\bFuel\s*Gas\s*Code\b/i,
  // Accessibility codes
  /\bICC\s*\/?\s*ANSI\b/i,
  /\bICC\s*A\s*117/i,
  /\bA\s*117\.?1?\b/i,
  /\bAccessibility\s*Code\b/i,
  /\bADA\b/i,
  // Other specialty codes
  /\bNFPA\b/i,
  /\bANSI\b/i,
  /\bIRC\b/i, // Residential
  /\bIEBC\b/i, // Existing Building
  /\bIECC\b/i, // Energy
  /\bIPC\b/i, // Plumbing
  /\bIMC\b/i, // Mechanical
  /\bIPMC\b/i, // Property Maintenance
  /\bIWUIC\b/i, // Wildland-Urban Interface
  /\bResidential\s*Code\b/i,
  /\bPlumbing\s*Code\b/i,
  /\bMechanical\s*Code\b/i,
  /\bEnergy\s*Code\b/i,
  /\bExisting\s*Building\s*Code\b/i,
  /\bProperty\s*Maintenance\b/i,
];

// WHITELIST - Only these building code patterns are allowed
const WHITELIST_PATTERN = /\b(IBC|International\s*Building\s*Code|Building\s*Code|SBC|NYSBC|NYCBC|NYBC|CBC|NBC|UBC|MBC|OBC|TBC|FBC|Chicago\s*Building\s*Code|California\s*Building\s*Code|NYC\s*Building\s*Code|New\s*York\s*(City\s*)?Building\s*Code)\b/i;

// Year pattern - must have a 4-digit year (19XX or 20XX)
const YEAR_PATTERN = /\b(19|20)\d{2}\b/;

/**
 * Check if an answer is a valid building code for Question 1
 * Returns true if the answer should be KEPT, false if it should be FILTERED OUT
 */
export function isValidBuildingCodeAnswer(answer: string | null | undefined): boolean {
  if (!answer) return false;
  
  const trimmed = answer.trim();
  
  // Skip empty or "Not Found"/"Not Available" answers
  if (!trimmed || trimmed.toLowerCase() === 'not found' || trimmed.toLowerCase() === 'not available') {
    return false;
  }
  
  // Check blacklist FIRST - if matches any blacklist pattern, REJECT
  const isBlacklisted = BLACKLIST_PATTERNS.some(pattern => pattern.test(trimmed));
  if (isBlacklisted) {
    return false;
  }
  
  // Check whitelist - must match a valid building code pattern
  const hasValidBuildingCode = WHITELIST_PATTERN.test(trimmed);
  if (!hasValidBuildingCode) {
    return false;
  }
  
  // Check for year - must have a valid 4-digit year
  const hasYear = YEAR_PATTERN.test(trimmed);
  if (!hasYear) {
    return false;
  }
  
  // Check if answer is JUST a year (reject those)
  const isJustYear = /^(19|20)\d{2}$/.test(trimmed);
  if (isJustYear) {
    return false;
  }
  
  // Passed all checks - this is a valid building code answer
  return true;
}

/**
 * Filter an array of answer pairs for Question 1
 * Removes all invalid building code answers completely
 */
export function filterBuildingCodePairs<T extends { answer: string }>(pairs: T[]): T[] {
  return pairs.filter(pair => isValidBuildingCodeAnswer(pair.answer));
}

/**
 * Check if this is Question 1 (Building Code question)
 */
export function isQuestion1(questionIndex: number, question?: string): boolean {
  // Question 1 is index 0 (zero-based) or question ID 1
  if (questionIndex === 0) return true;
  
  // Also check by question text if available
  if (question) {
    const lowerQuestion = question.toLowerCase();
    return lowerQuestion.includes('building code') && 
           (lowerQuestion.includes('version year') || lowerQuestion.includes('what is'));
  }
  
  return false;
}
