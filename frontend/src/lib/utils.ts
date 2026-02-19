import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

interface DeflectionRule {
  Description: string;
  Combination: string;
  LimitRatio: string | null;
  Max: string | null;
}

export function normalizeDeflectionCriteria(extractedAnswer: string): string {
  // Handle both internal "Not Found" and display "Not Available"
  if (extractedAnswer === "Not Found" || extractedAnswer === "Not Available" || !extractedAnswer) {
    return extractedAnswer;
  }

  try {
    // Split by common delimiters: semicolon, period followed by capital, multiple spaces
    const sentences = extractedAnswer
      .split(/[;]|(?:\.\s+(?=[A-Z]))/)
      .map(s => s.trim())
      .filter(s => s.length > 5); // Filter out very short fragments

    const rules: DeflectionRule[] = [];

    for (let sentence of sentences) {
      // Handle multiple conditions in one sentence separated by "and", "or", commas followed by keywords or ratio patterns
      const subConditions = sentence.split(/\s+and\s+|\s+or\s+|\s*,\s*(?=(?:maximum|for|under|with|L\/|l\/|span\/|1\/))/i);
      
      for (const condition of subConditions) {
        if (condition.trim().length < 5) continue;
        
        // Extract ALL LimitRatios from this condition first
        const ratioMatches = [...condition.matchAll(/(?:span|1|l|L)\/(\d+)/gi)];
        
        // Base rule properties (shared across all ratios in this condition)
        let description = "general deflection limit";
        let combination = "None";
        let max: string | null = null;

        // Extract Description (full phrase after "for")
        const forMatch = condition.match(/for\s+(.+?)(?:\s*[;.]|$)/i);
        if (forMatch) {
          description = "for " + forMatch[1].trim();
        } else if (/vertical\s+deflection/i.test(condition)) {
          description = "vertical deflection";
        } else if (/horizontal\s+deflection/i.test(condition)) {
          description = "horizontal deflection";
        } else if (/story\s+drift/i.test(condition)) {
          description = "story drift";
        }

        // Detect Combination (order matters - check most specific first)
        if (/horizontal\s+load\s+(?:of\s+)?(?:\()?(\d+)\s*psf/i.test(condition) || 
            /lateral\s+load\s+(?:of\s+)?(?:\()?(\d+)\s*psf/i.test(condition)) {
          combination = "W";
        } else if (/\bwind\b/i.test(condition) || /\bW\b/.test(condition) || /wind\s+load/i.test(condition)) {
          combination = "W";
        } else if (/\bsnow\b/i.test(condition) || /\bS\b/.test(condition) || /snow\s+load/i.test(condition)) {
          combination = "S";
        } else if (/roof\s+live\s+load/i.test(condition) || /\bLr\b/.test(condition)) {
          combination = "Lr";
        } else if (/\blive\s+load\b/i.test(condition) && !/roof/i.test(condition)) {
          combination = "L";
        } else if (/dead\s*\+\s*live/i.test(condition) || /D\s*\+\s*L\b/.test(condition)) {
          combination = "D+L";
        } else if (/dead\s*\+\s*roof\s+live/i.test(condition) || /D\s*\+\s*Lr\b/.test(condition)) {
          combination = "D+Lr";
        } else if (/dead\s+load/i.test(condition) || /\bD\b/.test(condition)) {
          combination = "D";
        }

        // Extract Max (absolute limits like "1/2 inch", "3/4 inch", "1.0 inch", etc.)
        const maxMatch = condition.match(/(?:not\s+more\s+than|maximum|max\.?|but\s+not\s+(?:to\s+)?exceed(?:ing)?)\s+([\d./]+\s*inch(?:es)?|\d+\.?\d*\s*inch(?:es)?)/i);
        if (maxMatch) {
          let maxValue = maxMatch[1].trim();
          // Normalize common fraction formats
          maxValue = maxValue.replace(/\s+/g, ' ');
          max = maxValue;
        }

        // If multiple ratios found, create separate rules for each
        if (ratioMatches.length > 1) {
          for (const match of ratioMatches) {
            const rule: DeflectionRule = {
              Description: description,
              Combination: combination,
              LimitRatio: `L/${match[1]}`,
              Max: max
            };
            rules.push(rule);
          }
        } else if (ratioMatches.length === 1) {
          // Single ratio found
          const rule: DeflectionRule = {
            Description: description,
            Combination: combination,
            LimitRatio: `L/${ratioMatches[0][1]}`,
            Max: max
          };
          rules.push(rule);
        } else if (max !== null || combination !== "None") {
          // No ratio but has max or combination - still add the rule
          const rule: DeflectionRule = {
            Description: description,
            Combination: combination,
            LimitRatio: null,
            Max: max
          };
          rules.push(rule);
        }
      }
    }

    // If no rules extracted, return original
    if (rules.length === 0) {
      return extractedAnswer;
    }

    // Return as formatted JSON string
    return JSON.stringify(rules, null, 2);
  } catch (error) {
    console.error("Error normalizing deflection criteria:", error);
    return extractedAnswer;
  }
}
