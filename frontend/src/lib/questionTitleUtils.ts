/**
 * Transforms question titles to match UI cleanQuestionText logic from ResultsDisplay.tsx:
 * 1. Question 1 becomes "Building Code & Year"
 * 2. Removes "What is the", "What are the" prefixes
 * 3. Applies Title Case with preserved abbreviations (SDS, SD1, Ip, Ie, Pf, Ct, Ce, Is, Pg, Vult, GCpi, ASCE)
 * 4. Removes "?" marks except for question 2
 */
export function formatQuestionTitle(questionText: string, questionId?: number): string {
  if (!questionText) return '';
  
  // Special handling for question 1 (Building Code)
  if (questionId === 1) {
    return 'Building Code & Year';
  }
  if (questionText.toLowerCase().includes('building code') && 
      questionText.toLowerCase().includes('version year')) {
    return 'Building Code & Year';
  }
  
  // Remove "What is the" or "What are the" prefix
  let cleaned = questionText
    .replace(/^What is the\s+/i, '')
    .replace(/^What are the\s+/i, '');
  
  // List of abbreviations to preserve in original case
  const preservedWords = ['SDS', 'SD1', 'Ip', 'Ie', 'Pf', 'Ct', 'Ce', 'Is', 'Pg', 'Vult', 'GCpi', 'ASCE'];
  
  // Split into words and capitalize each word (Title Case)
  const words = cleaned.split(/\s+/);
  const capitalizedWords = words.map(word => {
    // Check if this word (case-insensitive) is in the preserved list
    const matchedPreserved = preservedWords.find(
      preserved => word.toLowerCase() === preserved.toLowerCase()
    );
    
    if (matchedPreserved) {
      return matchedPreserved;
    }
    
    // Otherwise capitalize first letter, lowercase the rest
    if (word.length === 0) return word;
    return word.charAt(0).toUpperCase() + word.slice(1).toLowerCase();
  });
  
  let result = capitalizedWords.join(' ');
  
  // Remove "?" from the end, except for question 2 (deflection criteria)
  if (questionId !== 2 && result.endsWith('?')) {
    result = result.slice(0, -1);
  }
  
  return result;
}
