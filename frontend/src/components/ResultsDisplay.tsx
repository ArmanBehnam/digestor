import { Download, ThumbsUp, ThumbsDown, Trash2, CheckCircle, Send, Pencil, Check, X, ChevronsUpDown, RotateCcw, Save, FileText, LogOut } from "lucide-react";
import { VerificationCheckmark } from "./VerificationCheckmark";
import { displayAnswer } from "@/lib/displayUtils";
import { isValidBuildingCodeAnswer } from "@/lib/buildingCodeFilter";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useState, useMemo, useEffect, useRef, useCallback } from "react";
import { Chatbot } from "./Chatbot";
import { PDFViewerWithAnnotations, PDFHighlight } from "./PDFViewerWithAnnotations";
import { ProjectNotes } from "./ProjectNotes";
import { UnsavedChangesDialog } from "./UnsavedChangesDialog";
import apiClient from "@/lib/apiClient";
import { useAuth } from "@/hooks/useAuth";
import { useToast } from "@/hooks/use-toast";
import { useUnsavedChangesProtection, useAutosaveOnVisibilityChange } from "@/hooks/useReviewDirtyState";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { formatConfidence } from "@/lib/confidenceUtils";
import { formatProcessedTime } from "@/lib/timeUtils";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { normalizeDeflectionCriteria } from "@/lib/utils";
import { DeflectionCriteriaEditor } from "./DeflectionCriteriaEditor";
import { PDFSourceCarousel } from "./PDFSourceCarousel";
import { usePdfBroadcastChannel } from "@/hooks/usePdfBroadcastChannel";
import { sendDirectMessage } from "@/lib/pdfPopoutRegistry";
import { 
  buildStructuredReference, 
  waitForPdfReady, 
  jumpToPdfLocation as executeJumpToPdfLocation,
  StructuredReference 
} from "@/lib/referenceNavigation";

import { EditNoteIndicator } from "./EditNoteIndicator";
import { RemarksColumn } from "./RemarksColumn";

export interface AnswerReferencePair {
  answer: string;
  reference: string;
  confidence?: number;
  feedback?: "up" | "down" | null;
  normalizedAnswer?: string;
  unit?: string;
  originalAnswer?: string;
  originalNormalizedAnswer?: string;
  is_edited?: boolean;
  last_edited_by_full_name?: string;
  last_edited_at?: string;
  last_edited_changes?: {
    "Extracted Answer"?: { old: string | null; new: string | null };
    "Normalized Answer"?: { old: string | null; new: string | null };
    "Unit"?: { old: string | null; new: string | null };
  };
  bbox?: {
    x: number;
    y: number;
    width: number;
    height: number;
  };
  excluded?: boolean;
  excluded_by?: string;
  excluded_at?: string;
  restored_by?: string;
  restored_at?: string;
  is_selected?: boolean;
  deleted?: boolean;
  deleted_by?: string;
  deleted_at?: string;
  // Not Applicable / Hide Question feature
  is_not_applicable?: boolean;
  not_applicable_by?: string;
  not_applicable_at?: string;
  not_applicable_restored_by?: string;
  not_applicable_restored_at?: string;
}

export interface AnalysisResult {
  category: string;
  question: string;
  pairs: AnswerReferencePair[];
}

interface ResultsDisplayProps {
  results: AnalysisResult[];
  projectId: string;
  projectName: string;
  processingTimeSeconds: number;
  processingTimeMinutes?: number; // Direct calculated value in minutes
  processingRecordId: string;
  projectHash: string;
  filesMetadata?: Array<{ name: string; path: string; size: number; type: string }>;
  onProjectIdChange: (value: string) => void;
  onProjectNameChange: (value: string) => void;
  onExportCSV: () => void;
  onExportJSON: () => void;
  onUpdateAnswer: (resultIndex: number, pairIndex: number, newAnswer: string) => void;
  onUpdateNormalizedAnswer: (resultIndex: number, pairIndex: number, newAnswer: string) => void;
  onUpdateFeedback: (resultIndex: number, pairIndex: number, feedback: "up" | "down" | null) => void;
  onDeleteAnswer: (resultIndex: number, pairIndex: number) => void;
  onSelectAnswer: (resultIndex: number, pairIndex: number) => void;
  onExcludeAnswer: (resultIndex: number, pairIndex: number, currentUser: any) => void;
  onIncludeAnswer: (resultIndex: number, pairIndex: number, currentUser: any) => void;
  onMarkNotApplicable?: (resultIndex: number) => void; // Mark entire question as N/A
  onRestoreApplicable?: (resultIndex: number) => void; // Restore question from N/A
  hideSubmitButton?: boolean; // Hide Submit button in supervisor review mode
  persistEditsLocally?: boolean; // When false, skip DB persistence + note dialog (parent handles it)
  externalEditHistory?: Record<string, any[]>; // External edit history from parent (SupervisorReview)
  onSubmitSuccess?: () => void; // Callback for post-submit navigation
  onDirtyStateChange?: (isDirty: boolean) => void; // Callback when dirty state changes
  onSaveCallback?: (saveFn: () => Promise<void>) => void; // Callback to expose save function to parent
  onSaveAndExit?: () => void; // Callback to navigate home after saving
}

// Loading state tracking for feedback buttons
interface FeedbackLoadingState {
  [key: string]: boolean; // key format: "resultIndex-pairIndex-action"
}

