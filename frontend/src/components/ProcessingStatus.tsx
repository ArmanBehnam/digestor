import { CheckCircle2, Loader2, AlertCircle, RotateCcw } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Button } from "@/components/ui/button";

export type ProcessingStage = "idle" | "extracting" | "analyzing" | "complete" | "error";

interface ProcessingStatusProps {
  stage: ProcessingStage;
  progress: number;
  error?: string;
  onRetry?: () => void;
}

const stageInfo = {
  idle: { label: "Ready to process", icon: null },
  extracting: { label: "Extracting text from document...", icon: Loader2 },
  analyzing: { label: "Analyzing contract with ClarkDietrich AI...", icon: Loader2 },
  complete: { label: "Analysis complete!", icon: CheckCircle2 },
  error: { label: "Processing failed", icon: AlertCircle },
};

export const ProcessingStatus = ({ stage, progress, error, onRetry }: ProcessingStatusProps) => {
  if (stage === "idle") return null;

  const info = stageInfo[stage];
  const Icon = info.icon;

  return (
    <Card className="bg-gradient-card border-border shadow-card animate-slide-up">
      <div className="p-6">
        <div className="flex items-center gap-3 mb-4">
          {Icon && (
            <Icon
              className={`h-5 w-5 ${
                stage === "complete"
                  ? "text-accent"
                  : stage === "error"
                  ? "text-destructive"
                  : "text-primary animate-spin"
              }`}
            />
          )}
          <p className="font-medium text-foreground">{info.label}</p>
        </div>
        
        {stage !== "complete" && stage !== "error" && (
          <Progress value={progress} className="h-2" />
        )}
        
        {error && (
          <div className="mt-3 space-y-3">
            <p className="text-sm text-destructive bg-destructive/10 p-3 rounded-md">
              {error}
            </p>
            {onRetry && (
              <Button 
                onClick={onRetry} 
                variant="outline" 
                size="sm"
                className="gap-2"
              >
                <RotateCcw className="h-4 w-4" />
                Retry Processing
              </Button>
            )}
          </div>
        )}
      </div>
    </Card>
  );
};
