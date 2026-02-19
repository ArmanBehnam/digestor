import { CheckCircle2 } from "lucide-react";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";

interface VerificationCheckmarkProps {
  isEdited: boolean;           // Now shows green (same as selected)
  isSelected: boolean;         // Green if true (single answer or is_selected)
  isExcluded: boolean;         // Grey if true
  isDeleted: boolean;          // Grey if true
  hasMultipleAnswers: boolean;
  onClick?: () => void;        // Handler for selecting this answer
  isClickable: boolean;        // Can user click to select
  excludedBy?: string;
  excludedAt?: string;
  deletedBy?: string;
  deletedAt?: string;
}

export function VerificationCheckmark({
  isEdited,
  isSelected,
  isExcluded,
  isDeleted,
  hasMultipleAnswers,
  onClick,
  isClickable,
  excludedBy,
  excludedAt,
  deletedBy,
  deletedAt,
}: VerificationCheckmarkProps) {
  // Determine checkmark color based on state priority
  // Priority: Deleted/Excluded (grey) > Selected/Edited (green) > Alternative (grey)
  let colorClass = "text-green-500"; // Default: selected/verified
  let tooltipText = "Verified answer";
  
  if (isDeleted) {
    colorClass = "text-gray-400";
    tooltipText = deletedBy && deletedAt 
      ? `Deleted by ${deletedBy} on ${new Date(deletedAt).toLocaleDateString()}`
      : "Deleted answer";
  } else if (isExcluded) {
    colorClass = "text-gray-400";
    tooltipText = excludedBy && excludedAt
      ? `Excluded by ${excludedBy} on ${new Date(excludedAt).toLocaleDateString()}. Click to select this answer.`
      : "Excluded answer. Click to select.";
  } else if (isSelected || isEdited) {
    colorClass = "text-green-500";
    tooltipText = isEdited 
      ? (hasMultipleAnswers ? "Selected answer (edited)" : "Verified answer (edited)")
      : (hasMultipleAnswers ? "Selected answer" : "Verified answer");
  } else if (hasMultipleAnswers) {
    // Multiple answers but not selected - grey (alternative)
    colorClass = "text-gray-400";
    tooltipText = "Alternative answer. Click to select.";
  }

  const isInteractive = isClickable && !isDeleted;

  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <button
            type="button"
            onClick={isInteractive ? onClick : undefined}
            className={`flex-shrink-0 mt-0.5 transition-all duration-200 ${
              isInteractive 
                ? "cursor-pointer hover:scale-110 hover:opacity-80" 
                : "cursor-default"
            }`}
            disabled={!isInteractive}
            aria-label={tooltipText}
          >
            <CheckCircle2 
              className={`h-4 w-4 ${colorClass}`}
              strokeWidth={2}
            />
          </button>
        </TooltipTrigger>
        <TooltipContent side="top" className="max-w-xs">
          <p className="text-xs">{tooltipText}</p>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