export const normalizeAnswer = (answer: string, questionId: number): string => {
  // Keep internal "Not Found" value unchanged for logic consistency
  if (answer === "Not Found" || answer === "Not Available") return answer;
  
  // Handle deflection criteria questions (3-7)
  if (questionId >= 3 && questionId <= 7) {
    return normalizeDeflectionCriteria(answer);
  }
  
  // Remove common prefixes
  let cleaned = answer
    .replace(/^(Answer:|The answer is:|Yes,|No,)\s*/gi, '')
    .replace(/\s+/g, ' ')
    .trim();
  
  // Apply question-specific rules
  switch (questionId) {
    case 1: {
      // First, check if this is an excluded code type (IRC, IEBC, fire, electric, gas, plumbing, etc.) - if so, mark as Not Available
      const isExcludedCode = /\b(IRC|IEBC|IFC|IFGC|IECC|IPC|IMC|IPMC|IWUIC|NFPA|NEC|N\.?E\.?C\.?|ANSI|ICC\s*A|Residential\s*Code|Fire\s*Code|International\s*Fire\s*Code|Electric(al)?\s*Code|National\s*Electrical\s*Code|Fuel\s*Gas\s*Code|International\s*Fuel\s*Gas\s*Code|Plumbing\s*Code|Mechanical\s*Code|Energy\s*Code|Existing\s*Building\s*Code)\b/i.test(cleaned);
      if (isExcludedCode) {
        return "Not Available";
      }
      
      // Remove extraneous text like chapter numbers, symbols
      // Keep only International/State building code and version year (IBC or state/city building codes)
      
      // Extract year (4 digits)
      const yearMatch = cleaned.match(/(\d{4})/);
      const year = yearMatch ? yearMatch[1] : '';
      
      // Remove chapter numbers (e.g., "Chapter 16", "Ch. 16", "16-", etc.)
      let codeText = cleaned
        .replace(/\bChapter\s*\d+\b/gi, '')
        .replace(/\bCh\.?\s*\d+\b/gi, '')
        .replace(/\d+-/g, '')
        .replace(/\(\d+\)/g, '');
      
      // Remove the year from the text
      if (year) {
        codeText = codeText.replace(year, '');
      }
      
      // Remove extra symbols and clean up spacing
      codeText = codeText
        .replace(/[,;:\[\]{}]/g, '')
        .replace(/\s+/g, ' ')
        .trim();
      
      // Return as: Building Code Name YYYY
      return year ? `${codeText} ${year}` : codeText;
    }
    
    case 8: {
      // Special normalization for deflection depth (Question 8)
      // Rule 1: Check if it's in inches format (1/2", 3/4 inch, 1.0 in, etc.)
      if (/["'']|inch(es)?|in\b/i.test(cleaned)) {
        // Extract numeric part (fractions like 1/2, 3/4 or decimals like 1.0)
        const numericMatch = cleaned.match(/(\d+\/\d+|\d+\.?\d*)/);
        return numericMatch ? numericMatch[1] : cleaned;
      }
      
      // Rule 2: Check if it's in span ratio format (1/###, L/###, l/###, span/###)
      // Convert all to L/### format
      const spanRatioMatch = cleaned.match(/(?:1|L|l|span)\s*\/\s*(\d+)/i);
      if (spanRatioMatch) {
        return `L/${spanRatioMatch[1]}`; // Return as L/###
      }
      
      // Rule 3: Check if it's a generic span ratio format with /### (e.g., /240 of span)
      // Match the number AFTER the slash
      const slashRatioMatch = cleaned.match(/\/\s*(\d+)/);
      if (slashRatioMatch) {
        return slashRatioMatch[1]; // Return just the number after the slash
      }
      
      // Default: return as-is
      return cleaned;
    }
    
    case 9:
    case 13:
    case 14: {
      // Extract integer value only (unit goes to Unit column)
      const match = cleaned.match(/(\d+)/);
      return match ? match[1] : cleaned;
    }
    
    case 19: {
      // Preserve decimal if present, otherwise keep as integer
      const match = cleaned.match(/(\d+\.?\d*)/);
      return match ? match[1] : cleaned;
    }
    
    case 15: {
      // Extract decimal value as-is from extracted answer
      const match = cleaned.match(/(\d+\.?\d*)/);
      return match ? match[1] : cleaned;
    }
    
    case 10: {
      // Extract Roman numeral I-IV
      const match = cleaned.match(/\b([IV]+)\b/i);
      return match ? match[1].toUpperCase() : cleaned;
    }
    
    case 11: {
      // Extract letter B, C, D
      const match = cleaned.match(/\b([BCD])\b/i);
      return match ? match[1].toUpperCase() : cleaned;
    }
    
    case 12: {
      // Extract decimal value as-is from extracted answer
      const match = cleaned.match(/(\d+\.\d+)/);
      return match ? match[1] : cleaned;
    }
    
    case 16:
    case 21:
    case 22: {
      // Extract decimal value as-is from extracted answer
      const match = cleaned.match(/(\d+\.?\d*)/);
      return match ? match[1] : cleaned;
    }
    
    case 24:
    case 25: {
      // Convert percentage to decimal (e.g., 20% → 0.200)
      // Format: #.### (one digit before decimal, three after)
      if (cleaned.includes('%')) {
        const match = cleaned.match(/(\d+\.?\d*)/);
        if (match) {
          const percentValue = parseFloat(match[1]);
          return (percentValue / 100).toFixed(3);
        }
      }
      // Extract decimal value and format to #.###
      const match = cleaned.match(/(\d+\.?\d*)/);
      if (match) {
        const decimalValue = parseFloat(match[1]);
        return decimalValue.toFixed(3);
      }
      return cleaned;
    }
    
    case 17:
    case 18: {
      // Extract decimal value as-is from extracted answer
      const match = cleaned.match(/(\d+\.?\d*)/);
      return match ? match[1] : cleaned;
    }
    
    case 20: {
      // Extract letter A, B, C, D
      const match = cleaned.match(/\b([ABCD])\b/i);
      return match ? match[1].toUpperCase() : cleaned;
    }
    
    case 23: {
      // Extract letter A-F or combinations BC, CD, DE
      const match = cleaned.match(/\b([A-F]{1,2}|BC|CD|DE)\b/i);
      return match ? match[1].toUpperCase() : cleaned;
    }
    
    default:
      return cleaned;
  }
};

export const standardizeUnit = (rawUnit: string): string => {
  const unit = rawUnit.toLowerCase().replace(/\./g, '').trim();
  
  // mph variants
  if (/^(mph|m\s*p\s*h|miles?\s*(per|\/)\s*hour?|mi\s*\/\s*h?r?|m\s*\/\s*h?r?)$/i.test(unit)) {
    return "mph";
  }
  // km/h variants -> mph
  if (/^(km\s*\/?\s*h|kph|kilometers?\s*(per|\/)\s*hour?|kmph)$/i.test(unit)) {
    return "mph";
  }
  // m/s variants -> mph
  if (/^(m\s*\/?\s*s|meters?\s*(per|\/)\s*second?)$/i.test(unit)) {
    return "mph";
  }
  
  // psf variants
  if (/^(psf|p\s*s\s*f|pounds?\s*(per|\/)\s*square\s*foot|lb\s*\/?\s*(sqft|sf|ft[²2])|lbs?\s*\/?\s*ft[²2]|lb\.?\s*\/?\s*sq\.?\s*ft\.?)$/i.test(unit)) {
    return "psf";
  }
  // Pa variants -> psf
  if (/^(pa|pascal|n\s*\/?\s*m[²2])$/i.test(unit)) {
    return "psf";
  }
  // kPa variants -> psf
  if (/^(kpa|kilopascal)$/i.test(unit)) {
    return "psf";
  }
  // psi variants -> psf
  if (/^(psi|p\s*s\s*i|lb\s*\/?\s*in[²2]|pounds?\s*(per|\/)\s*square\s*inch)$/i.test(unit)) {
    return "psf";
  }
  
  // inch variants
  if (/^(inch(es)?|in\.?|"|'')$/i.test(unit)) {
    return "inch";
  }
  // ft variants -> inch
  if (/^(ft|foot|feet|')$/i.test(unit)) {
    return "inch";
  }
  // cm variants -> inch
  if (/^(cm|centimeters?|centimetres?)$/i.test(unit)) {
    return "inch";
  }
  // mm variants -> inch
  if (/^(mm|millimeters?|millimetres?)$/i.test(unit)) {
    return "inch";
  }
  // m variants -> inch
  if (/^(m|meters?|metres?)$/i.test(unit) && !/mph|m\s*\//.test(rawUnit)) {
    return "inch";
  }
  
  // plf variants
  if (/^(plf|p\.?\s*l\.?\s*f\.?|pounds?\s*(per|\/)\s*linear\s*foot|lb\s*\/?\s*ft|lbs?\s*\/?\s*ft|lb\.?\s*\/?\s*ft\.?|pounds?\s*\/?\s*foot)$/i.test(unit)) {
    return "plf";
  }
  // N/m variants -> plf
  if (/^(n\s*\/?\s*m|newton\s*(per|\/)\s*meters?)$/i.test(unit)) {
    return "plf";
  }
  // kN/m variants -> plf
  if (/^(kn\s*\/?\s*m|kilonewton\s*(per|\/)\s*meters?)$/i.test(unit)) {
    return "plf";
  }
  // kg/m variants -> plf
  if (/^(kg\s*\/?\s*m|kilograms?\s*(per|\/)\s*meters?)$/i.test(unit)) {
    return "plf";
  }
  
  return unit;
};

const convertValue = (value: number, fromUnit: string): { value: number; unit: string } => {
  const unit = fromUnit.toLowerCase().replace(/\./g, '').trim();
  
  // Speed conversions to mph
  if (/^(km\s*\/?\s*h|kph|kilometers?\s*(per|\/)\s*hour?|kmph)$/i.test(unit)) {
    return { value: value * 0.621371, unit: "mph" };
  }
  if (/^(m\s*\/?\s*s|meters?\s*(per|\/)\s*second?)$/i.test(unit)) {
    return { value: value * 2.23694, unit: "mph" };
  }
  
  // Pressure/load conversions to psf
  if (/^(pa|pascal|n\s*\/?\s*m[²2])$/i.test(unit)) {
    return { value: value * 0.020885, unit: "psf" };
  }
  if (/^(kpa|kilopascal)$/i.test(unit)) {
    return { value: value * 20.885, unit: "psf" };
  }
  if (/^(psi|p\s*s\s*i|lb\s*\/?\s*in[²2]|pounds?\s*(per|\/)\s*square\s*inch)$/i.test(unit)) {
    return { value: value * 144, unit: "psf" };
  }
  
  // Length conversions to inch
  if (/^(ft|foot|feet|')$/i.test(unit)) {
    return { value: value * 12, unit: "inch" };
  }
  if (/^(cm|centimeters?|centimetres?)$/i.test(unit)) {
    return { value: value * 0.393701, unit: "inch" };
  }
  if (/^(mm|millimeters?|millimetres?)$/i.test(unit)) {
    return { value: value * 0.0393701, unit: "inch" };
  }
  if (/^(m|meters?|metres?)$/i.test(unit) && !/mph|m\s*\//.test(fromUnit)) {
    return { value: value * 39.3701, unit: "inch" };
  }
  
  // Line load conversions to plf
  if (/^(n\s*\/?\s*m|newton\s*(per|\/)\s*meters?)$/i.test(unit)) {
    return { value: value * 0.0685218, unit: "plf" };
  }
  if (/^(kn\s*\/?\s*m|kilonewton\s*(per|\/)\s*meters?)$/i.test(unit)) {
    return { value: value * 68.5218, unit: "plf" };
  }
  if (/^(kg\s*\/?\s*m|kilograms?\s*(per|\/)\s*meters?)$/i.test(unit)) {
    return { value: value * 0.671969, unit: "plf" };
  }
  
  // No conversion needed
  return { value, unit: standardizeUnit(fromUnit) };
};

export const extractUnit = (answer: string, questionId: number): string => {
  // Handle both internal "Not Found" and display "Not Available"
  if (answer === "Not Found" || answer === "Not Available") return "";
  
  // Special handling for Question 8 (deflection depth)
  if (questionId === 8) {
    // If answer contains inch indicators, return "inch"
    if (/["'']|inch(es)?|in\b/i.test(answer)) {
      return "inch";
    }
    // If it's a ratio format (/360, L/360, etc.), return empty string
    if (/(?:L\s*)?\/?\s*\d+(?:\s+of\s+span)?/i.test(answer)) {
      return "";
    }
    return "";
  }
  
  // Only extract units for specific questions
  const questionsWithUnits = [9, 13, 14, 15, 19];
  if (!questionsWithUnits.includes(questionId)) {
    return "";
  }
  
  // Extract unit patterns
  const unitPatterns = [
    /\b(mph|m\.?\s*p\.?\s*h\.?|miles?\s*(per|\/)\s*hours?|mi\s*\/\s*h?r?|m\s*\/\s*h?r?)\b/i,
    /\b(km\s*\/?\s*h|kph|kilometers?\s*(per|\/)\s*hours?|kmph)\b/i,
    /\b(m\s*\/?\s*s|meters?\s*(per|\/)\s*seconds?)\b/i,
    /\b(psf|p\.?\s*s\.?\s*f\.?|pounds?\s*(per|\/)\s*square\s*foot|lb\s*\/?\s*(sqft|sf|ft[²2])|lbs?\s*\/?\s*ft[²2])\b/i,
    /\b(psi|p\.?\s*s\.?\s*i\.?|lb\s*\/?\s*in[²2]|pounds?\s*(per|\/)\s*square\s*inch)\b/i,
    /\b(pa|pascal|n\s*\/?\s*m[²2])\b/i,
    /\b(kpa|kilopascal)\b/i,
    /\b(plf|p\.?\s*l\.?\s*f\.?|pounds?\s*(per|\/)\s*linear\s*foot|lb\s*\/?\s*ft|lbs?\s*\/?\s*ft|pounds?\s*\/?\s*foot)\b/i,
    /\b(n\s*\/?\s*m|newton\s*(per|\/)\s*meters?)\b/i,
    /\b(kn\s*\/?\s*m|kilonewton\s*(per|\/)\s*meters?)\b/i,
    /\b(kg\s*\/?\s*m|kilograms?\s*(per|\/)\s*meters?)\b/i,
    /\b(inches?|in\.?|")\b/i,
    /\b(feet|foot|ft\.?|')\b/i,
    /\b(cm|centimeters?|centimetres?)\b/i,
    /\b(mm|millimeters?|millimetres?)\b/i,
  ];
  
  for (const pattern of unitPatterns) {
    const match = answer.match(pattern);
    if (match) {
      return standardizeUnit(match[1]);
    }
  }
  
  return "";
};

// Helper: Generate HTML snapshot from flattened rows
function generateSnapshotHtml(rows: any[], projectName: string): string {
  const tableRows = rows.map(row => {
    const isExcluded = row.excluded === true;
    const isDeleted = row.deleted === true;
    const isNotApplicable = row.is_not_applicable === true;
    const isGrayed = isExcluded || isDeleted || isNotApplicable;
    
    // Build tooltip text
    let tooltipText = '';
    if (isExcluded && row.excluded_by && row.excluded_at) {
      const excludedDate = new Date(row.excluded_at).toLocaleString();
      tooltipText = `This answer was excluded by ${row.excluded_by} on ${excludedDate}`;
    } else if (isDeleted && row.deleted_by && row.deleted_at) {
      const deletedDate = new Date(row.deleted_at).toLocaleString();
      tooltipText = `This answer was deleted by ${row.deleted_by} on ${deletedDate}`;
    }
    
    const rowStyle = isGrayed 
      ? 'background-color: #f2f2f2; color: #888888; font-style: italic;' 
      : '';
    const cellStyle = isGrayed 
      ? 'border: 1px solid #ddd; padding: 8px; color: #888888;' 
      : 'border: 1px solid #ddd; padding: 8px;';
    
    return `
    <tr style="${rowStyle}" title="${tooltipText}">
      <td style="${cellStyle}">${row.category}</td>
      <td style="${cellStyle}">${row.question}</td>
      <td style="${cellStyle}">${row.extracted_answer}</td>
      <td style="${cellStyle}">${row.normalized_answer}</td>
      <td style="${cellStyle}">${row.unit}</td>
      <td style="${cellStyle}">${row.reference}</td>
      <td style="${cellStyle}">${row.feedback}</td>
      <td style="${cellStyle}">${row.is_edited ? '✏️' : ''}${isExcluded ? ' ❌' : ''}${isDeleted ? ' 🗑️' : ''}${isNotApplicable ? ' 🚫' : ''}</td>
    </tr>
  `;
  }).join('');

  return `
    <!DOCTYPE html>
    <html>
      <head>
        <meta charset="UTF-8">
        <title>${projectName} - Results</title>
        <style>
          body { font-family: Arial, sans-serif; margin: 20px; }
          table { border-collapse: collapse; width: 100%; }
          th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
          th { background-color: #f2f2f2; }
        </style>
      </head>
      <body>
        <h1>${projectName}</h1>
        <table>
          <thead>
            <tr>
              <th>Category</th>
              <th>Question</th>
              <th>Extracted Answer</th>
              <th>Normalized Answer</th>
              <th>Unit</th>
              <th>Reference</th>
              <th>AI Extraction Accuracy</th>
              <th>Edited</th>
            </tr>
          </thead>
          <tbody>
            ${tableRows}
          </tbody>
        </table>
      </body>
    </html>
  `;
}

export const ResultsDisplay = ({
  results,
  projectId,
  projectName,
  processingTimeSeconds,
  processingTimeMinutes,
  processingRecordId,
  projectHash,
  filesMetadata,
  onProjectIdChange,
  onProjectNameChange,
  onExportCSV,
  onExportJSON,
  onUpdateAnswer,
  onUpdateNormalizedAnswer,
  onUpdateFeedback,
  onDeleteAnswer,
  onSelectAnswer,
  onExcludeAnswer,
  onIncludeAnswer,
  onMarkNotApplicable,
  onRestoreApplicable,
  hideSubmitButton = false,
  persistEditsLocally = true,
  externalEditHistory,
  onSubmitSuccess,
  onDirtyStateChange,
  onSaveCallback,
  onSaveAndExit,
}: ResultsDisplayProps) => {
  const { toast } = useToast();
  const { user: authUser } = useAuth();
  
  // Review dirty state tracking for unsaved changes protection
  // Uses combined hook that handles both internal SPA navigation and external browser events
  const { 
    isDirty, 
    markDirty, 
    markClean, 
    reset: resetDirtyState,
    showDialog: showUnsavedDialog,
    setShowDialog: setShowUnsavedDialog,
    handleProceed: proceedWithNavigation,
    handleStay: cancelNavigation,
    triggerNavigationBlock,
  } = useUnsavedChangesProtection();
  
  const [isSavingForLater, setIsSavingForLater] = useState(false);
  
  // Notify parent of dirty state changes
  useEffect(() => {
    onDirtyStateChange?.(isDirty);
  }, [isDirty, onDirtyStateChange]);

  // Helper to clean question text
  const cleanQuestionText = (question: string, questionNumber?: number): string => {
    // Special handling for question 1
    if (questionNumber === 1) {
      return 'Building Code & Year';
    }
    
    // Remove "What is the" or "What are the" prefix
    let cleaned = question
      .replace(/^What is the\s+/i, '')
      .replace(/^What are the\s+/i, '');
    
    // List of abbreviations to preserve in original case
    const preservedWords = ['SDS', 'SD1', 'Ip', 'Ie', 'Pf', 'Ct', 'Ce', 'Is', 'Pg', 'Vult', 'GCpi', 'ASCE'];
    
    // Split into words and capitalize each word
    const words = cleaned.split(/\s+/);
    const capitalizedWords = words.map(word => {
      // Check if this word (case-insensitive) is in the preserved list
      const matchedPreserved = preservedWords.find(
        preserved => word.toLowerCase() === preserved.toLowerCase()
      );
      
      if (matchedPreserved) {
        // Return the preserved version
        return matchedPreserved;
      }
      
      // Otherwise capitalize first letter, lowercase the rest
      if (word.length === 0) return word;
      return word.charAt(0).toUpperCase() + word.slice(1).toLowerCase();
    });
    
    let result = capitalizedWords.join(' ');
    
    // Remove "?" from the end, except for question 2
    if (questionNumber !== 2 && result.endsWith('?')) {
      result = result.slice(0, -1);
    }
    
    return result;
  };

  // Helper to extract answer locations from results
  // Only extract locations that have valid bounding box coordinates to prevent random highlights
  const extractAnswerLocations = (results: AnalysisResult[]) => {
    const locations: any[] = [];
    results.forEach((result) => {
      result.pairs.forEach((pair: any) => {
        // Check if pair has valid bounding box data
        if (pair.bbox && 
            typeof pair.bbox.x === 'number' && 
            typeof pair.bbox.y === 'number' &&
            typeof pair.bbox.width === 'number' && 
            typeof pair.bbox.height === 'number') {
          // Only add locations with valid bbox coordinates
          const pageMatch = pair.reference?.match(/Page\s+(\d+)/i);
          if (pageMatch) {
            locations.push({
              question: result.question,
              category: result.category,
              answer: pair.answer,
              page: parseInt(pageMatch[1]),
              reference: pair.reference,
              x: pair.bbox.x,
              y: pair.bbox.y,
              width: pair.bbox.width,
              height: pair.bbox.height,
            });
          }
        }
      });
    });
    console.log('Extracted answer locations with bbox:', locations.length);
    return locations;
  };

  // Handle answer location updates from PDF viewer
  const handleAnswerLocationUpdate = (locationId: string, updates: any) => {
    console.log('Answer location updated:', locationId, updates);
    toast({
      title: "Bounding box updated",
      description: "Changes will be saved with the project.",
    });
  };

  const [editingKey, setEditingKey] = useState<string | null>(null);
  const [editValue, setEditValue] = useState("");
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<{ resultIndex: number; pairIndex: number } | null>(null);
  const [deletedAnswers, setDeletedAnswers] = useState<{[key: string]: boolean}>({});
  const [deflectionDialogOpen, setDeflectionDialogOpen] = useState(false);
  const [deflectionEditContext, setDeflectionEditContext] = useState<{ resultIndex: number; pairIndex: number; value: string } | null>(null);
  const [excludedAnswers, setExcludedAnswers] = useState<{[key: string]: boolean}>({});
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isSubmitted, setIsSubmitted] = useState(false);
  const [downloadLinks, setDownloadLinks] = useState<{ csv?: string; json?: string }>({});
  const [currentUser, setCurrentUser] = useState<{ id: string; fullName: string } | null>(null);
  const [editHistory, setEditHistory] = useState<Record<string, any[]>>({});
  const [supervisors, setSupervisors] = useState<Array<{ user_id: string; full_name: string; email: string }>>([]);
  const [selectedSupervisor, setSelectedSupervisor] = useState<string>("");
  const [supervisorPopoverOpen, setSupervisorPopoverOpen] = useState(false);
  const [submitConfirmOpen, setSubmitConfirmOpen] = useState(false);
  const [publishDirectConfirmOpen, setPublishDirectConfirmOpen] = useState(false);
  const [hasEdits, setHasEdits] = useState(false);
  const [pdfUrls, setPdfUrls] = useState<Array<{ name: string; url: string; pageCount?: number; size?: number }>>([]);
  const [selectedPdfIndex, setSelectedPdfIndex] = useState(0);
  const [pdfHighlights, setPdfHighlights] = useState<PDFHighlight[]>([]);
  const [loadingPdf, setLoadingPdf] = useState(false);
  const [feedbackLoading, setFeedbackLoading] = useState<FeedbackLoadingState>({});
  const [isPopoutActive, setIsPopoutActive] = useState(false);
  
  // Broadcast channel for cross-window PDF navigation
  const { sendNavigate } = usePdfBroadcastChannel({
    projectId: projectHash,
    enabled: true,
  });
  
  // Local results state that can be updated synchronously for immediate UI feedback
  // This is initialized from props and synced when props change
  const [localResults, setLocalResults] = useState<AnalysisResult[]>(results);
  
  // Ref to always have the latest results for database persistence (prevents race conditions)
  const resultsRef = useRef<AnalysisResult[]>(results);
  
  // Flag to skip syncing from props immediately after a local edit
  // This prevents the UI from reverting to stale parent state during async updates
  const justEditedRef = useRef(false);
  
  // Sync local state and ref when props change (e.g., from parent state updates)
  useEffect(() => {
    // Skip syncing from props for 150ms after a local edit
    // This prevents overwriting the immediate UI update with stale parent state
    if (justEditedRef.current) {
      console.log('[ResultsDisplay] Skipping sync from props - justEditedRef is true');
      return;
    }
    setLocalResults(results);
    resultsRef.current = results;
  }, [results]);

  // Fetch ALL PDF URLs from files metadata
  useEffect(() => {
    const loadAllPdfs = async () => {
      console.log('ResultsDisplay: filesMetadata =', filesMetadata);
      
      if (!filesMetadata || filesMetadata.length === 0) {
        console.log('ResultsDisplay: No files metadata available');
        return;
      }

      const pdfFiles = filesMetadata.filter((f) => f.name?.toLowerCase().endsWith('.pdf'));
      if (pdfFiles.length === 0) {
        console.log('ResultsDisplay: No PDF files found in metadata:', filesMetadata);
        return;
      }

      console.log('ResultsDisplay: Found PDF files:', pdfFiles);

      try {
        setLoadingPdf(true);

        const urlPromises = pdfFiles.map(async (pdfFile) => {
          const urlData = await apiClient.getPresignedUrl(pdfFile.path);
          return {
            name: pdfFile.name,
            url: urlData.signed_url,
            size: pdfFile.size,
          };
        });
        const urls = await Promise.all(urlPromises);

        console.log('ResultsDisplay: All PDF URLs loaded:', urls);
        setPdfUrls(urls);
        
        toast({
          title: "PDFs Loaded",
          description: `${urls.length} document(s) ready for preview`
        });
      } catch (error) {
        console.error('ResultsDisplay: Error loading PDFs:', error);
        toast({
          title: "PDF Load Error", 
          description: "Failed to load document previews",
          variant: "destructive"
        });
      } finally {
        setLoadingPdf(false);
      }
    };

    loadAllPdfs();
  }, [filesMetadata, toast]);

  // Fetch all users who can be assigned using secure endpoint (no email exposure)
  useEffect(() => {
    const fetchUsers = async () => {
      try {
        const data = await apiClient.getUsersForAssignment();

        if (data) {
          setSupervisors(data.map((u: { user_id: string; full_name: string }) => ({
            user_id: u.user_id,
            full_name: u.full_name || '',
            email: '' // Not exposed by secure endpoint
          })));
        }
      } catch (error) {
        console.error('Error fetching users for assignment:', error);
      }
    };

    fetchUsers();
  }, []);

  // Check if project has edits (both from database and local edit history)
  useEffect(() => {
    const checkEdits = async () => {
      if (!projectHash) return;

      // Check if there are any edits in the local edit history
      const hasLocalEdits = Object.keys(editHistory).length > 0;

      // Also check database for existing edits via API
      try {
        const data = await apiClient.getProjectByHash(projectHash);
        setHasEdits(hasLocalEdits || data?.is_edited || false);
      } catch {
        setHasEdits(hasLocalEdits);
      }
    };
    checkEdits();
  }, [projectHash, editHistory]);

  // Get current user info from auth hook
  useEffect(() => {
    if (authUser) {
      setCurrentUser({
        id: authUser.id,
        fullName: authUser.full_name || authUser.email?.split('@')[0] || 'Unknown User',
      });
    }
  }, [authUser]);

  // Load edit history for this project
  useEffect(() => {
    const fetchEditHistory = async () => {
      if (!projectHash) return;

      try {
        const data = await apiClient.getEditHistory(projectHash);
        if (data) {
          const groupedEdits: Record<string, any[]> = {};
          data.forEach((edit: any) => {
            const key = `${edit.row_id}`;
            if (!groupedEdits[key]) groupedEdits[key] = [];
            groupedEdits[key].push(edit);
          });
          setEditHistory(groupedEdits);
        }
      } catch (error) {
        console.error('Error fetching edit history:', error);
      }
    };
    fetchEditHistory();
  }, [projectHash]);

  // Reset submission state when results change (new project run)
  useEffect(() => {
    setIsSubmitted(false);
    setDownloadLinks({});
  }, [results]);

  // Interface for deduplicated pairs that preserves original index
  interface DeduplicatedPair extends AnswerReferencePair {
    originalPairIndex: number;
  }

  // Deduplicate pairs with the same answer, keeping only unique answers
  // For Question 1 (Building Code), also applies HARD filter to exclude non-building codes
  // CRITICAL: Preserves originalPairIndex so handlers can target the correct database row
  const deduplicatePairs = (pairs: AnswerReferencePair[], questionIndex?: number): DeduplicatedPair[] => {
    const seen = new Map<string, DeduplicatedPair>();
    pairs.forEach((pair, originalIndex) => {
      // For Question 1 (index 0), apply hard building code filter
      if (questionIndex === 0 && !isValidBuildingCodeAnswer(pair.answer)) {
        return; // Skip invalid building code answers completely
      }
      const existing = seen.get(pair.answer);
      if (!existing) {
        seen.set(pair.answer, { ...pair, originalPairIndex: originalIndex });
      } else if (pair.is_edited && !existing.is_edited) {
        // Prefer edited versions over non-edited duplicates so UI shows edited value
        seen.set(pair.answer, { ...pair, originalPairIndex: originalIndex });
      }
    });
    return Array.from(seen.values());
  };

  // Build document context for chatbot from results and full document text
  const documentContext = useMemo(() => {
    if (results.length === 0) return "";
    
    let context = `Project ID: ${projectId}\nProject Name: ${projectName}\n\n`;
    
    // Add extracted Q&A data
    context += "=== EXTRACTED Q&A DATA ===\n\n";
    
    results.forEach((result, index) => {
      const uniquePairs = deduplicatePairs(result.pairs, index);
      
      context += `${index + 1}. [${result.category}] ${result.question}\n`;
      
      uniquePairs.forEach((pair, pairIndex) => {
        // Exclude "Not Found" and "Not Available" answers from context
        if (pair.answer !== "Not Found" && pair.answer !== "Not Available") {
          context += `   Answer ${pairIndex + 1}: ${pair.answer}\n`;
          if (pair.reference) {
            context += `   Reference: ${pair.reference}\n`;
          }
          if (pair.confidence !== undefined) {
            context += `   Confidence: ${formatConfidence(pair.answer, pair.confidence)}\n`;
          }
        }
      });
      
      context += "\n";
    });
    
    return context;
  }, [results, projectId, projectName]);

  // Fetch and include full document text for enhanced chatbot capabilities
  const [fullDocumentText, setFullDocumentText] = useState<string>("");
  
  useEffect(() => {
    const fetchDocumentText = async () => {
      if (!processingRecordId || results.length === 0) return;

      try {
        // Fetch document text via API
        const data = await apiClient.getDocumentText(processingRecordId);

        if (data && data.length > 0) {
          // Combine all document texts if multiple files
          const combinedText = data
            .map((doc: any) => doc.document_text)
            .filter((text: string) => text)
            .join('\n\n--- NEXT DOCUMENT ---\n\n');

          setFullDocumentText(combinedText);
        }
      } catch (error) {
        console.error('Error fetching document text:', error);
      }
    };

    fetchDocumentText();
  }, [processingRecordId, results]);

  // Combine extracted data with full document text
  const enhancedContext = useMemo(() => {
    let combined = documentContext;
    
    if (fullDocumentText) {
      combined += "\n\n=== FULL DOCUMENT TEXT ===\n\n";
      combined += fullDocumentText;
      combined += "\n\n=== END OF DOCUMENT ===";
    }
    
    return combined;
  }, [documentContext, fullDocumentText]);

  if (localResults.length === 0) return null;

  const totalPairs = localResults.reduce((sum, result, idx) => sum + deduplicatePairs(result.pairs, idx).length, 0);

  // State for accuracy tracking
  const [accuracy, setAccuracy] = useState(0);
  const [isInitialAccuracy, setIsInitialAccuracy] = useState(true);
  
  // State for backend processing time
  const [backendProcessingTime, setBackendProcessingTime] = useState<number | null>(null);
  const [backendSavedTime, setBackendSavedTime] = useState<number | null>(null);
  
  // Edit protection and auto-save state
  const [isEditing, setIsEditing] = useState(false);
  const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false);
  const [lastSavedAt, setLastSavedAt] = useState<Date | null>(null);
  
  // Refs for debouncing and tracking
  const editTimerRef = useRef<NodeJS.Timeout | null>(null);
  const accuracyUpdateTimerRef = useRef<NodeJS.Timeout | null>(null);
  const autoSaveTimerRef = useRef<NodeJS.Timeout | null>(null);
  const localStorageKey = `project_backup_${projectHash}`;
  const isInitialMount = useRef(true);

  // PHASE 1: Stop Polling Cascade - Only poll on mount, not on every edit
  useEffect(() => {
    // Skip if user is actively editing
    if (isEditing) {
      console.log('⏸️  Skipping metrics fetch - user is editing');
      return;
    }
    
    const fetchProcessingMetrics = async () => {
      if (processingRecordId) {
        try {
          const data = await apiClient.getProcessingMetrics(processingRecordId);

          if (data?.processed_time !== null && data?.processed_time !== undefined) {
            console.log('Fetched processed_time from DB:', data.processed_time, 'minutes');
            setBackendProcessingTime(data.processed_time);
            setBackendSavedTime(data.saved_time || null);
          } else {
            console.log('No processed_time in DB yet');
          }
        } catch {
          console.log('No processed_time in DB yet');
        }
      }
    };
    
    fetchProcessingMetrics();
    
    // Poll for updates every 500ms for the first 5 seconds ONLY on mount
    const pollInterval = setInterval(fetchProcessingMetrics, 500);
    const stopPolling = setTimeout(() => clearInterval(pollInterval), 5000);
    
    return () => {
      clearInterval(pollInterval);
      clearTimeout(stopPolling);
    };
  }, [processingRecordId]); // FIXED: Removed 'results' from dependencies

  // PHASE 2: Optimize Database Updates - Debounce accuracy calculations
  useEffect(() => {
    // Skip if user is actively editing
    if (isEditing) {
      console.log('⏸️  Skipping accuracy calculation - user is editing');
      return;
    }
    
    const calculateAccuracy = async () => {
      // Filter out N/A questions from accuracy calculation
      const applicableResults = results.filter(result => 
        !result.pairs.some(pair => pair.is_not_applicable === true)
      );
      
      // Count all individual answers with feedback (answer-level accuracy)
      let totalAnswers = 0;
      let likedAnswers = 0;
      
      applicableResults.forEach(result => {
        result.pairs.forEach(pair => {
          if (pair.feedback === "up" || pair.feedback === "down") {
            totalAnswers++;
            if (pair.feedback === "up") {
              likedAnswers++;
            }
          }
        });
      });
      
      if (totalAnswers > 0) {
        const feedbackAccuracy = (likedAnswers / totalAnswers) * 100;
        
        // Update state immediately (optimistic UI)
        setAccuracy(feedbackAccuracy);
        setIsInitialAccuracy(false);
        
        // Debounce database update - only update 3 seconds after user stops editing
        if (accuracyUpdateTimerRef.current) {
          clearTimeout(accuracyUpdateTimerRef.current);
        }
        
        accuracyUpdateTimerRef.current = setTimeout(async () => {
          const allQuestionsHaveFeedback = applicableResults.every(result =>
            result.pairs.some(pair => pair.feedback === "up" || pair.feedback === "down")
          );

          if (allQuestionsHaveFeedback && processingRecordId) {
            console.log('Updating final_accuracy in database:', feedbackAccuracy);
            try {
              await apiClient.updateProjectById(processingRecordId, { final_accuracy: feedbackAccuracy });
            } catch (e) {
              console.error('Error updating final_accuracy:', e);
            }
          }
        }, 3000); // Wait 3 seconds after last change
      } else {
        if (processingRecordId) {
          try {
            const data = await apiClient.getProcessingMetrics(processingRecordId);
            if (data?.initial_accuracy !== null && data?.initial_accuracy !== undefined) {
              setAccuracy(data.initial_accuracy);
              setIsInitialAccuracy(true);
            } else {
              setAccuracy(0);
            }
          } catch {
            setAccuracy(0);
          }
        }
      }
    };
    
    calculateAccuracy();
    
    return () => {
      if (accuracyUpdateTimerRef.current) {
        clearTimeout(accuracyUpdateTimerRef.current);
      }
    };
  }, [results, processingRecordId, isEditing]);

  // PHASE 3 & 4: Session Recovery, Auto-Save, and Edit Protection
  
  // Auto-save to localStorage every time results change
  useEffect(() => {
    if (autoSaveTimerRef.current) {
      clearTimeout(autoSaveTimerRef.current);
    }
    
    autoSaveTimerRef.current = setTimeout(() => {
      const backup = {
        results,
        projectId,
        projectName,
        timestamp: new Date().toISOString(),
      };
      localStorage.setItem(localStorageKey, JSON.stringify(backup));
      console.log('💾 Auto-saved to localStorage');
    }, 1000); // Save 1 second after last change
    
    return () => {
      if (autoSaveTimerRef.current) {
        clearTimeout(autoSaveTimerRef.current);
      }
    };
  }, [results, projectId, projectName, localStorageKey]);
  
  // Track editing state with debounce
  useEffect(() => {
    if (editingKey) {
      setIsEditing(true);
      setHasUnsavedChanges(true);
      console.log('✏️  User started editing');
      
      // Clear previous timer
      if (editTimerRef.current) {
        clearTimeout(editTimerRef.current);
      }
      
      // Mark as not editing 2 seconds after last edit
      editTimerRef.current = setTimeout(() => {
        setIsEditing(false);
        console.log('⏸️  User stopped editing');
      }, 2000);
    }
    
    return () => {
      if (editTimerRef.current) {
        clearTimeout(editTimerRef.current);
      }
    };
  }, [editingKey, editValue]);
  
  // Warn before leaving page with unsaved changes
  useEffect(() => {
    const handleBeforeUnload = (e: BeforeUnloadEvent) => {
      if (hasUnsavedChanges) {
        e.preventDefault();
        e.returnValue = 'You have unsaved changes. Are you sure you want to leave?';
        return e.returnValue;
      }
    };
    
    window.addEventListener('beforeunload', handleBeforeUnload);
    return () => window.removeEventListener('beforeunload', handleBeforeUnload);
  }, [hasUnsavedChanges]);
  
  // Mark as saved after successful submission
  const markAsSaved = useCallback(() => {
    setHasUnsavedChanges(false);
    setLastSavedAt(new Date());
    localStorage.removeItem(localStorageKey);
    // Also reset the dirty state tracking
    markClean();
    resetDirtyState();
    console.log('✅ Changes saved to database');
  }, [localStorageKey, markClean, resetDirtyState]);

  // Save progress and continue later (in-review saved state)
  const handleSaveAndContinueLater = useCallback(async () => {
    if (!currentUser) return;
    
    setIsSavingForLater(true);
    try {
      // Build snapshot from resultsRef (always-latest source of truth) to avoid race conditions
      const snapshotJson = resultsRef.current.map((result, idx) => {
        return result.pairs.map((pair, pairIdx) => ({
          row_id: `${idx}-${pairIdx}`,
          question_id: idx + 1,
          category: result.category,
          question: result.question,
          extracted_answer: pair.answer,
          normalized_answer: pair.normalizedAnswer || "",
          unit: pair.unit || "",
          reference: pair.reference,
          confidence: pair.confidence,
          feedback: pair.feedback || "",
          is_edited: pair.is_edited || false,
          excluded: pair.excluded || false,
          deleted: pair.deleted || false,
          is_selected: pair.is_selected || false,
          // N/A fields - include all metadata for persistence
          is_not_applicable: pair.is_not_applicable || false,
          not_applicable_by: pair.not_applicable_by || "",
          not_applicable_at: pair.not_applicable_at || "",
          not_applicable_restored_by: pair.not_applicable_restored_by || "",
          not_applicable_restored_at: pair.not_applicable_restored_at || "",
        }));
      }).flat();
      
      await apiClient.submitProjectForApproval({
        projectHash,
        projectId,
        projectName,
        results: snapshotJson,
        feedback: localResults.map((r, idx) => ({
          question_id: idx + 1,
          question: r.question,
          feedback: r.pairs.map(p => ({ answer: p.answer, feedback: p.feedback })),
        })),
        saveForLater: true,
        savedByUserId: currentUser.id,
        savedByFullName: currentUser.fullName,
        pendingSnapshotJson: snapshotJson,
        pendingSnapshotHtml: "",
      });
      
      markAsSaved();
      
      toast({
        title: "Progress Saved",
        description: "Your review has been saved. You can continue later from Waiting for Approval.",
      });
      
      // Don't call proceedWithNavigation or onSubmitSuccess here - let parent handle it
    } catch (error: any) {
      console.error("Save for later error:", error);
      toast({
        title: "Save Failed",
        description: error.message || "Failed to save progress. Please try again.",
        variant: "destructive",
      });
      throw error; // Re-throw so parent knows save failed
    } finally {
      setIsSavingForLater(false);
    }
  }, [currentUser, localResults, projectHash, projectId, projectName, markAsSaved, toast]);
  
  // Expose save function to parent for navigation guard
  useEffect(() => {
    if (onSaveCallback) {
      onSaveCallback(handleSaveAndContinueLater);
    }
  }, [onSaveCallback, handleSaveAndContinueLater]);
  
  // Autosave on visibility change (tab hidden) to prevent data loss on tab close
  useAutosaveOnVisibilityChange(isDirty, handleSaveAndContinueLater);
  
  // Handle discard changes
  const handleDiscardChanges = () => {
    markAsSaved();
    // Proceed with the blocked navigation
    proceedWithNavigation();
  };
  
  // Handle cancel (stay on page)
  const handleCancelNavigation = () => {
    // Stay on page - cancel the blocked navigation
    cancelNavigation();
  };

  // Handle save and exit - saves changes and navigates home
  const handleSaveAndExit = useCallback(async () => {
    try {
      await handleSaveAndContinueLater();
      // On success, call the exit callback to navigate home
      if (onSaveAndExit) {
        onSaveAndExit();
      }
    } catch (error) {
      // Error toast already shown by handleSaveAndContinueLater
      console.error("Save and exit failed:", error);
    }
  }, [handleSaveAndContinueLater, onSaveAndExit]);

  // Calculate answers with likes for display (answer-level accuracy)
  let totalAnswersForDisplay = 0;
  let likedAnswersForDisplay = 0;
  localResults.forEach(result => {
    result.pairs.forEach(pair => {
      if (pair.feedback === "up" || pair.feedback === "down") {
        totalAnswersForDisplay++;
        if (pair.feedback === "up") {
          likedAnswersForDisplay++;
        }
      }
    });
  });
  const questionsWithLikes = likedAnswersForDisplay;
  const totalQuestions = localResults.length;

  // PRIORITY: Always use backend time if available (single source of truth from process-document edge function)
  // Fall back to prop values only during initial processing before DB value is available
  const displayProcessingTime = backendProcessingTime !== null 
    ? backendProcessingTime 
    : (processingTimeMinutes !== undefined && processingTimeMinutes !== null
      ? processingTimeMinutes
      : processingTimeSeconds / 60); // Convert seconds to minutes for frontend time during active processing
  
  // Saved Time = 2400 minutes - Processed Time
  const displaySavedTime = 2400 - displayProcessingTime;

  const handleEditStart = (resultIndex: number, pairIndex: number, currentAnswer: string) => {
    setEditingKey(`${resultIndex}-${pairIndex}`);
    setEditValue(currentAnswer);
  };

  const handleEditSave = async (resultIndex: number, pairIndex: number, newValue?: string) => {
    if (!currentUser) {
      toast({
        title: "Authentication Required",
        description: "You must be signed in to edit results.",
        variant: "destructive",
      });
      return;
    }

    const pair = resultsRef.current[resultIndex].pairs[pairIndex];
    const questionId = resultIndex + 1;
    const isNormalized = editingKey?.startsWith('norm-');
    
    // BLOCK editing of Extracted Answer column
    if (!isNormalized) {
      toast({
        title: "Edit Not Allowed",
        description: "The Extracted Answer column cannot be edited.",
        variant: "destructive",
      });
      setEditingKey(null);
      return;
    }
    
    const columnName = 'Normalized Answer';
    const oldValue = pair.normalizedAnswer || normalizeAnswer(pair.answer, questionId);
    
    // Use the passed newValue or fall back to editValue state
    const valueToSave = newValue !== undefined ? newValue : editValue;
    
    // If no change, just cancel
    if (valueToSave === oldValue) {
      setEditingKey(null);
      return;
    }

    // Generate row_id for this result
    const rowId = `${resultIndex}-${pairIndex}`;
    
    // Store original values if not already stored
    const originalNormalizedAnswer = pair.originalNormalizedAnswer || pair.normalizedAnswer || normalizeAnswer(pair.answer, questionId);
    
    // User edited Normalized Answer directly - use it as-is
    const newNormalizedAnswer = valueToSave;

    // If persistEditsLocally is false, just call the callback and exit (parent handles persistence + note dialog)
    if (!persistEditsLocally) {
      onUpdateNormalizedAnswer(resultIndex, pairIndex, newNormalizedAnswer);
      setEditingKey(null);
      return;
    }

    // Save audit record with question metadata
    try {
      const result = results[resultIndex];
      await apiClient.createResultEdit({
        project_hash: projectHash,
        row_id: rowId,
        column_name: columnName,
        old_value: oldValue,
        new_value: newNormalizedAnswer,
        edited_by_user_id: currentUser.id,
        edited_by_full_name: currentUser.fullName,
        question_id: questionId,
        question_text: result.question,
        category: result.category,
      });

      // Build last_edited_changes object
      const lastEditedChanges = pair.last_edited_changes || {};
      lastEditedChanges["Normalized Answer"] = {
        old: oldValue,
        new: newNormalizedAnswer
      };

      // CRITICAL: Build the updated results with ALL metadata FIRST
      // This ensures both UI (via resultsRef) and DB have identical data
      const latestResults = JSON.parse(JSON.stringify(resultsRef.current));
      latestResults[resultIndex].pairs[pairIndex] = {
        ...latestResults[resultIndex].pairs[pairIndex],
        normalizedAnswer: newNormalizedAnswer,
        originalNormalizedAnswer: originalNormalizedAnswer,
        is_edited: true,
        last_edited_by_full_name: currentUser.fullName,
        last_edited_at: new Date().toISOString(),
        last_edited_changes: lastEditedChanges,
      };
      
      // CRITICAL: Set justEditedRef BEFORE updating state to prevent useEffect from overwriting
      justEditedRef.current = true;
      
      // Use functional state update to ensure we're working with the latest state
      // and update resultsRef atomically within the same update cycle
      setLocalResults(() => {
        resultsRef.current = latestResults;
        console.log('[handleEditSave] Updated localResults:', latestResults[resultIndex].pairs[pairIndex].normalizedAnswer);
        return latestResults;
      });
      
      // Also notify parent to update its state (for consistency across app)
      onUpdateNormalizedAnswer(resultIndex, pairIndex, newNormalizedAnswer);
      
      // Clear justEditedRef after 500ms to allow parent state to fully propagate
      // 150ms was too short and allowed stale parent state to overwrite local edits
      setTimeout(() => {
        justEditedRef.current = false;
        console.log('[handleEditSave] justEditedRef cleared - ready to sync from props');
      }, 500);

      // Persist to database with the complete updated results
      console.log('[handleEditSave] Saving to DB, normalizedAnswer:', newNormalizedAnswer);
      try {
        await apiClient.updateProjectByHash(projectHash, {
          results: latestResults,
          is_edited: true,
        });
        console.log('[handleEditSave] DB save confirmed');
      } catch (updateError) {
        console.error('Error updating results with edit metadata:', updateError);
      }
      
      // Update local hasEdits state immediately
      setHasEdits(true);

      // Reload edit history to get the latest edit record ID
      const editHistoryData = await apiClient.getEditHistory(projectHash);
      const latestEdit = (editHistoryData || []).find(
        (e: any) => e.row_id === rowId && e.column_name === columnName
      );
      const data = latestEdit ? [latestEdit] : [];

      console.log('[handleEditSave] Edit saved, record ID:', data?.[0]?.id);

      // Update local editHistory immediately so pencil icon shows right away
      const newEditEntry = {
        id: data?.[0]?.id,
        project_hash: projectHash,
        row_id: rowId,
        column_name: columnName,
        old_value: oldValue,
        new_value: newNormalizedAnswer,
        edited_by_user_id: currentUser.id,
        edited_by_full_name: currentUser.fullName,
        edited_at: new Date().toISOString(),
        question_id: questionId,
        question_text: result.question,
        category: result.category,
      };
      setEditHistory(prev => ({
        ...prev,
        [rowId]: [newEditEntry, ...(prev[rowId] || [])],
      }));

      // Automatically trigger dislike feedback when normalized answer is edited
      const currentFeedback = pair.feedback;
      if (currentFeedback !== "down") {
        // Update the latest results with dislike feedback
        latestResults[resultIndex].pairs[pairIndex] = {
          ...latestResults[resultIndex].pairs[pairIndex],
          feedback: "down"
        };
        
        // Persist feedback to database
        await apiClient.updateProjectByHash(projectHash, {
          results: latestResults,
        });

        // Create audit log entry for the automatic dislike
        await apiClient.createResultEdit({
          project_hash: projectHash,
          row_id: rowId,
          column_name: "Feedback",
          old_value: currentFeedback || "none",
          new_value: "down",
          edited_by_user_id: currentUser.id,
          edited_by_full_name: currentUser.fullName || '',
          question_id: questionId,
          question_text: results[resultIndex].question,
          category: results[resultIndex].category,
        });
        
        // Update local state to show dislike icon immediately
        resultsRef.current = latestResults;
        setLocalResults(latestResults);
        onUpdateFeedback(resultIndex, pairIndex, "down");
        
        // Recalculate accuracy after automatic dislike (excluding N/A questions)
        const applicableResults = latestResults.filter((r: AnalysisResult) => 
          !r.pairs.some(p => p.is_not_applicable === true)
        );
        
        // Count all individual answers with feedback (answer-level accuracy)
        let totalAnswers = 0;
        let likedAnswers = 0;
        
        applicableResults.forEach((r: AnalysisResult) => {
          r.pairs.forEach(p => {
            if (p.feedback === "up" || p.feedback === "down") {
              totalAnswers++;
              if (p.feedback === "up") {
                likedAnswers++;
              }
            }
          });
        });
        
        if (totalAnswers > 0) {
          const feedbackAccuracy = (likedAnswers / totalAnswers) * 100;
          
          setAccuracy(feedbackAccuracy);
          setIsInitialAccuracy(false);
          
          // Update final_accuracy in database if all applicable questions have feedback
          const allQuestionsHaveFeedback = applicableResults.every((r: AnalysisResult) =>
            r.pairs.some(p => p.feedback === "up" || p.feedback === "down")
          );
          
          if (allQuestionsHaveFeedback && processingRecordId) {
            await apiClient.updateProjectById(processingRecordId, { final_accuracy: feedbackAccuracy });
          }
        }
      }

      // Mark dirty for unsaved changes protection
      markDirty("normalized_answer_edited", { resultIndex, pairIndex, newValue: editValue });
      
      toast({
        title: "Edit Saved",
        description: "Your changes have been saved and marked as needing review.",
      });
    } catch (error) {
      console.error('Error saving edit:', error);
      toast({
        title: "Save Failed",
        description: "Failed to save edit. Please try again.",
        variant: "destructive",
      });
    }

    setEditingKey(null);
  };

  const handleEditCancel = () => {
    setEditingKey(null);
    setEditValue("");
    setDeflectionDialogOpen(false);
    setDeflectionEditContext(null);
  };

  const toggleFeedback = async (resultIndex: number, pairIndex: number, feedbackType: "up" | "down") => {
    if (!currentUser) {
      toast({
        title: "Authentication Required",
        description: "Please sign in to provide feedback.",
        variant: "destructive",
      });
      return;
    }

    const loadingKey = `${resultIndex}-${pairIndex}-${feedbackType}`;
    const pair = resultsRef.current[resultIndex].pairs[pairIndex];
    const currentFeedback = pair.feedback;
    const newFeedback = currentFeedback === feedbackType ? null : feedbackType;
    
    // Store previous state for rollback (use ref for latest state)
    const previousResults = JSON.parse(JSON.stringify(resultsRef.current));
    
    // CRITICAL: Build updated results with feedback change
    const latestResults = JSON.parse(JSON.stringify(resultsRef.current));
    latestResults[resultIndex].pairs[pairIndex] = {
      ...latestResults[resultIndex].pairs[pairIndex],
      feedback: newFeedback
    };
    
    // Synchronously update BOTH localResults AND resultsRef for immediate UI feedback
    resultsRef.current = latestResults;
    setLocalResults(latestResults);
    
    // Set loading state
    setFeedbackLoading(prev => ({ ...prev, [loadingKey]: true }));
    
    // Mark dirty for unsaved changes protection
    markDirty("feedback_changed", { resultIndex, pairIndex, newFeedback });
    
    // Also notify parent to update its state (for consistency)
    onUpdateFeedback(resultIndex, pairIndex, newFeedback);
    
    try {
      const result = resultsRef.current[resultIndex];
      const key = `${resultIndex}-${pairIndex}`;
      
      // Persist to database using the latest merged state
      await apiClient.updateProjectByHash(projectHash, {
        results: latestResults,
        is_edited: true,
      });

      // Create audit log entry
      await apiClient.createResultEdit({
        project_hash: projectHash,
        row_id: key,
        column_name: "Feedback",
        old_value: currentFeedback || "none",
        new_value: newFeedback || "none",
        edited_by_user_id: currentUser.id,
        edited_by_full_name: currentUser.fullName || '',
        question_id: resultIndex + 1,
        question_text: result.question,
        category: result.category,
      });
      
      // Recalculate accuracy after feedback change (excluding N/A questions)
      const applicableResults = latestResults.filter((r: AnalysisResult) => 
        !r.pairs.some(p => p.is_not_applicable === true)
      );
      
      // Count all individual answers with feedback (answer-level accuracy)
      let totalAnswers = 0;
      let likedAnswers = 0;
      
      applicableResults.forEach((r: AnalysisResult) => {
        r.pairs.forEach(p => {
          if (p.feedback === "up" || p.feedback === "down") {
            totalAnswers++;
            if (p.feedback === "up") {
              likedAnswers++;
            }
          }
        });
      });
      
      if (totalAnswers > 0) {
        const feedbackAccuracy = (likedAnswers / totalAnswers) * 100;
        
        setAccuracy(feedbackAccuracy);
        setIsInitialAccuracy(false);
        
        // Update final_accuracy in database if all applicable questions have feedback
        const allQuestionsHaveFeedback = applicableResults.every((r: AnalysisResult) =>
          r.pairs.some(p => p.feedback === "up" || p.feedback === "down")
        );
        
        if (allQuestionsHaveFeedback && processingRecordId) {
          await apiClient.updateProjectById(processingRecordId, { final_accuracy: feedbackAccuracy });
        }
      }

      // Toast notification suppressed for feedback actions
      
    } catch (error) {
      console.error('Error saving feedback:', error);
      
      // Rollback optimistic update - restore both local state and ref
      resultsRef.current = previousResults;
      setLocalResults(previousResults);
      onUpdateFeedback(resultIndex, pairIndex, previousResults[resultIndex].pairs[pairIndex].feedback);
      
      toast({
        title: "Couldn't save feedback",
        description: "Please try again.",
        variant: "destructive",
      });
    } finally {
      setFeedbackLoading(prev => {
        const newState = { ...prev };
        delete newState[loadingKey];
        return newState;
      });
    }
  };

  const handleDeleteClick = (resultIndex: number, pairIndex: number) => {
    setPendingDelete({ resultIndex, pairIndex });
    setDeleteDialogOpen(true);
  };

  // PDF visibility toggle state
  const [showPdfViewer, setShowPdfViewer] = useState(true);

  const confirmDelete = () => {
    if (pendingDelete) {
      handleDeleteAnswer(pendingDelete.resultIndex, pendingDelete.pairIndex);
    }
  };

  const cancelDelete = () => {
    setDeleteDialogOpen(false);
    setPendingDelete(null);
  };

  const handleDeleteAnswer = async (resultIndex: number, pairIndex: number) => {
    if (!currentUser) {
      toast({
        title: "Authentication Required",
        description: "You must be signed in to delete answers.",
        variant: "destructive",
      });
      return;
    }

    const pair = results[resultIndex].pairs[pairIndex];
    const now = new Date().toISOString();

    // Mark as deleted
    pair.deleted = true;
    pair.deleted_by = currentUser.fullName;
    pair.deleted_at = now;

    // Update local state
    const key = `${resultIndex}-${pairIndex}`;
    setDeletedAnswers({ ...deletedAnswers, [key]: true });
    
    // Mark dirty for unsaved changes protection
    markDirty("deletion_changed", { resultIndex, pairIndex, action: "deleted" });

    // Update database
    try {
      const updatedResults = [...results];
      await apiClient.updateProjectById(processingRecordId, {
        results: updatedResults,
      });

      // Backend handles audit logs automatically

      toast({
        title: "Answer Deleted",
        description: "Click Undo to restore this answer.",
      });
    } catch (error) {
      console.error('Error deleting answer:', error);
      toast({
        title: "Error",
        description: "Failed to delete answer",
        variant: "destructive",
      });
    }

    setDeleteDialogOpen(false);
    setPendingDelete(null);
  };

  const handleRestoreDeletedAnswer = async (resultIndex: number, pairIndex: number) => {
    if (!currentUser) {
      toast({
        title: "Authentication Required",
        description: "You must be signed in to restore answers.",
        variant: "destructive",
      });
      return;
    }

    const pair = results[resultIndex].pairs[pairIndex];
    const now = new Date().toISOString();

    // Mark as restored
    pair.deleted = false;
    pair.restored_by = currentUser.fullName;
    pair.restored_at = now;

    // Mark dirty for unsaved changes protection
    markDirty("restore_answer", { resultIndex, pairIndex });
    
    // Update local state
    const key = `${resultIndex}-${pairIndex}`;
    const updatedDeletedAnswers = { ...deletedAnswers };
    delete updatedDeletedAnswers[key];
    setDeletedAnswers(updatedDeletedAnswers);

    // Update database
    try {
      const updatedResults = [...results];
      await apiClient.updateProjectById(processingRecordId, {
        results: updatedResults,
      });

      // Backend handles audit logs automatically

      toast({
        title: "Answer Restored",
        description: "The answer has been restored successfully.",
      });
    } catch (error) {
      console.error('Error restoring answer:', error);
      toast({
        title: "Error",
        description: "Failed to restore answer",
        variant: "destructive",
      });
    }
  };

  const handleExcludeAnswer = async (resultIndex: number, pairIndex: number) => {
    if (!currentUser) {
      toast({
        title: "Authentication Required",
        description: "Please sign in to exclude answers.",
        variant: "destructive",
      });
      return;
    }

    const key = `${resultIndex}-${pairIndex}`;
    const result = results[resultIndex];
    
    // Call parent handler to update state immutably
    onExcludeAnswer(resultIndex, pairIndex, currentUser);
    
    // Mark dirty for unsaved changes protection
    markDirty("exclusion_changed", { resultIndex, pairIndex, action: "excluded" });
    
    // Update local state
    setExcludedAnswers(prev => ({ ...prev, [key]: true }));
    
    // Save to database
    await apiClient.updateProjectByHash(projectHash, {
      results: results,
      is_edited: true,
    });

    // Create audit log entry
    await apiClient.createResultEdit({
      project_hash: projectHash,
      row_id: key,
      column_name: "Conflict Resolution",
      old_value: "included",
      new_value: "excluded",
      edited_by_user_id: currentUser.id,
      edited_by_full_name: currentUser?.fullName || '',
      question_id: resultIndex + 1,
      question_text: result.question,
      category: result.category,
    });

    toast({
      title: "Answer Excluded",
      description: "This answer has been marked as excluded.",
    });
  };

  const handleIncludeAnswer = async (resultIndex: number, pairIndex: number) => {
    if (!currentUser) {
      toast({
        title: "Authentication Required",
        description: "You must be logged in to restore answers.",
        variant: "destructive",
      });
      return;
    }

    const result = results[resultIndex];
    const key = `${resultIndex}-${pairIndex}`;
    
    // Call parent handler to update state immutably
    onIncludeAnswer(resultIndex, pairIndex, currentUser);
    
    // Update local state
    setExcludedAnswers(prev => {
      const newState = { ...prev };
      delete newState[key];
      return newState;
    });
    
    // Mark dirty for unsaved changes protection
    markDirty("exclusion_changed", { resultIndex, pairIndex, action: "included" });
    
    // Save to database
    await apiClient.updateProjectById(processingRecordId, {
      results: results,
      updated_at: new Date().toISOString(),
    });

    // Create audit log
    await apiClient.createResultEdit({
      project_hash: projectHash,
      row_id: key,
      column_name: "Conflict Resolution",
      old_value: "excluded",
      new_value: "restored",
      edited_by_user_id: currentUser.id,
      edited_by_full_name: currentUser?.fullName || '',
      question_id: resultIndex + 1,
      question_text: result.question,
      category: result.category,
    });

    toast({
      title: "Answer Included",
      description: "This answer has been marked as the selected answer.",
    });
  };

  const handleSelectAnswer = async (resultIndex: number, pairIndex: number) => {
    if (!currentUser) {
      toast({
        title: "Authentication Required",
        description: "Please sign in to select answers.",
        variant: "destructive",
      });
      return;
    }

    const key = `${resultIndex}-${pairIndex}`;
    const result = results[resultIndex];
    const pair = result.pairs[pairIndex];
    
    // If already selected, do nothing
    if (pair.is_selected && !pair.excluded) {
      return;
    }
    
    // Call parent handler to update state immutably
    onSelectAnswer(resultIndex, pairIndex);
    
    // Update local state
    setExcludedAnswers(prev => {
      const newState = { ...prev };
      delete newState[key];
      return newState;
    });
    
    // Mark dirty for unsaved changes protection
    markDirty("selection_changed", { resultIndex, pairIndex });
    
    // Save to database
    await apiClient.updateProjectByHash(projectHash, {
      results: results,
      is_edited: true,
    });

    // Create audit log entry
    await apiClient.createResultEdit({
      project_hash: projectHash,
      row_id: key,
      column_name: "Conflict Resolution",
      old_value: null,
      new_value: "selected as primary answer",
      edited_by_user_id: currentUser.id,
      edited_by_full_name: currentUser?.fullName || '',
      question_id: resultIndex + 1,
      question_text: result.question,
      category: result.category,
    });

    toast({
      title: "Answer Selected",
      description: "This answer has been marked as the primary answer.",
    });
  };

  // Check if all results have feedback
  const allResultsHaveFeedback = results.every(result => 
    deduplicatePairs(result.pairs).some(pair => pair.feedback === "up" || pair.feedback === "down")
  );

  // Handle submit for review button click - show confirmation dialog
  const handleSubmitForReviewClick = () => {
    if (!allResultsHaveFeedback) {
      toast({
        title: "Feedback Required",
        description: "Please provide feedback (👍 or 👎) for all questions before submitting.",
        variant: "destructive",
      });
      return;
    }
    setSubmitConfirmOpen(true);
  };

  // Handle publish directly button click - show confirmation dialog
  const handlePublishDirectlyClick = () => {
    if (!allResultsHaveFeedback) {
      toast({
        title: "Feedback Required",
        description: "Please provide feedback (👍 or 👎) for all questions before publishing.",
        variant: "destructive",
      });
      return;
    }
    setPublishDirectConfirmOpen(true);
  };

  // Handle submission after confirmation (directPublish = true bypasses Waiting for Approval)
  const handleSubmit = async (directPublish: boolean = false) => {
    if (!allResultsHaveFeedback) {
      toast({
        title: "Feedback Required",
        description: "Please provide feedback (👍 or 👎) for all questions before submitting.",
        variant: "destructive",
      });
      return;
    }

    // For direct publish, clear any selected supervisor
    const effectiveSupervisorId = directPublish ? null : (selectedSupervisor || null);
    const effectiveSupervisorName = directPublish ? null : (selectedSupervisor ? supervisors.find(s => s.user_id === selectedSupervisor)?.full_name : null);

    setIsSubmitting(true);
    try {
      // Backfill edit metadata from audit records for any edited rows missing info
      const updatedResults = await Promise.all(results.map(async (result, idx) => {
        const uniquePairs = await Promise.all(deduplicatePairs(result.pairs).map(async (pair, pairIdx) => {
          const rowId = `${idx}-${pairIdx}`;
          const rowEdits = editHistory[rowId] || [];
          
          if (rowEdits.length > 0 && (!pair.last_edited_by_full_name || !pair.last_edited_changes)) {
            // Backfill from latest edit records
            const latestEdit = rowEdits[0];
            
            // Build changes object from all edits for this row
            const changes: any = {};
            rowEdits.forEach(edit => {
              if (!changes[edit.column_name]) {
                changes[edit.column_name] = {
                  old: edit.old_value,
                  new: edit.new_value
                };
              }
            });
            
            return {
              ...pair,
              is_edited: true,
              last_edited_by_full_name: latestEdit.edited_by_full_name,
              last_edited_at: latestEdit.edited_at,
              last_edited_changes: changes,
            };
          }
          
          return pair;
        }));
        
        return {
          ...result,
          pairs: uniquePairs,
        };
      }));
      
      // NO RECOMPUTATION: Freeze values as-is from current UI state
      const frozenResults = updatedResults.map((result, idx) => {
        const questionId = idx + 1;
        return {
          ...result,
          pairs: result.pairs.map(pair => ({
            ...pair,
            // Use existing values or empty string (no fallback to recomputation)
            normalizedAnswer: pair.normalizedAnswer || "",
            unit: pair.unit || "",
          }))
        };
      });

      // Create submitted snapshot: exact UI state as JSON (compute normalized_answer and unit for ALL rows)
      const submittedSnapshotJson = frozenResults.map((result, idx) => {
        const uniquePairs = deduplicatePairs(result.pairs, idx);
        return uniquePairs.map((pair, pairIdx) => {
          // CRITICAL: Compute normalized_answer and unit for ALL rows, not just edited ones
          const normalizedAnswer = pair.normalizedAnswer || normalizeAnswer(pair.answer, idx + 1);
          const unit = pair.unit || extractUnit(pair.answer, idx + 1);
          
          // Build edited_details from edit history for audit log
          const rowId = `${idx}-${pairIdx}`;
          const rowEdits = editHistory[rowId] || [];
          const editedDetails = rowEdits.map(edit => ({
            column_name: edit.column_name,
            old_value: edit.old_value,
            new_value: edit.new_value,
            edited_by_full_name: edit.edited_by_full_name,
            edited_at: edit.edited_at,
          }));
          
          return {
            row_id: `${idx}-${pairIdx}`,
            question_id: idx + 1,
            category: result.category,
            question: result.question,
            extracted_answer: displayAnswer(pair.answer),
            normalized_answer: displayAnswer(normalizedAnswer),
            unit: unit,
            reference: displayAnswer(pair.reference),
            confidence: pair.confidence ? (typeof pair.confidence === 'number' ? formatConfidence(pair.answer, pair.confidence) : pair.confidence) : "",
            feedback: pair.feedback === "up" ? "up" : pair.feedback === "down" ? "down" : "",
            is_edited: pair.is_edited || false,
            last_edited_by_full_name: pair.last_edited_by_full_name || "",
            last_edited_at: pair.last_edited_at || null,
            edited_details: editedDetails,
            excluded: pair.excluded || false,
            excluded_by: pair.excluded_by || null,
            excluded_at: pair.excluded_at || null,
            restored_by: pair.restored_by || null,
            restored_at: pair.restored_at || null,
            deleted: pair.deleted || false,
            deleted_by: pair.deleted_by || null,
            deleted_at: pair.deleted_at || null,
            is_selected: pair.is_selected || false,
            // N/A fields - include all metadata for persistence across stages
            is_not_applicable: pair.is_not_applicable || false,
            not_applicable_by: pair.not_applicable_by || null,
            not_applicable_at: pair.not_applicable_at || null,
            not_applicable_restored_by: pair.not_applicable_restored_by || null,
            not_applicable_restored_at: pair.not_applicable_restored_at || null,
          };
        });
      }).flat();

      // Block submission if snapshot is empty
      if (!submittedSnapshotJson || submittedSnapshotJson.length === 0) {
        throw new Error("Cannot submit: No results to submit. Please ensure all questions are answered.");
      }

      console.log(`Submitting project: ${projectHash}, snapshot rows: ${submittedSnapshotJson.length}, hasEdits: ${hasEdits}`);

      // Generate submitted snapshot HTML
      const submittedSnapshotHtml = generateSnapshotHtml(submittedSnapshotJson, projectName);
      
      console.log(`Generated snapshot HTML length: ${submittedSnapshotHtml.length}`);

      // Prepare results for submission (use snapshot as-is)
      const submissionResults = submittedSnapshotJson;

      // Prepare feedback data
      const feedbackData = results.map((result, idx) => ({
        question_id: idx + 1,
        question: result.question,
        feedback: deduplicatePairs(result.pairs).map(pair => ({
          answer: displayAnswer(pair.answer),
          feedback: pair.feedback,
        })),
      }));

      const data = await apiClient.submitProjectForApproval({
        projectHash,
        projectId,
        projectName,
        results: submissionResults,
        feedback: feedbackData,
        hasEdits,
        supervisorId: effectiveSupervisorId,
        supervisorName: effectiveSupervisorName,
        directPublish, // New parameter for direct publishing
        pendingSnapshotJson: submittedSnapshotJson,
        pendingSnapshotHtml: submittedSnapshotHtml,
        processingTimeSeconds: processingTimeSeconds,
        initialAccuracy: isInitialAccuracy ? accuracy : undefined,
      });

      // Get signed URLs for download
      const csvPath = data.csv_path;
      const jsonPath = data.json_path;

      const csvUrlData = await apiClient.getPresignedUrl(csvPath);
      const jsonUrlData = await apiClient.getPresignedUrl(jsonPath);

      setDownloadLinks({
        csv: csvUrlData?.signed_url,
        json: jsonUrlData?.signed_url,
      });

      setIsSubmitted(true);
      markAsSaved(); // Clear unsaved changes after successful submission
      
      const successMessage = directPublish 
        ? "✅ Results published to Approved Projects"
        : effectiveSupervisorId
          ? "✅ Submitted for supervisor approval"
          : "✅ Submitted to Waiting for Approval";
      const description = directPublish
        ? "Viewable anytime in Approved Projects."
        : effectiveSupervisorId
          ? `Assigned to ${effectiveSupervisorName} for review.`
          : "Project is waiting for review in Waiting for Approval.";
      
      toast({
        title: successMessage,
        description,
      });
      
      // Refresh to show the newly submitted project in history if ProjectsHistory is mounted
      window.dispatchEvent(new Event('project-submitted'));
      
      // Navigate back to main Projects UI after successful submission
      onSubmitSuccess?.();
    } catch (error) {
      console.error("Submission error:", error);
      toast({
        title: "Submission Failed",
        description: error instanceof Error ? error.message : "Failed to submit results. Please try again.",
        variant: "destructive",
      });
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleDownload = (url: string | undefined, filename: string) => {
    if (!url) return;
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  return (
    <div className="w-full">
      {/* Analysis Results - Optimized Two Column Layout */}
      <div className="mb-4">
        <Card className="bg-gradient-card border-border shadow-card animate-slide-up w-full">
          <div className="p-6">
            {/* Header with Metrics */}
            <div className="flex items-center justify-between mb-6 flex-wrap gap-4">
              <h2 className="text-2xl font-bold text-foreground">Analysis Results</h2>
              <div className="flex items-center gap-3 flex-wrap">
                <TooltipProvider>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <div className="flex items-center gap-2 px-3 py-2 bg-green-500 rounded-lg whitespace-nowrap cursor-help shadow-sm">
                        <span className="text-sm font-medium text-black">Accuracy:</span>
                        <span className="text-xl font-bold text-black">{accuracy.toFixed(1)}%</span>
                        {isInitialAccuracy && (
                          <span className="text-xs text-black/70">(initial)</span>
                        )}
                      </div>
                    </TooltipTrigger>
                    <TooltipContent>
                      <p className="text-sm">
                        {isInitialAccuracy 
                          ? "Based on average AI confidence scores. Provide feedback to update."
                          : "Based on your like/dislike feedback"}
                      </p>
                    </TooltipContent>
                  </Tooltip>
                </TooltipProvider>
                <div className="flex items-center gap-2 px-3 py-2 bg-blue-500 rounded-lg whitespace-nowrap shadow-sm">
                  <span className="text-sm font-medium text-black">Processing Time:</span>
                  <span className="text-lg font-bold text-black">
                    {displayProcessingTime > 0 ? formatProcessedTime(displayProcessingTime) : 'Processing time unavailable'}
                  </span>
                </div>
              </div>
            </div>
            
            {/* Project Details - Side by Side */}
            <div className="space-y-4 bg-muted/30 rounded-lg p-4 border border-border">
              <h3 className="text-lg font-semibold text-foreground">Project Details</h3>
              
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="space-y-1.5">
                  <Label htmlFor="project-id" className="text-sm font-medium">
                    Project ID:
                  </Label>
                  <Input
                    id="project-id"
                    type="text"
                    value={projectId}
                    onChange={(e) => onProjectIdChange(e.target.value)}
                    placeholder="Enter project ID"
                    className="h-10"
                    disabled={isSubmitted}
                  />
                </div>
                
                <div className="space-y-1.5">
                  <Label htmlFor="project-name" className="text-sm font-medium">
                    Project Name:
                  </Label>
                  <Input
                    id="project-name"
                    type="text"
                    value={projectName}
                    onChange={(e) => onProjectNameChange(e.target.value)}
                    placeholder="Enter project name"
                    className="h-10"
                    disabled={isSubmitted}
                  />
                </div>
              </div>
            </div>

            {/* Unsaved Changes Indicator */}
            {hasUnsavedChanges && lastSavedAt && (
              <div className="flex items-center gap-2 text-xs text-muted-foreground bg-muted/30 rounded-md px-3 py-2 mt-4">
                <Save className="h-3 w-3" />
                <span>Last saved at {lastSavedAt.toLocaleTimeString()}</span>
              </div>
            )}
            {hasUnsavedChanges && !lastSavedAt && (
              <div className="flex items-center gap-2 text-xs text-yellow-600 dark:text-yellow-400 bg-yellow-50 dark:bg-yellow-900/20 rounded-md px-3 py-2 mt-4">
                <Save className="h-3 w-3 animate-pulse" />
                <span>Unsaved changes - Auto-saving...</span>
              </div>
            )}
            
            {/* Download Buttons (only shown after submission) */}
            {isSubmitted && (
              <div className="flex gap-2 flex-wrap pt-4">
                <Button
                  onClick={() => handleDownload(downloadLinks.csv, `${projectId}_${projectName}.csv`)}
                  variant="outline"
                  className="gap-2"
                  disabled={!downloadLinks.csv}
                >
                  <Download className="h-4 w-4" />
                  Download CSV
                </Button>
                <Button
                  onClick={() => handleDownload(downloadLinks.json, `${projectId}_${projectName}.json`)}
                  variant="outline"
                  className="gap-2"
                  disabled={!downloadLinks.json}
                >
                  <Download className="h-4 w-4" />
                  Download JSON
                </Button>
              </div>
            )}
          </div>
        </Card>
      </div>

      {/* Two Column Layout: Extracted Results + PDF Viewer */}
      <div className={`grid gap-4 items-start ${showPdfViewer ? 'grid-cols-1 xl:grid-cols-[1.2fr_1fr]' : 'grid-cols-1'}`}>
        {/* Left Column: Extracted Results */}
        <div className="h-[calc(100vh-8rem)] flex flex-col overflow-hidden">
          {/* Results Table Card */}
          <Card className="bg-gradient-card border-border shadow-card animate-slide-up w-full h-full flex flex-col">
            <div className="p-4 flex justify-between items-center flex-shrink-0">
              <h3 className="text-xl font-bold text-foreground">Extracted Results</h3>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setShowPdfViewer(!showPdfViewer)}
                className="gap-2"
              >
                {showPdfViewer ? "Expand" : "Compact"}
              </Button>
            </div>
            <Separator />
            {/* Outer wrapper for rounded corner clipping at bottom */}
            <div className="flex-1 overflow-hidden rounded-b-lg">
              <div className="w-full overflow-auto h-full">
                <table className="w-full border-collapse text-sm table-fixed">
            <thead className="sticky top-0 bg-background/95 backdrop-blur-sm z-10">
              <tr className="border-b border-border">
                <th className="text-left p-3 font-semibold text-foreground w-[10%]">Category</th>
                <th className="text-left p-3 font-semibold text-foreground w-[17%]">Question</th>
                <th className="text-left p-3 font-semibold text-foreground w-[13%]">Extracted Answer</th>
                <th className="text-left p-3 font-semibold text-foreground w-[15%]">Normalized Answer</th>
                <th className="text-left p-3 font-semibold text-foreground w-[6%]">Unit</th>
                <th className="text-left p-3 font-semibold text-foreground w-[13%]">Reference</th>
                <th className="text-left p-3 font-semibold text-foreground w-[11%]">AI Extraction Accuracy</th>
                <th className="text-left p-3 font-semibold text-foreground w-[15%]">Remarks</th>
              </tr>
            </thead>
            <tbody>
              {localResults.map((result, resultIndex) => {
                const uniquePairs = deduplicatePairs(result.pairs, resultIndex);
                const hasMultipleAnswers = uniquePairs.length > 1;
                
                // Check if any answer has been explicitly selected in this result
                const hasExplicitSelection = hasMultipleAnswers && result.pairs.some(p => p.is_selected === true && !p.excluded && !p.deleted);
                
                // Check if this entire question is marked as Not Applicable
                const isNotApplicable = result.pairs.some(p => p.is_not_applicable === true);
                
                return uniquePairs.map((pair, displayIndex) => {
                  // CRITICAL: Use originalPairIndex for all database operations and state lookups
                  const originalPairIndex = pair.originalPairIndex;
                  const isExcluded = excludedAnswers[`${resultIndex}-${originalPairIndex}`] || pair.excluded;
                  const isDeleted = deletedAnswers[`${resultIndex}-${originalPairIndex}`] || pair.deleted;
                  const isSelected = pair.is_selected === true;
                  const editKey = `${resultIndex}-${originalPairIndex}`;
                  const rowId = editKey;
                  const isFirstPair = displayIndex === 0;
                  // Use external edit history if provided (from SupervisorReview), otherwise use local state
                  const effectiveEditHistory = externalEditHistory ?? editHistory;
                  const rowEdits = effectiveEditHistory[rowId] || [];
                  // Show pencil icon only when Normalized Answer has been edited
                  const hasEdits = rowEdits.some(edit => edit.column_name === "Normalized Answer");
                  
                  // Compute if this answer should show as unselected (grey italic) in multi-answer context
                  const isUnselectedAlternative = hasMultipleAnswers && !isExcluded && !isDeleted && 
                    (hasExplicitSelection ? !isSelected : !isFirstPair);
                  
                  return (
                    <tr 
                      key={editKey}
                      className={`border-b border-border transition-all duration-200 ease-in-out ${
                        isNotApplicable
                          ? 'bg-gray-100 dark:bg-gray-800/30'
                          : isDeleted 
                          ? 'bg-red-50/50 dark:bg-red-900/10' 
                          : isExcluded 
                          ? 'bg-amber-50/50 dark:bg-amber-900/10' 
                          : isUnselectedAlternative
                          ? 'bg-[#f2f2f2] dark:bg-gray-800/50'
                          : 'hover:bg-background/50'
                      }`}
                    >
                      {isFirstPair && (
                        <>
                          <td 
                            className={`p-3 align-top border-r border-border ${
                              isNotApplicable ? 'text-[#888888] dark:text-gray-500 line-through' : 'text-muted-foreground'
                            }`}
                            rowSpan={uniquePairs.length}
                          >
                            {result.category}
                          </td>
                          <td 
                            className={`p-3 align-top font-medium border-r border-border ${
                              isNotApplicable ? 'text-[#888888] dark:text-gray-500' : 'text-foreground'
                            }`}
                            rowSpan={uniquePairs.length}
                          >
                            <div className="flex items-start gap-2">
                              {/* X button on the left side */}
                              <div className="flex items-center gap-1 flex-shrink-0 pt-0.5">
                                {!isSubmitted && !isNotApplicable && onMarkNotApplicable && (
                                  <TooltipProvider>
                                    <Tooltip>
                                      <TooltipTrigger asChild>
                                        <Button
                                          size="sm"
                                          variant="ghost"
                                          className="h-5 w-5 p-0 text-muted-foreground hover:text-red-500"
                                          onClick={() => {
                                            // Mark dirty BEFORE calling parent callback to ensure autosave triggers
                                            markDirty("question_applicability_changed", { resultIndex, value: true });
                                            onMarkNotApplicable(resultIndex);
                                          }}
                                        >
                                          <X className="h-3 w-3" />
                                        </Button>
                                      </TooltipTrigger>
                                      <TooltipContent>
                                        <p>Mark as Not Applicable</p>
                                      </TooltipContent>
                                    </Tooltip>
                                  </TooltipProvider>
                                )}
                                {/* Restore button to undo Not Applicable */}
                                {!isSubmitted && isNotApplicable && onRestoreApplicable && (
                                  <TooltipProvider>
                                    <Tooltip>
                                      <TooltipTrigger asChild>
                                        <Button
                                          size="sm"
                                          variant="ghost"
                                          className="h-5 w-5 p-0 text-green-600 hover:text-green-700"
                                          onClick={() => {
                                            // Mark dirty BEFORE calling parent callback to ensure autosave triggers
                                            markDirty("question_applicability_changed", { resultIndex, value: false });
                                            onRestoreApplicable(resultIndex);
                                          }}
                                        >
                                          <RotateCcw className="h-3 w-3" />
                                        </Button>
                                      </TooltipTrigger>
                                      <TooltipContent>
                                        <p>Restore question</p>
                                      </TooltipContent>
                                    </Tooltip>
                                  </TooltipProvider>
                                )}
                              </div>
                              <div className={`flex-1 ${isNotApplicable ? 'line-through' : ''}`}>
                                <span className="flex items-center gap-2">
                                  {cleanQuestionText(result.question, resultIndex + 1)}
                                  {isNotApplicable && (
                                    <Badge variant="outline" className="text-xs bg-gray-200 dark:bg-gray-700 text-[#888888] dark:text-gray-400">
                                      N/A
                                    </Badge>
                                  )}
                                </span>
                              </div>
                            </div>
                          </td>
                        </>
                      )}
                      <td 
                        className={`p-3 align-top break-words transition-all duration-300 ${
                          isNotApplicable ? 'text-[#888888] dark:text-gray-500 italic bg-gray-100 dark:bg-gray-800/30 line-through' :
                          isDeleted ? 'text-[#888888] dark:text-gray-500 italic bg-[#f2f2f2] dark:bg-gray-800/50' : 
                          isExcluded ? 'text-[#888888] dark:text-gray-500 italic bg-[#f2f2f2] dark:bg-gray-800/50' : 
                          isUnselectedAlternative ? 'text-[#888888] dark:text-gray-500 italic' :
                          'text-foreground'
                        }`}
                        title={
                          isNotApplicable 
                            ? 'This question has been marked as Not Applicable'
                            : isExcluded && pair.excluded_by && pair.excluded_at 
                            ? `This answer was excluded by ${pair.excluded_by} on ${new Date(pair.excluded_at).toLocaleString()}`
                            : isDeleted && pair.deleted_by && pair.deleted_at
                            ? `This answer was deleted by ${pair.deleted_by} on ${new Date(pair.deleted_at).toLocaleString()}`
                            : ''
                        }
                      >
                        <div className="p-2 max-w-full">
                          {displayAnswer(pair.answer)}
                        </div>
                      </td>
                      <td 
                        className={`p-3 align-top break-words transition-all duration-300 ${
                          isNotApplicable ? 'text-[#888888] dark:text-gray-500 italic bg-gray-100 dark:bg-gray-800/30 line-through' :
                          isDeleted ? 'text-[#888888] dark:text-gray-500 italic bg-[#f2f2f2] dark:bg-gray-800/50' : 
                          isExcluded ? 'text-[#888888] dark:text-gray-500 italic bg-[#f2f2f2] dark:bg-gray-800/50' : 
                          isUnselectedAlternative ? 'text-[#888888] dark:text-gray-500 italic' :
                          'text-foreground'
                        }`}
                        title={
                          isNotApplicable 
                            ? 'This question has been marked as Not Applicable'
                            : isExcluded && pair.excluded_by && pair.excluded_at 
                            ? `This answer was excluded by ${pair.excluded_by} on ${new Date(pair.excluded_at).toLocaleString()}`
                            : isDeleted && pair.deleted_by && pair.deleted_at
                            ? `This answer was deleted by ${pair.deleted_by} on ${new Date(pair.deleted_at).toLocaleString()}`
                            : ''
                        }
                      >
                        <div className="flex items-start gap-2">
                          {/* Verification Checkmark */}
                          <VerificationCheckmark
                            isEdited={hasEdits}
                            isSelected={!hasMultipleAnswers || (!isExcluded && !isDeleted && (hasExplicitSelection ? isSelected : isFirstPair))}
                            isExcluded={isExcluded}
                            isDeleted={isDeleted}
                            hasMultipleAnswers={hasMultipleAnswers}
                            onClick={() => onSelectAnswer(resultIndex, originalPairIndex)}
                            isClickable={hasMultipleAnswers && !isDeleted && (isExcluded || isUnselectedAlternative) && !isSubmitted}
                            excludedBy={pair.excluded_by}
                            excludedAt={pair.excluded_at}
                            deletedBy={pair.deleted_by}
                            deletedAt={pair.deleted_at}
                          />
                          
                          {/* Existing answer content */}
                          <div className="flex-1 min-w-0">
                            {editingKey === `norm-${editKey}` && !isExcluded ? (
                              // Check if this is deflection criteria (questions 3-7)
                              (resultIndex >= 2 && resultIndex <= 6) ? (
                                <div className="p-2">
                                  <span className="text-xs text-muted-foreground">Editing in dialog...</span>
                                </div>
                              ) : (
                                <div className="space-y-2">
                                  <Textarea
                                    value={editValue}
                                    onChange={(e) => setEditValue(e.target.value)}
                                    className="min-h-[60px] text-xs"
                                    autoFocus
                                  />
                                  <div className="flex gap-2">
                                    <Button
                                      size="sm"
                                      onClick={() => handleEditSave(resultIndex, originalPairIndex)}
                                    >
                                      Save
                                    </Button>
                                    <Button
                                      size="sm"
                                      variant="outline"
                                      onClick={handleEditCancel}
                                    >
                                      Cancel
                                    </Button>
                                  </div>
                                </div>
                              )
                            ) : (
                              <div
                                className={isSubmitted || isExcluded || isDeleted ? "p-2 break-words max-w-full" : "cursor-pointer hover:bg-accent/50 p-2 rounded transition-colors break-words max-w-full"}
                                onClick={isSubmitted || isExcluded || isDeleted ? undefined : () => {
                                  const normalizedValue = pair.normalizedAnswer || normalizeAnswer(pair.answer, resultIndex + 1);
                                  setEditingKey(`norm-${editKey}`);
                                  // For questions 3-7, keep original value (DeflectionCriteriaEditor handles it)
                                  // For all other questions, transform "Not Found" to "Not Available"
                                  if (resultIndex >= 2 && resultIndex <= 6) {
                                    setEditValue(normalizedValue);
                                  } else {
                                    setEditValue(displayAnswer(normalizedValue));
                                  }
                                  
                                  // For deflection criteria questions (3-7), open the dialog
                                  if (resultIndex >= 2 && resultIndex <= 6) {
                                    setDeflectionEditContext({ resultIndex, pairIndex: originalPairIndex, value: normalizedValue });
                                    setDeflectionDialogOpen(true);
                                  }
                                }}
                                title={isSubmitted || isExcluded || isDeleted ? "" : "Click to edit"}
                              >
                                {(() => {
                                  const normalizedValue = pair.normalizedAnswer || normalizeAnswer(pair.answer, resultIndex + 1);
                                  // Check if this is deflection criteria JSON (questions 3-7)
                                  if (resultIndex >= 2 && resultIndex <= 6) {
                                    try {
                                      // Try to parse and display in user-friendly format
                                      const parsed = JSON.parse(normalizedValue);
                                      const items = Array.isArray(parsed) ? parsed : [parsed];
                                      
                                      return (
                                        <div className="space-y-3 text-xs">
                                          {items.map((item, idx) => (
                                            <div key={idx} className="bg-muted/30 p-2 rounded space-y-1">
                                              {items.length > 1 && (
                                                <div className="font-semibold text-primary mb-1">Entry {idx + 1}</div>
                                              )}
                                              <div>
                                                <span className="font-medium">Description:</span>{' '}
                                                <span className="text-muted-foreground">{item.Description || '—'}</span>
                                              </div>
                                              <div>
                                                <span className="font-medium">Combination:</span>{' '}
                                                <span className="text-muted-foreground">{item.Combination || '—'}</span>
                                              </div>
                                              <div>
                                                <span className="font-medium">LimitRatio:</span>{' '}
                                                <span className="text-muted-foreground">{item.LimitRatio !== undefined && item.LimitRatio !== null ? item.LimitRatio : '—'}</span>
                                              </div>
                                              <div>
                                                <span className="font-medium">Max:</span>{' '}
                                                <span className="text-muted-foreground">{item.Max !== undefined && item.Max !== null ? item.Max : '—'}</span>
                                              </div>
                                            </div>
                                          ))}
                                        </div>
                                      );
                                    } catch {
                                      // Not valid JSON, display as-is with "Not Available" transformation
                                      return displayAnswer(normalizedValue);
                                    }
                                  }
                                  return displayAnswer(normalizedValue);
                                })()}
                                <EditNoteIndicator
                                  projectHash={projectHash}
                                  rowId={rowId}
                                  questionText={result.question}
                                />
                              </div>
                            )}
                          </div>
                        </div>
                      </td>
                      <td 
                        className={`p-3 align-top break-words transition-all duration-300 ${
                          isNotApplicable ? 'text-[#888888] dark:text-gray-500 italic bg-gray-100 dark:bg-gray-800/30 line-through' :
                          isDeleted ? 'text-[#888888] dark:text-gray-500 italic bg-[#f2f2f2] dark:bg-gray-800/50' : 
                          isExcluded ? 'text-[#888888] dark:text-gray-500 italic bg-[#f2f2f2] dark:bg-gray-800/50' : 
                          isUnselectedAlternative ? 'text-[#888888] dark:text-gray-500 italic' :
                          'text-muted-foreground'
                        }`}
                        title={
                          isNotApplicable 
                            ? 'This question has been marked as Not Applicable'
                            : isExcluded && pair.excluded_by && pair.excluded_at 
                            ? `This answer was excluded by ${pair.excluded_by} on ${new Date(pair.excluded_at).toLocaleString()}`
                            : isDeleted && pair.deleted_by && pair.deleted_at
                            ? `This answer was deleted by ${pair.deleted_by} on ${new Date(pair.deleted_at).toLocaleString()}`
                            : ''
                        }
                      >
                        {pair.unit || extractUnit(pair.answer, resultIndex + 1)}
                      </td>
                      <td 
                        className={`p-3 align-top break-words transition-all duration-300 ${
                          isNotApplicable ? 'text-[#888888] dark:text-gray-500 italic bg-gray-100 dark:bg-gray-800/30 line-through' :
                          isDeleted ? 'text-[#888888] dark:text-gray-500 italic bg-[#f2f2f2] dark:bg-gray-800/50' : 
                          isExcluded ? 'text-[#888888] dark:text-gray-500 italic bg-[#f2f2f2] dark:bg-gray-800/50' : 
                          isUnselectedAlternative ? 'text-[#888888] dark:text-gray-500 italic' :
                          'text-muted-foreground'
                        }`}
                        title={
                          isExcluded && pair.excluded_by && pair.excluded_at 
                            ? `This answer was excluded by ${pair.excluded_by} on ${new Date(pair.excluded_at).toLocaleString()}`
                            : isDeleted && pair.deleted_by && pair.deleted_at
                            ? `This answer was deleted by ${pair.deleted_by} on ${new Date(pair.deleted_at).toLocaleString()}`
                            : ''
                        }
                      >
                        <button
                          onClick={async () => {
                            // Build structured reference using the new utility
                            const ref = buildStructuredReference(
                              { reference: pair.reference, bbox: pair.bbox },
                              pdfUrls.map(pdf => ({ name: pdf.name, url: pdf.url }))
                            );
                            
                            if (!ref) {
                              toast({
                                title: "Invalid Reference",
                                description: "Could not parse page reference",
                                variant: "destructive"
                              });
                              return;
                            }
                            
                            // Set highlights for embedded viewer
                            if (ref.bbox) {
                              setPdfHighlights([{ page: ref.page, ...ref.bbox }]);
                            }
                            
                            // Switch to the correct PDF if needed
                            const needsFileSwitch = ref.fileIndex !== selectedPdfIndex;
                            if (needsFileSwitch) {
                              setSelectedPdfIndex(ref.fileIndex);
                            }
                            
                            // If popout is active, send navigation via BOTH broadcast channel AND direct postMessage
                            if (isPopoutActive) {
                              // Sanitize highlight - only send if all fields are valid numbers
                              const sanitizedHighlight = ref.bbox && 
                                typeof ref.bbox.x === 'number' && !isNaN(ref.bbox.x) &&
                                typeof ref.bbox.y === 'number' && !isNaN(ref.bbox.y) &&
                                typeof ref.bbox.width === 'number' && !isNaN(ref.bbox.width) &&
                                typeof ref.bbox.height === 'number' && !isNaN(ref.bbox.height)
                                ? ref.bbox
                                : undefined;
                              
                              console.log('[MainWindow] Sending NAVIGATE to pop-out:', {
                                fileIndex: ref.fileIndex,
                                page: ref.page,
                                fileName: ref.fileName,
                                highlight: sanitizedHighlight,
                              });
                              
                              // Method 1: BroadcastChannel
                              sendNavigate(
                                ref.fileIndex,
                                ref.page,
                                ref.fileName,
                                sanitizedHighlight
                              );
                              
                              // Method 2: Direct postMessage (fallback/redundancy)
                              sendDirectMessage(projectHash, {
                                type: 'NAVIGATE',
                                payload: {
                                  fileIndex: ref.fileIndex,
                                  page: ref.page,
                                  fileName: ref.fileName,
                                  highlight: sanitizedHighlight,
                                },
                              });
                            }
                            
                            // Navigate embedded viewer
                            // Wait for PDF viewer to be ready
                            const isReady = await waitForPdfReady(5000);
                            
                            if (!isReady) {
                              toast({
                                title: "PDF Not Ready",
                                description: "Please try again in a moment.",
                                variant: "destructive"
                              });
                              return;
                            }
                            
                            // Extra delay if file switch happened
                            if (needsFileSwitch) {
                              await new Promise(resolve => setTimeout(resolve, 200));
                            }
                            
                            executeJumpToPdfLocation(ref.page, ref.bbox);
                          }}
                          className="text-left text-blue-600 hover:text-blue-800 dark:text-blue-400 dark:hover:text-blue-300 hover:underline cursor-pointer transition-colors"
                          title="Click to view in PDF"
                        >
                          {displayAnswer(pair.reference)}
                        </button>
                      </td>
                      <td className="p-3 align-top border-l border-border">
                        <div className="flex gap-1 items-center">
                          {isDeleted ? (
                            <TooltipProvider>
                              <Tooltip>
                                <TooltipTrigger asChild>
                                  <Button
                                    size="sm"
                                    variant="outline"
                                    className="hover:bg-blue-50 hover:text-blue-600 h-7 w-7 p-0"
                                    onClick={() => handleRestoreDeletedAnswer(resultIndex, originalPairIndex)}
                                    title="Undo delete"
                                  >
                                    <RotateCcw className="h-3 w-3" />
                                  </Button>
                                </TooltipTrigger>
                                <TooltipContent>
                                  <p>Undo delete</p>
                                </TooltipContent>
                              </Tooltip>
                            </TooltipProvider>
                           ) : isNotApplicable ? (
                            <TooltipProvider>
                              <Tooltip>
                                <TooltipTrigger asChild>
                                  <span className="text-muted-foreground text-sm cursor-help">🚫</span>
                                </TooltipTrigger>
                                <TooltipContent>
                                  <p>Accuracy rating not applicable for excluded questions</p>
                                </TooltipContent>
                              </Tooltip>
                            </TooltipProvider>
                           ) : (
                            <>
                              <Button
                                size="sm"
                                variant={pair.feedback === "up" ? "default" : "outline"}
                                className={pair.feedback === "up" ? "bg-green-500 hover:bg-green-600 text-white h-7 w-7 p-0" : "hover:bg-accent h-7 w-7 p-0"}
                                onClick={() => toggleFeedback(resultIndex, originalPairIndex, "up")}
                                title="Mark as correct"
                                disabled={isSubmitted || feedbackLoading[`${resultIndex}-${originalPairIndex}-up`]}
                                aria-pressed={pair.feedback === "up"}
                                aria-label="Like - mark as correct"
                              >
                                {feedbackLoading[`${resultIndex}-${originalPairIndex}-up`] ? (
                                  <span className="animate-spin">⏳</span>
                                ) : (
                                  <ThumbsUp className="h-3 w-3" />
                                )}
                              </Button>
                              <Button
                                size="sm"
                                variant={pair.feedback === "down" ? "default" : "outline"}
                                className={pair.feedback === "down" ? "bg-red-500 hover:bg-red-600 text-white h-7 w-7 p-0" : "hover:bg-accent h-7 w-7 p-0"}
                                onClick={() => toggleFeedback(resultIndex, originalPairIndex, "down")}
                                title="Mark as incorrect"
                                disabled={isSubmitted || feedbackLoading[`${resultIndex}-${originalPairIndex}-down`]}
                                aria-pressed={pair.feedback === "down"}
                                aria-label="Dislike - mark as incorrect"
                              >
                                {feedbackLoading[`${resultIndex}-${originalPairIndex}-down`] ? (
                                  <span className="animate-spin">⏳</span>
                                ) : (
                                  <ThumbsDown className="h-3 w-3" />
                                )}
                              </Button>
                              {hasMultipleAnswers && (
                                <Button
                                  size="sm"
                                  variant="outline"
                                  className="hover:bg-red-50 hover:text-red-600 h-7 w-7 p-0"
                                  onClick={() => {
                                    setPendingDelete({ resultIndex, pairIndex: originalPairIndex });
                                    setDeleteDialogOpen(true);
                                  }}
                                  title="Delete answer"
                                  disabled={isSubmitted}
                                >
                                  <Trash2 className="h-3 w-3" />
                                </Button>
                              )}
                            </>
                          )}
                           {hasEdits && (
                            <TooltipProvider>
                              <Tooltip>
                                <TooltipTrigger asChild>
                                  <div className="ml-1 cursor-help">
                                    <span className="text-lg">✏️</span>
                                  </div>
                                </TooltipTrigger>
                                <TooltipContent className="max-w-sm">
                                  <div className="space-y-2 text-xs">
                                    {rowEdits.length > 0 && (
                                      <>
                                        <p className="font-semibold">
                                          Edited by {rowEdits[0].edited_by_full_name}
                                        </p>
                                        <p className="text-muted-foreground">
                                          {new Date(rowEdits[0].edited_at).toLocaleString()}
                                        </p>
                                        <div className="mt-2 space-y-2">
                                          {rowEdits.map((edit, idx) => (
                                            <div key={idx} className="border-b border-border/50 pb-2 last:border-b-0 last:pb-0">
                                              <p className="font-medium">{edit.column_name}:</p>
                                              <p className="text-muted-foreground">
                                                "{edit.old_value}" → "{edit.new_value}"
                                              </p>
                                              {edit.note_text && (
                                                <p className="text-primary mt-1 italic">
                                                  Reason: "{edit.note_text}"
                                                </p>
                                              )}
                                            </div>
                                          ))}
                                        </div>
                                      </>
                                    )}
                                  </div>
                                </TooltipContent>
                              </Tooltip>
                            </TooltipProvider>
                          )}
                        </div>
                      </td>
                      <td className="p-3 align-top">
                        <RemarksColumn
                          projectHash={projectHash}
                          rowId={rowId}
                          canAddRemark={!!currentUser}
                          currentUser={currentUser}
                        />
                      </td>
                    </tr>
            );
          });
        })}
      </tbody>
              </table>
              </div>
            </div>

        {!currentUser && (
          <div className="p-4 bg-yellow-50 dark:bg-yellow-900/20 border-t border-border">
            <p className="text-sm text-yellow-800 dark:text-yellow-200">
              ⚠️ Sign in to edit results and track changes
            </p>
          </div>
        )}
      </Card>

      <AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete Answer?</AlertDialogTitle>
            <AlertDialogDescription>
              Are you sure you want to delete this answer? This will remove it from the table and exports. You can undo this action.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel onClick={cancelDelete}>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={confirmDelete} className="bg-red-500 hover:bg-red-600">
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Submit for Review Confirmation Dialog */}
      <AlertDialog open={submitConfirmOpen} onOpenChange={setSubmitConfirmOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Submit for Review</AlertDialogTitle>
            <AlertDialogDescription>
              {selectedSupervisor ? (
                <>
                  This project will be submitted to <strong>Waiting for Approval</strong> and assigned to <strong>{supervisors.find(s => s.user_id === selectedSupervisor)?.full_name}</strong> for review.
                  <br /><br />
                  Once approved, it will be moved to Approved Projects.
                </>
              ) : (
                <>
                  This project will be submitted to <strong>Waiting for Approval</strong> (unassigned).
                  <br /><br />
                  Any supervisor or admin can review and approve it.
                </>
              )}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel onClick={() => setSubmitConfirmOpen(false)}>Cancel</AlertDialogCancel>
            <AlertDialogAction 
              onClick={() => {
                setSubmitConfirmOpen(false);
                handleSubmit(false);
              }}
            >
              Submit for Review
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Publish Directly Confirmation Dialog */}
      <AlertDialog open={publishDirectConfirmOpen} onOpenChange={setPublishDirectConfirmOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Publish Directly</AlertDialogTitle>
            <AlertDialogDescription>
              This project will be published directly to <strong>Approved Projects</strong>, bypassing the review process.
              <br /><br />
              You can view it anytime in the Approved Projects section.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel onClick={() => setPublishDirectConfirmOpen(false)}>Cancel</AlertDialogCancel>
            <AlertDialogAction 
              onClick={() => {
                setPublishDirectConfirmOpen(false);
                handleSubmit(true);
              }}
              className="bg-gradient-primary"
            >
              Publish Directly
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Unsaved Changes Protection Dialog */}
      <UnsavedChangesDialog
        open={showUnsavedDialog}
        onSaveAndContinue={handleSaveAndContinueLater}
        onDiscard={handleDiscardChanges}
        onCancel={handleCancelNavigation}
        isSaving={isSavingForLater}
      />

    </div>

        {/* Right Column: PDF Viewer - Conditionally Visible */}
        {showPdfViewer && (
        <div className="h-[calc(100vh-8rem)] flex flex-col overflow-hidden w-full">
          {loadingPdf ? (
            <Card className="p-6 h-full flex items-center justify-center">
              <div className="text-center">
                <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary mx-auto mb-4"></div>
                <p className="text-muted-foreground">Loading PDF previews...</p>
              </div>
            </Card>
          ) : pdfUrls.length === 0 ? (
            <Card className="p-6 h-full flex items-center justify-center">
              <div className="text-center">
                <p className="text-muted-foreground mb-2">No PDF preview available</p>
                <p className="text-sm text-muted-foreground">PDFs will load when available</p>
              </div>
            </Card>
          ) : (
            <>
              {/* PDF Source Carousel */}
              <PDFSourceCarousel
                sources={pdfUrls.map(pdf => ({
                  name: pdf.name,
                  url: pdf.url,
                  pageCount: pdf.pageCount,
                  size: pdf.size,
                }))}
                selectedIndex={selectedPdfIndex}
                onSelect={setSelectedPdfIndex}
                projectId={projectHash}
                filesMetadata={filesMetadata}
                onPopoutStateChange={setIsPopoutActive}
              />
              
              {/* PDF Viewer */}
              <div className="flex-1 overflow-hidden w-full">
                <PDFViewerWithAnnotations 
                  fileUrl={pdfUrls[selectedPdfIndex].url} 
                  fileName={pdfUrls[selectedPdfIndex].name}
                  highlights={pdfHighlights}
                />
              </div>
            </>
          )}
        </div>
        )}
      </div>

      {/* Project Notes Section - Full Width */}
      {currentUser && (
        <div className="w-full mt-4">
          <ProjectNotes
            projectId={processingRecordId}
            currentUserId={currentUser.id}
            currentUserFullName={currentUser.fullName || "Unknown User"}
            isSupervisor={false}
          />
        </div>
      )}

      {/* Chatbot Card - Full Width Below */}
      <Card className="bg-gradient-card border-border shadow-card w-full mt-4">
        <div className="p-4">
          <Chatbot documentContext={enhancedContext} processingId={processingRecordId} />
        </div>
      </Card>

      {/* Submit for Review / Publish Directly Buttons - After Chatbot */}
      {!isSubmitted && !hideSubmitButton && (
        <Card className="w-full mt-4 p-4 bg-white dark:bg-card border-border shadow-card">
          <div className="space-y-3">
            <div className="grid grid-cols-4 gap-4 items-end w-full">
              {/* Save and Exit Button */}
              <div className="space-y-1.5">
                <Label className="text-sm font-medium invisible">Action</Label>
                <Button
                  variant="outline"
                  onClick={handleSaveAndExit}
                  disabled={isSavingForLater}
                  className="w-full h-10"
                >
                  <LogOut className="h-4 w-4 mr-2" />
                  {isSavingForLater ? "Saving..." : "Save and Exit"}
                </Button>
              </div>
              
              {/* Assign to Section */}
              <div className="space-y-1.5">
                <Label htmlFor="supervisor" className="text-sm font-medium">
                  Assign to
                </Label>
                <Popover open={supervisorPopoverOpen} onOpenChange={setSupervisorPopoverOpen}>
                  <PopoverTrigger asChild>
                    <Button
                      variant="outline"
                      role="combobox"
                      aria-expanded={supervisorPopoverOpen}
                      className="w-full justify-between h-10"
                    >
                      {selectedSupervisor
                        ? supervisors.find((s) => s.user_id === selectedSupervisor)?.full_name || 
                          supervisors.find((s) => s.user_id === selectedSupervisor)?.email
                        : "Select a supervisor..."}
                      <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
                    </Button>
                  </PopoverTrigger>
                  <PopoverContent className="w-[400px] p-0" align="start">
                    <Command>
                      <CommandInput placeholder="Search supervisor..." />
                      <CommandList>
                        <CommandEmpty>No supervisor found.</CommandEmpty>
                        <CommandGroup>
                          <CommandItem
                            value="none"
                            onSelect={() => {
                              setSelectedSupervisor("");
                              setSupervisorPopoverOpen(false);
                            }}
                          >
                            <Check
                              className={`mr-2 h-4 w-4 ${
                                !selectedSupervisor
                                  ? "opacity-100"
                                  : "opacity-0"
                              }`}
                            />
                            None (Submit directly)
                          </CommandItem>
                          {supervisors.map((supervisor) => (
                            <CommandItem
                              key={supervisor.user_id}
                              value={supervisor.full_name || supervisor.email}
                              onSelect={() => {
                                setSelectedSupervisor(supervisor.user_id);
                                setSupervisorPopoverOpen(false);
                              }}
                            >
                              <Check
                                className={`mr-2 h-4 w-4 ${
                                  selectedSupervisor === supervisor.user_id
                                    ? "opacity-100"
                                    : "opacity-0"
                                }`}
                              />
                              {supervisor.full_name || supervisor.email}
                            </CommandItem>
                          ))}
                        </CommandGroup>
                      </CommandList>
                    </Command>
                  </PopoverContent>
                </Popover>
              </div>

              {/* Submit for Review Button */}
              <div className="space-y-1.5">
                <Label className="text-sm font-medium invisible">Submit</Label>
                <Button
                  onClick={handleSubmitForReviewClick}
                  disabled={!allResultsHaveFeedback || isSubmitting}
                  variant="outline"
                  className="w-full h-10 gap-2"
                >
                  {isSubmitting ? (
                    <>Processing...</>
                  ) : (
                    <>
                      <Send className="h-4 w-4" />
                      Submit for Review
                    </>
                  )}
                </Button>
              </div>

              {/* Publish Directly Button */}
              <div className="space-y-1.5">
                <Label className="text-sm font-medium invisible">Publish</Label>
                <Button
                  onClick={handlePublishDirectlyClick}
                  disabled={!allResultsHaveFeedback || isSubmitting}
                  className="w-full h-10 gap-2 bg-gradient-primary"
                >
                  {isSubmitting ? (
                    <>Processing...</>
                  ) : (
                    <>
                      <CheckCircle className="h-4 w-4" />
                      Publish Directly
                    </>
                  )}
                </Button>
              </div>
            </div>

            {/* Warning Message */}
            {!allResultsHaveFeedback && (
              <div className="bg-white dark:bg-card border border-white dark:border-card rounded-lg p-3">
                <p className="text-sm text-yellow-800 dark:text-yellow-400">
                  Please provide feedback (👍 or 👎) for all questions to enable submission.
                </p>
              </div>
            )}
          </div>
        </Card>
      )}

      {/* Deflection Criteria Editor Dialog */}
      <Dialog open={deflectionDialogOpen} onOpenChange={(open) => {
        setDeflectionDialogOpen(open);
        if (!open) {
          // Clean up when dialog closes
          handleEditCancel();
        }
      }}>
        <DialogContent className="max-w-4xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="text-lg font-semibold">
              {deflectionEditContext && results[deflectionEditContext.resultIndex]?.question}
            </DialogTitle>
          </DialogHeader>
          <div className="mt-4">
            {deflectionEditContext && (
              <DeflectionCriteriaEditor
                value={deflectionEditContext.value}
                onSave={(newValue) => {
                  handleEditSave(deflectionEditContext.resultIndex, deflectionEditContext.pairIndex, newValue);
                  setDeflectionDialogOpen(false);
                  setDeflectionEditContext(null);
                }}
                onCancel={() => {
                  setDeflectionDialogOpen(false);
                  handleEditCancel();
                }}
              />
            )}
          </div>
        </DialogContent>
      </Dialog>

      
    </div>
  );
};
