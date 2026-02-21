import { useState, useEffect, useRef, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { exportAnswer } from "@/lib/displayUtils";
import { formatQuestionTitle } from "@/lib/questionTitleUtils";
import { isValidBuildingCodeAnswer } from "@/lib/buildingCodeFilter";
import { FileUpload } from "@/components/FileUpload";
import { ProcessingStatus, ProcessingStage } from "@/components/ProcessingStatus";
import { ResultsDisplay, AnalysisResult, normalizeAnswer } from "@/components/ResultsDisplay";
import { ProjectsHistory } from "@/components/ProjectsHistory";
import { ProjectDetail } from "@/components/ProjectDetail";
import { UnsavedChangesDialog } from "@/components/UnsavedChangesDialog";

import { SupervisorReview } from "@/components/SupervisorReview";
import { useToast } from "@/hooks/use-toast";
import { useAuth } from "@/hooks/useAuth";
import { useUserRole } from "@/hooks/useUserRole";
import apiClient from "@/lib/apiClient";
import { useWebSocket } from "@/hooks/useWebSocket";
import { extractTextFromPDF, extractTextWithPositions } from "@/lib/pdfParser";
import { FileText, Sparkles, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import ClarkDietrichLogo from "@/assets/ClarkDietrich_Logo.jpg";
import workflowBackground from "@/assets/workflow-background.png";
import { Auth } from "@/components/Auth";
import { Profile } from "@/components/Profile";
import { Navbar } from "@/components/Navbar";


const standardizeUnit = (rawUnit: string): string => {
  const unit = rawUnit.toLowerCase().replace(/\./g, "").trim();

  if (/^(mph|m\s*p\s*h|miles?\s*(per|\/)\s*hour?|mi\s*\/\s*h?r?|m\s*\/\s*h?r?)$/i.test(unit)) {
    return "mph";
  }
  if (/^(km\s*\/?\s*h|kph|kilometers?\s*(per|\/)\s*hour?|kmph)$/i.test(unit)) {
    return "mph";
  }
  if (/^(m\s*\/?\s*s|meters?\s*(per|\/)\s*second?)$/i.test(unit)) {
    return "mph";
  }
  if (
    /^(psf|p\s*s\s*f|pounds?\s*(per|\/)\s*square\s*foot|lb\s*\/?\s*(sqft|sf|ft[²2])|lbs?\s*\/?\s*ft[²2]|lb\.?\s*\/?\s*sq\.?\s*ft\.?)$/i.test(
      unit,
    )
  ) {
    return "psf";
  }
  if (/^(pa|pascal|n\s*\/?\s*m[²2])$/i.test(unit)) {
    return "psf";
  }
  if (/^(kpa|kilopascal)$/i.test(unit)) {
    return "psf";
  }
  if (/^(psi|p\s*s\s*i|lb\s*\/?\s*in[²2]|pounds?\s*(per|\/)\s*square\s*inch)$/i.test(unit)) {
    return "psf";
  }
  if (/^(inch(es)?|in\.?|"|'')$/i.test(unit)) {
    return "inch";
  }
  if (/^(ft|foot|feet|')$/i.test(unit)) {
    return "inch";
  }
  if (/^(cm|centimeters?|centimetres?)$/i.test(unit)) {
    return "inch";
  }
  if (/^(mm|millimeters?|millimetres?)$/i.test(unit)) {
    return "inch";
  }
  if (/^(m|meters?|metres?)$/i.test(unit) && !/mph|m\s*\//.test(rawUnit)) {
    return "inch";
  }

  // plf variants
  if (
    /^(plf|p\.?\s*l\.?\s*f\.?|pounds?\s*(per|\/)\s*linear\s*foot|lb\s*\/?\s*ft|lbs?\s*\/?\s*ft|lb\.?\s*\/?\s*ft\.?|pounds?\s*\/?\s*foot)$/i.test(
      unit,
    )
  ) {
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
  const unit = fromUnit.toLowerCase().replace(/\./g, "").trim();

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

const extractUnit = (answer: string, questionId: number): string => {
  // Handle both internal "Not Found" and display "Not Available"
  if (answer === "Not Found" || answer === "Not Available") return "";

  const questionsWithUnits = [9, 13, 14, 15, 19];
  if (!questionsWithUnits.includes(questionId)) {
    return "";
  }

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

// Compute project hash from project name and files
const computeProjectHash = (projectName: string, files: File[]): string => {
  const fileMetadata = files
    .map((f) => `${f.name}:${f.size}`)
    .sort()
    .join("|");
  const combined = `${projectName.trim().toLowerCase()}|${fileMetadata}`;

  // Simple hash function
  let hash = 0;
  for (let i = 0; i < combined.length; i++) {
    const char = combined.charCodeAt(i);
    hash = (hash << 5) - hash + char;
    hash = hash & hash;
  }
  return Math.abs(hash).toString(36);
};

const Index = () => {
  const navigate = useNavigate();
  const { user, isLoading: authLoading, logout } = useAuth();
  const userId = user?.id ?? null;
  const { isSupervisor, isAdmin } = useUserRole(userId);

  const [stage, setStage] = useState<ProcessingStage>("idle");
  const [progress, setProgress] = useState(0);
  const [results, setResults] = useState<AnalysisResult[]>([]);
  const [error, setError] = useState<string>();
  const [uploadKey, setUploadKey] = useState(0);
  const [projectId, setProjectId] = useState("");
  const [projectName, setProjectName] = useState("");
  const [manualProjectName, setManualProjectName] = useState("");
  const [processingTimeSeconds, setProcessingTimeSeconds] = useState<number>(0);
  const [processingRecordId, setProcessingRecordId] = useState<string>("");
  const [loadedFromCache, setLoadedFromCache] = useState(false);
  const [projectHash, setProjectHash] = useState<string>("");
  const [filesMetadata, setFilesMetadata] = useState<Array<{ name: string; path: string; size: number; type: string }>>([]);
  const [showProfile, setShowProfile] = useState(false);
  const [currentView, setCurrentView] = useState<"home" | "approvals" | "approval-detail">("home");
  const [reviewingProjectHash, setReviewingProjectHash] = useState<string | null>(null);
  const { toast } = useToast();

  // Navigation guard state for unsaved changes protection
  const [isResultsDirty, setIsResultsDirty] = useState(false);
  const [pendingNavigation, setPendingNavigation] = useState<string | null>(null);
  const [showUnsavedDialog, setShowUnsavedDialog] = useState(false);
  const [isSavingProgress, setIsSavingProgress] = useState(false);
  const saveCallbackRef = useRef<(() => Promise<void>) | null>(null);

  // Supervisor review dirty state tracking (for approval-detail view)
  const [isSupervisorReviewDirty, setIsSupervisorReviewDirty] = useState(false);
  const [showSupervisorUnsavedDialog, setShowSupervisorUnsavedDialog] = useState(false);
  const [isSavingSupervisorProgress, setIsSavingSupervisorProgress] = useState(false);
  const supervisorSaveRef = useRef<(() => Promise<void>) | null>(null);

  // Guarded navigation function - checks dirty state before navigating
  const guardedNavigate = useCallback((path: string) => {
    if (isResultsDirty && results.length > 0) {
      setPendingNavigation(path);
      setShowUnsavedDialog(true);
      return;
    }
    navigate(path);
  }, [isResultsDirty, results.length, navigate]);

  // SPA navigation handlers - use React Router navigate instead of window.location
  const handleNavigateToTickets = () => guardedNavigate("/tickets");
  const handleNavigateToFeedback = () => guardedNavigate("/feedback");
  const handleNavigateToDashboard = () => guardedNavigate("/dashboard");
  const handleNavigateToAnalytics = () => guardedNavigate("/analytics");
  const handleNavigateToAdminSettings = () => guardedNavigate("/admin-settings");

  // Ref to track processing start time
  const processingStartTimeRef = useRef<number | null>(null);
  const processingEndTimeRef = useRef<number | null>(null);
  const hasCalculatedProcessingTimeRef = useRef(false);
  const [debugTimestamps, setDebugTimestamps] = useState<{
    startTime: number | null;
    endTime: number | null;
    durationMs: number | null;
    durationSeconds: number | null;
    durationMinutes: number | null;
  }>({
    startTime: null,
    endTime: null,
    durationMs: null,
    durationSeconds: null,
    durationMinutes: null,
  });

  // Calculate and store processed time when results are fully rendered
  useEffect(() => {
    const calculateProcessedTime = () => {
      if (
        stage === "complete" &&
        results.length > 0 &&
        processingStartTimeRef.current !== null &&
        !hasCalculatedProcessingTimeRef.current &&
        !loadedFromCache &&
        processingRecordId
      ) {
        requestAnimationFrame(() => {
          requestAnimationFrame(async () => {
            hasCalculatedProcessingTimeRef.current = true;

            const endTime = Date.now();
            const startTime = processingStartTimeRef.current!;

            if (endTime < startTime) {
              console.error('Invalid timestamps: end time before start time');
              return;
            }

            const durationMs = endTime - startTime;
            const durationSeconds = durationMs / 1000;
            const minutes = Math.floor(durationSeconds / 60);
            const seconds = durationSeconds % 60;
            const durationMinutes = minutes + (seconds / 60);

            processingEndTimeRef.current = endTime;

            setDebugTimestamps({
              startTime,
              endTime,
              durationMs,
              durationSeconds: Number(durationSeconds.toFixed(2)),
              durationMinutes: Number(durationMinutes.toFixed(2)),
            });

            setProcessingTimeSeconds(durationSeconds);

            // Update database with TRUE client-measured end-to-end time
            try {
              await apiClient.updateResult({
                document_id: processingRecordId,
                question_key: '__processing_time__',
                new_value: JSON.stringify({
                  processed_time: durationMinutes,
                  saved_time: Math.max(0, 2400 - durationMinutes),
                }),
              });
              sessionStorage.removeItem('processing_start_time');
            } catch (err) {
              console.error('Failed to update processing time:', err);
            }
          });
        });
      }
    };

    calculateProcessedTime();
  }, [stage, results, loadedFromCache, processingRecordId]);

  const handleAuthSuccess = () => {
    // Auth state is managed by AuthProvider - no manual check needed
  };

  const handleSignOut = async () => {
    try {
      await logout();
      setShowProfile(false);
    } catch (err) {
      console.error("Sign out error:", err);
    }
  };

  // Unsaved changes dialog handlers
  const handleSaveAndContinue = async () => {
    setIsSavingProgress(true);
    try {
      if (saveCallbackRef.current) {
        await saveCallbackRef.current();
      }
      setShowUnsavedDialog(false);
      setIsResultsDirty(false);

      toast({
        title: "Saved to Waiting for Approval",
        description: "Project saved and assigned to you. Find it in 'Waiting for Approval'.",
      });

      window.dispatchEvent(new CustomEvent("project-saved-to-waiting"));

      setStage("idle");
      setProgress(0);
      setResults([]);
      setReviewingProjectHash(null);
      setCurrentView("home");

      if (pendingNavigation && pendingNavigation !== "INTERNAL_ACTION") {
        navigate(pendingNavigation);
      }
      setPendingNavigation(null);
    } catch (error) {
      console.error("Save and continue error:", error);
      toast({
        title: "Save Failed",
        description: "Failed to save progress. Please try again.",
        variant: "destructive",
      });
    } finally {
      setIsSavingProgress(false);
    }
  };

  const handleDiscardChanges = () => {
    setShowUnsavedDialog(false);
    setIsResultsDirty(false);
    if (pendingNavigation) {
      navigate(pendingNavigation);
      setPendingNavigation(null);
    }
  };

  const handleCancelNavigation = () => {
    setShowUnsavedDialog(false);
    setPendingNavigation(null);
  };

  // Supervisor review unsaved dialog handlers
  const executeSupervisorPendingNavigation = useCallback(() => {
    const nav = pendingNavigation;
    setPendingNavigation(null);
    setIsSupervisorReviewDirty(false);

    if (nav === "HOME") {
      setCurrentView("home");
      setShowProfile(false);
      setReviewingProjectHash(null);
    } else if (nav === "APPROVALS") {
      setCurrentView("approvals");
      setShowProfile(false);
      setReviewingProjectHash(null);
    } else if (nav?.startsWith("REVIEW:")) {
      const hash = nav.replace("REVIEW:", "");
      setReviewingProjectHash(hash);
      setCurrentView("approval-detail");
    } else if (nav && nav !== "INTERNAL_ACTION") {
      navigate(nav);
    }
  }, [pendingNavigation, navigate]);

  const handleSupervisorSaveAndContinue = async () => {
    setIsSavingSupervisorProgress(true);
    try {
      if (supervisorSaveRef.current) {
        await supervisorSaveRef.current();
      }
      setShowSupervisorUnsavedDialog(false);
      setIsSupervisorReviewDirty(false);

      toast({
        title: "Changes Saved",
        description: "Your review progress has been saved.",
      });

      executeSupervisorPendingNavigation();
    } catch (error) {
      console.error("Supervisor save error:", error);
      toast({
        title: "Save Failed",
        description: "Failed to save progress. Please try again.",
        variant: "destructive",
      });
    } finally {
      setIsSavingSupervisorProgress(false);
    }
  };

  const handleSupervisorDiscardChanges = () => {
    setShowSupervisorUnsavedDialog(false);
    setIsSupervisorReviewDirty(false);
    executeSupervisorPendingNavigation();
  };

  const handleSupervisorCancelNavigation = () => {
    setShowSupervisorUnsavedDialog(false);
    setPendingNavigation(null);
  };

  // Guard internal navigation that doesn't use React Router paths
  const guardedInternalNavigate = useCallback((action: () => void) => {
    if (isResultsDirty && results.length > 0) {
      setPendingNavigation("INTERNAL_ACTION");
      saveCallbackRef.current = null;
      setShowUnsavedDialog(true);
      return false;
    }
    action();
    return true;
  }, [isResultsDirty, results.length]);

  const handleNewProject = () => {
    const doNewProject = () => {
      setStage("idle");
      setProgress(0);
      setResults([]);
      setError(undefined);
      setUploadKey((prev) => prev + 1);
      setProjectId("");
      setProjectName("");
      setManualProjectName("");
      setProcessingTimeSeconds(0);
      setProcessingRecordId("");
      setLoadedFromCache(false);
      setProjectHash("");
      setFilesMetadata([]);
      setIsResultsDirty(false);
      processingStartTimeRef.current = null;
      processingEndTimeRef.current = null;
      hasCalculatedProcessingTimeRef.current = false;
      setDebugTimestamps({
        startTime: null,
        endTime: null,
        durationMs: null,
        durationSeconds: null,
        durationMinutes: null,
      });
      toast({
        title: "New project started",
        description: "Ready to analyze new documents.",
      });
    };

    if (isResultsDirty && results.length > 0) {
      setPendingNavigation("NEW_PROJECT");
      setShowUnsavedDialog(true);
    } else {
      doNewProject();
    }
  };

  const handleNavigateToApprovals = () => {
    if (currentView === "approval-detail" && isSupervisorReviewDirty) {
      setPendingNavigation("APPROVALS");
      setShowSupervisorUnsavedDialog(true);
      return;
    }
    if (isResultsDirty && results.length > 0) {
      setPendingNavigation("APPROVALS");
      setShowUnsavedDialog(true);
      return;
    }
    setCurrentView("approvals");
    setShowProfile(false);
  };

  const handleNavigateToHome = () => {
    if (currentView === "approval-detail" && isSupervisorReviewDirty) {
      setPendingNavigation("HOME");
      setShowSupervisorUnsavedDialog(true);
      return;
    }
    if (isResultsDirty && results.length > 0) {
      setPendingNavigation("HOME");
      setShowUnsavedDialog(true);
      return;
    }
    setCurrentView("home");
    setShowProfile(false);
    setReviewingProjectHash(null);
  };

  const handleApprovalProjectClick = (projectHash: string) => {
    if (isResultsDirty && results.length > 0) {
      setPendingNavigation(`REVIEW:${projectHash}`);
      setShowUnsavedDialog(true);
      return;
    }
    setReviewingProjectHash(projectHash);
    setCurrentView("approval-detail");
  };

  const handleBackToApprovals = () => {
    setReviewingProjectHash(null);
    setCurrentView("approvals");
  };

  const handleSubmitSuccess = () => {
    setStage("idle");
    setProgress(0);
    setResults([]);
    setProjectId("");
    setProjectName("");
    setManualProjectName("");
    setProcessingTimeSeconds(0);
    setProcessingRecordId("");
    setLoadedFromCache(false);
    setProjectHash("");
    setFilesMetadata([]);
    processingStartTimeRef.current = null;
    processingEndTimeRef.current = null;
    hasCalculatedProcessingTimeRef.current = false;
    sessionStorage.removeItem('processing_start_time');
    setUploadKey(prev => prev + 1);
    setCurrentView("home");
  };

  const handleSaveAndExitToHome = () => {
    setStage("idle");
    setProgress(0);
    setResults([]);
    setProjectId("");
    setProjectName("");
    setManualProjectName("");
    setProcessingTimeSeconds(0);
    setProcessingRecordId("");
    setLoadedFromCache(false);
    setProjectHash("");
    setFilesMetadata([]);
    setIsResultsDirty(false);
    processingStartTimeRef.current = null;
    processingEndTimeRef.current = null;
    hasCalculatedProcessingTimeRef.current = false;
    sessionStorage.removeItem('processing_start_time');
    setUploadKey(prev => prev + 1);
    setCurrentView("home");
  };

  const handleSupervisorSaveAndExitToHome = () => {
    setReviewingProjectHash(null);
    setCurrentView("home");
  };

  const handleRerunProject = (projectData: any) => {
    setManualProjectName(projectData.projectName || "");
    toast({
      title: "Ready to re-run project",
      description: "Upload files to start a new version",
    });
  };

  // Initialize feedback defaults for existing projects that don't have feedback yet
  const initializeFeedbackDefaults = async (
    results: AnalysisResult[],
    recordId: string
  ): Promise<AnalysisResult[]> => {
    const hasFeedback = results.some(result =>
      result.pairs.some(pair => pair.feedback === "up" || pair.feedback === "down")
    );

    if (hasFeedback) {
      return results;
    }

    const initializedResults = results.map(result => ({
      ...result,
      pairs: result.pairs.map(pair => ({
        ...pair,
        feedback: (pair as any).is_not_applicable ? pair.feedback : "up" as const
      }))
    }));

    // Persist to database
    if (recordId) {
      try {
        await apiClient.updateResult({
          document_id: recordId,
          question_key: '__feedback_defaults__',
          new_value: JSON.stringify({ feedbackInitialized: true }),
          remarks: JSON.stringify(initializedResults),
        });
      } catch (err) {
        console.error('[initializeFeedbackDefaults] Failed to persist:', err);
      }
    }

    return initializedResults;
  };

  const aggregateMultipleFileResults = (fileResults: AnalysisResult[][]): AnalysisResult[] => {
    const aggregated = new Map<string, AnalysisResult>();

    fileResults.forEach((results) => {
      results.forEach((result) => {
        const key = `${result.category}:${result.question}`;
        const existing = aggregated.get(key);

        const resultPairs = result.pairs || [
          {
            answer: (result as any).answer,
            reference: (result as any).reference,
            feedback: (result as any).feedback,
          },
        ];

        if (!existing) {
          aggregated.set(key, {
            category: result.category,
            question: result.question,
            pairs: [...resultPairs],
          });
        } else {
          resultPairs.forEach((newPair) => {
            if (newPair.answer !== "Not Found") {
              const isDuplicate = existing.pairs.some(
                (p) => p.answer === newPair.answer && p.reference === newPair.reference,
              );

              if (!isDuplicate) {
                const notFoundIndex = existing.pairs.findIndex((p) => p.answer === "Not Found");
                if (notFoundIndex >= 0 && existing.pairs.length === 1) {
                  existing.pairs[notFoundIndex] = { ...newPair };
                } else if (notFoundIndex < 0) {
                  existing.pairs.push({ ...newPair });
                }
              }
            }
          });
        }
      });
    });

    return Array.from(aggregated.values());
  };

  const handleFileSelect = async (files: File[]) => {
    if (!user) {
      toast({
        title: "Authentication required",
        description: "Please sign in to upload and process documents.",
        variant: "destructive",
      });
      return;
    }

    const trueStartTimestamp = Date.now();
    processingStartTimeRef.current = trueStartTimestamp;
    hasCalculatedProcessingTimeRef.current = false;
    sessionStorage.setItem('processing_start_time', trueStartTimestamp.toString());

    try {
      setStage("extracting");
      setProgress(10);
      setError(undefined);
      setLoadedFromCache(false);

      let finalProjectName = manualProjectName.trim();

      if (!finalProjectName) {
        for (const file of files) {
          const fileName = file.name.toLowerCase();
          const isSpecFile = fileName.includes("spec") || fileName.includes("specification");
          const isDrawingFile =
            !isSpecFile &&
            (fileName.includes("drawing") ||
              fileName.includes("dwg") ||
              fileName.includes("plan") ||
              /[a-z]-\d+/i.test(fileName));

          if (isDrawingFile || !isSpecFile) {
            try {
              const { extractFirstPageTitle } = await import("@/lib/pdfParser");
              const detectedTitle = await extractFirstPageTitle(file);
              if (detectedTitle?.trim()) {
                finalProjectName = detectedTitle.trim();
                setProjectName(finalProjectName);
                setManualProjectName(finalProjectName);
                break;
              }
            } catch (error) {
              console.error("Error extracting project name:", error);
            }
          }
        }
      }

      // Check if project already exists via API
      if (finalProjectName) {
        const hash = computeProjectHash(finalProjectName, files);
        setProjectHash(hash);

        try {
          const existingData = await apiClient.listProjects(undefined, 1, 100);
          const existingProjects = (existingData?.projects || []).filter(
            (p: any) => p.project_hash === hash && (p.status === "complete" || p.status === "completed") && p.results
          );

          if (existingProjects.length > 0) {
            const allResults = existingProjects.flatMap((record: any) => record.results || []);
            if (allResults.length > 0) {
              const initializedResults = await initializeFeedbackDefaults(
                allResults as unknown as AnalysisResult[],
                existingProjects[0].id
              );
              setResults(initializedResults);
              setProcessingRecordId(existingProjects[0].id);
              setProjectName(finalProjectName);
              setProgress(100);
              setStage("complete");
              setLoadedFromCache(true);

              toast({
                title: "Project loaded from cache",
                description: `Found existing analysis for "${finalProjectName}"`,
              });
              return;
            }
          }
        } catch (err) {
          // Project doesn't exist yet, continue with processing
          console.log("No cached project found, processing fresh");
        }
      }

      // Prepare files metadata for storage
      const filesMetadataArray = files.map((f) => ({
        name: f.name,
        size: f.size,
        type: f.type,
      }));

      // Process all files and collect their results
      const fileResults: AnalysisResult[][] = [];
      // Generate a stable project name ONCE for all files (prevents separate projects)
      const stableProjectName = finalProjectName || `Project_${Date.now()}`;
      const hash = computeProjectHash(stableProjectName, files);
      setProjectHash(hash);

      // ============================================================
      // PHASE 1: Upload ALL files and extract text from each
      // ============================================================
      const documentTexts: Array<{ document_id: string; extracted_text: string }> = [];
      let serverProjectId: string | null = null;

      for (let i = 0; i < files.length; i++) {
        const file = files[i];
        setProgress(10 + (i / files.length) * 30); // 10-40% for uploads

        // Upload file via apiClient
        // After first upload, pass project_id so subsequent files join the SAME project
        const uploadData = await apiClient.uploadDocument(file, {
          projectHash: hash,
          projectName: stableProjectName,
          project_id: serverProjectId || undefined,
          filesMetadata: filesMetadataArray,
        });

        if (!uploadData?.processingId) {
          throw new Error(`Failed to upload ${file.name}: No processing ID returned`);
        }

        // Capture project_id and first processingId
        if (i === 0) {
          setProcessingRecordId(uploadData.processingId);
          serverProjectId = uploadData.project_id;
        }

        // Store file metadata with path
        if (uploadData.filePath) {
          const fileMetadata = {
            name: file.name,
            path: uploadData.filePath,
            size: file.size,
            type: file.type
          };
          setFilesMetadata(prev => [...prev, fileMetadata]);
        }

        // Extract text from PDF (browser-side via PDF.js)
        setStage("extracting");
        const documentText = await extractTextFromPDF(file);

        documentTexts.push({
          document_id: uploadData.processingId,
          extracted_text: documentText,
        });
      }

      // ============================================================
      // PHASE 2: Process — combined (multi-file) or single
      // ============================================================
      setStage("analyzing");
      setProgress(45);

      let finalResults: AnalysisResult[] | null = null;

      if (files.length > 1 && serverProjectId) {
        // ----- MULTI-FILE: Combined project processing -----
        // Sends ALL extracted text to backend, which combines and runs LLM once
        await apiClient.processProject({
          project_id: serverProjectId,
          documents: documentTexts,
        });

        // Poll project-level results
        const MAX_POLL_ATTEMPTS = 3600;
        let pollAttempts = 0;

        while (pollAttempts < MAX_POLL_ATTEMPTS) {
          await new Promise(resolve => setTimeout(resolve, 1000));

          let statusData: any;
          try {
            statusData = await apiClient.getProjectResults(serverProjectId);
          } catch (err) {
            console.error('Error polling project status:', err);
            pollAttempts++;
            continue;
          }

          setProgress(50 + Math.min((pollAttempts / 60) * 40, 45)); // 50-95%

          if (statusData.status === 'complete') {
            finalResults = statusData.results;
            break;
          } else if (statusData.status === 'error') {
            throw new Error('Processing failed');
          }

          pollAttempts++;
        }

        if (pollAttempts >= MAX_POLL_ATTEMPTS) {
          throw new Error('Processing timed out after 60 minutes.');
        }
      } else {
        // ----- SINGLE FILE: Existing per-document processing -----
        const singleDoc = documentTexts[0];
        await apiClient.processDocument(singleDoc.document_id, singleDoc.extracted_text);

        const MAX_POLL_ATTEMPTS = 3600;
        const STALE_THRESHOLD = 10 * 60 * 1000;
        const PROGRESS_SAVED_STALE_THRESHOLD = 3 * 60 * 1000;
        const MAX_AUTO_RETRIES = 20;
        let pollAttempts = 0;
        let lastActivityTime = Date.now();
        let lastStatus = '';
        let lastUpdatedAt = 0;
        let autoRetryCount = 0;

        while (pollAttempts < MAX_POLL_ATTEMPTS) {
          await new Promise(resolve => setTimeout(resolve, 1000));

          let statusData: any;
          try {
            statusData = await apiClient.getResults(singleDoc.document_id);
          } catch (err) {
            console.error('Error polling status:', err);
            pollAttempts++;
            continue;
          }

          // AUTO-RESUME logic
          const editState = statusData.edit_state as { canResume?: boolean; resumeRequired?: boolean } | null;
          const isTimeoutCheckpoint = statusData.status?.includes('timeout_checkpoint');
          const isAlreadyComplete = statusData.status === 'complete' || statusData.status?.includes('AI analysis complete');
          const lastUpdate = statusData.updated_at ? new Date(statusData.updated_at).getTime() : 0;
          const timeSinceUpdate = Date.now() - lastUpdate;
          const STUCK_THRESHOLD = 2 * 60 * 1000;
          const isRecordStale = timeSinceUpdate > STUCK_THRESHOLD;

          const isStuckMidBatch = editState?.resumeRequired === true && editState?.canResume === true && !isAlreadyComplete && isRecordStale;
          const needsResume = (isTimeoutCheckpoint && editState?.canResume) || isStuckMidBatch;

          if (needsResume) {
            autoRetryCount++;
            if (autoRetryCount <= MAX_AUTO_RETRIES) {
              await apiClient.processDocument(singleDoc.document_id, singleDoc.extracted_text);
              lastActivityTime = Date.now();
              continue;
            } else {
              throw new Error(`Processing failed after ${MAX_AUTO_RETRIES} auto-resume attempts. Please try with a smaller file.`);
            }
          }

          // Detect stale processing
          const currentUpdatedAt = statusData.updated_at ? new Date(statusData.updated_at).getTime() : 0;
          if (statusData.status !== lastStatus || currentUpdatedAt > lastUpdatedAt) {
            lastActivityTime = Date.now();
            lastStatus = statusData.status;
            lastUpdatedAt = currentUpdatedAt;
          } else {
            const isProgressSavedState = statusData.status?.includes('(progress saved)');
            const isProcessingState = statusData.status?.includes('analyzing') || statusData.status?.includes('creating embeddings');
            const staleDuration = Date.now() - lastActivityTime;

            const effectiveThreshold = isProgressSavedState ? PROGRESS_SAVED_STALE_THRESHOLD : STALE_THRESHOLD;

            if (staleDuration > effectiveThreshold && isProcessingState) {
              if (editState?.canResume && autoRetryCount < MAX_AUTO_RETRIES) {
                autoRetryCount++;
                await apiClient.processDocument(singleDoc.document_id, singleDoc.extracted_text);
                lastActivityTime = Date.now();
                continue;
              }
              throw new Error('Processing appears to be stuck. The document may be too large. Please try again or contact support.');
            }
          }

          // Update progress bar based on chunks
          if (statusData.total_chunks && statusData.processed_chunks) {
            const chunkProgress = (statusData.processed_chunks / statusData.total_chunks) * 100;
            setProgress(10 + chunkProgress * 0.8);
          }

          const isComplete = statusData.status === 'complete' ||
            (statusData.status?.includes('AI analysis complete') && statusData.results);

          if (isComplete) {
            finalResults = statusData.results;
            break;
          } else if (statusData.status === 'error') {
            throw new Error(statusData.error || 'Processing failed');
          }

          pollAttempts++;
        }

        if (pollAttempts >= MAX_POLL_ATTEMPTS) {
          throw new Error('Processing timed out after 60 minutes. Document may be too large.');
        }
      }

      setResults(finalResults || []);
      setProjectName(stableProjectName);
      setProgress(100);
      setStage("complete");

      toast({
        title: "Analysis complete",
        description: `Successfully analyzed ${files.length} document(s) for "${finalProjectName}".`,
      });
    } catch (err) {
      setStage("error");
      setError(err instanceof Error ? err.message : "An error occurred during processing");
      sessionStorage.removeItem('processing_start_time');
      toast({
        title: "Processing failed",
        description: err instanceof Error ? err.message : "Please try again or contact support.",
        variant: "destructive",
      });
    }
  };

  const handleUpdateAnswer = (resultIndex: number, pairIndex: number, newAnswer: string) => {
    const updatedResults = [...results];
    const updatedPairs = [...updatedResults[resultIndex].pairs];
    updatedPairs[pairIndex] = { ...updatedPairs[pairIndex], answer: newAnswer };
    updatedResults[resultIndex] = { ...updatedResults[resultIndex], pairs: updatedPairs };
    setResults(updatedResults);
  };

  const handleUpdateNormalizedAnswer = (resultIndex: number, pairIndex: number, newAnswer: string) => {
    setResults(prevResults => {
      const updatedResults = [...prevResults];
      const updatedPairs = [...updatedResults[resultIndex].pairs];
      const existingPair = updatedPairs[pairIndex];

      updatedPairs[pairIndex] = {
        ...existingPair,
        normalizedAnswer: newAnswer,
        is_edited: true,
        last_edited_at: existingPair.last_edited_at || new Date().toISOString(),
        last_edited_by_full_name: existingPair.last_edited_by_full_name || user?.full_name || user?.email || 'Unknown',
        last_edited_changes: existingPair.last_edited_changes || {},
      };
      updatedResults[resultIndex] = { ...updatedResults[resultIndex], pairs: updatedPairs };
      return updatedResults;
    });
  };

  const handleUpdateFeedback = (resultIndex: number, pairIndex: number, feedback: "up" | "down" | null) => {
    setResults(prevResults => {
      const updatedResults = [...prevResults];
      const updatedPairs = [...updatedResults[resultIndex].pairs];
      updatedPairs[pairIndex] = { ...updatedPairs[pairIndex], feedback };
      updatedResults[resultIndex] = { ...updatedResults[resultIndex], pairs: updatedPairs };
      return updatedResults;
    });
  };

  const handleSelectAnswer = (resultIndex: number, pairIndex: number) => {
    const updatedResults = results.map((result, rIdx) => {
      if (rIdx !== resultIndex) return result;

      const previousSelectedIndex = result.pairs.findIndex(p =>
        p.is_selected === true && !p.excluded && !p.deleted
      );

      if (previousSelectedIndex === pairIndex) return result;

      const updatedPairs = result.pairs.map((pair, pIdx) => {
        if (pIdx === pairIndex) {
          return {
            ...pair,
            is_selected: true,
            excluded: false,
            restored_by: user?.full_name || user?.email || '',
            restored_at: new Date().toISOString(),
          };
        } else if (pIdx === previousSelectedIndex && previousSelectedIndex >= 0) {
          return {
            ...pair,
            is_selected: false,
            excluded: true,
            excluded_by: user?.full_name || user?.email || '',
            excluded_at: new Date().toISOString(),
          };
        } else {
          return {
            ...pair,
            is_selected: false,
          };
        }
      });

      return { ...result, pairs: updatedPairs };
    });

    setResults(updatedResults);
  };

  const handleExcludeAnswer = (resultIndex: number, pairIndex: number, currentUser: any) => {
    const updatedResults = [...results];
    const updatedPairs = [...updatedResults[resultIndex].pairs];
    updatedPairs[pairIndex] = {
      ...updatedPairs[pairIndex],
      excluded: true,
      excluded_by: currentUser?.fullName || '',
      excluded_at: new Date().toISOString(),
      is_selected: false
    };
    updatedResults[resultIndex] = { ...updatedResults[resultIndex], pairs: updatedPairs };
    setResults(updatedResults);
  };

  const handleIncludeAnswer = (resultIndex: number, pairIndex: number, currentUser: any) => {
    const updatedResults = [...results];
    const updatedPairs = [...updatedResults[resultIndex].pairs];
    updatedPairs[pairIndex] = {
      ...updatedPairs[pairIndex],
      excluded: false,
      restored_by: currentUser?.fullName || '',
      restored_at: new Date().toISOString()
    };
    updatedResults[resultIndex] = { ...updatedResults[resultIndex], pairs: updatedPairs };
    setResults(updatedResults);
  };

  // Mark entire question as Not Applicable
  const handleMarkNotApplicable = async (resultIndex: number) => {
    const now = new Date().toISOString();
    const updatedResults = [...results];
    updatedResults[resultIndex] = {
      ...updatedResults[resultIndex],
      pairs: updatedResults[resultIndex].pairs.map(pair => ({
        ...pair,
        is_not_applicable: true,
        not_applicable_by: user?.full_name || user?.email || '',
        not_applicable_at: now,
      }))
    };
    setResults(updatedResults);

    // Persist to database via API
    if (processingRecordId) {
      try {
        await apiClient.updateResult({
          document_id: processingRecordId,
          question_key: `mark_not_applicable_${resultIndex}`,
          new_value: JSON.stringify(updatedResults),
        });
      } catch (err) {
        console.error('Failed to persist not-applicable state:', err);
      }
    }

    toast({
      title: "Question marked as Not Applicable",
      description: "This question will be excluded from exports.",
    });
  };

  // Restore question from Not Applicable state
  const handleRestoreApplicable = async (resultIndex: number) => {
    const now = new Date().toISOString();
    const updatedResults = [...results];
    updatedResults[resultIndex] = {
      ...updatedResults[resultIndex],
      pairs: updatedResults[resultIndex].pairs.map(pair => ({
        ...pair,
        is_not_applicable: false,
        not_applicable_restored_by: user?.full_name || user?.email || '',
        not_applicable_restored_at: now,
      }))
    };
    setResults(updatedResults);

    // Persist to database via API
    if (processingRecordId) {
      try {
        await apiClient.updateResult({
          document_id: processingRecordId,
          question_key: `restore_applicable_${resultIndex}`,
          new_value: JSON.stringify(updatedResults),
        });
      } catch (err) {
        console.error('Failed to persist restore-applicable state:', err);
      }
    }

    toast({
      title: "Question restored",
      description: "This question will be included in exports.",
    });
  };

  const handleDeleteAnswer = (resultIndex: number, pairIndex: number) => {
    setResults((currentResults) => {
      const updatedResults = [...currentResults];
      const updatedPairs = [...updatedResults[resultIndex].pairs];

      const deletedPair = { ...updatedPairs[pairIndex] };
      updatedPairs.splice(pairIndex, 1);

      if (updatedPairs.length === 0) {
        updatedPairs.push({ answer: "Not Available", reference: "N/A" });
      }

      updatedResults[resultIndex] = { ...updatedResults[resultIndex], pairs: updatedPairs };

      const handleUndo = () => {
        setResults((currentResults) => {
          const restoreResults = [...currentResults];
          const restorePairs = [...restoreResults[resultIndex].pairs];

          const notFoundIndex = restorePairs.findIndex((p) => (p.answer === "Not Found" || p.answer === "Not Available") && p.reference === "N/A");
          if (notFoundIndex >= 0 && restorePairs.length === 1) {
            restorePairs.splice(notFoundIndex, 1);
          }

          restorePairs.splice(pairIndex, 0, deletedPair);
          restoreResults[resultIndex] = { ...restoreResults[resultIndex], pairs: restorePairs };

          toast({
            title: "Answer restored",
            description: "The answer has been restored.",
          });

          return restoreResults;
        });
      };

      toast({
        title: "Answer removed",
        description: "The answer has been removed from the results.",
        action: (
          <Button size="sm" variant="outline" onClick={handleUndo}>
            Undo
          </Button>
        ),
      });

      return updatedResults;
    });
  };

  // Fetch remarks for a project hash
  const fetchRemarks = async (hash: string): Promise<Map<string, any[]>> => {
    try {
      const data = await apiClient.getProjectRemarks(hash);
      const remarks = data?.remarks || [];

      const remarksByRow = new Map<string, any[]>();
      remarks.forEach((remark: any) => {
        if (!remarksByRow.has(remark.row_id)) {
          remarksByRow.set(remark.row_id, []);
        }
        remarksByRow.get(remark.row_id)!.push(remark);
      });

      return remarksByRow;
    } catch (err) {
      console.error("Error fetching remarks:", err);
      return new Map();
    }
  };

  const exportCSV = async () => {
    const remarksByRow = projectHash ? await fetchRemarks(projectHash) : new Map();

    const rows: string[][] = [
      [
        "ID",
        "Category",
        "Question",
        "Extracted Answer",
        "Normalized Answer",
        "Unit",
        "Reference",
        "Confidence",
        "AI Extraction Accuracy",
        "Remarks",
      ],
    ];

    results.forEach((result, resultIndex) => {
      const seen = new Map<string, any>();
      result.pairs.forEach((pair) => {
        if (resultIndex === 0 && !isValidBuildingCodeAnswer(pair.answer)) {
          return;
        }
        if (!seen.has(pair.answer) && !pair.excluded && !pair.deleted) {
          seen.set(pair.answer, pair);
        }
      });
      const uniquePairs = Array.from(seen.values());

      uniquePairs.forEach((pair) => {
        const questionId = resultIndex + 1;
        const displayedAnswer = exportAnswer(pair.answer);
        const normalizedAns = exportAnswer(pair.normalizedAnswer || normalizeAnswer(pair.answer, questionId));
        const unit = extractUnit(pair.answer, questionId);
        const confidence = ((pair.confidence || 0) * 100).toFixed(0) + "%";

        const rowId = pair.id || `${resultIndex}-${pair.answer}`;
        const rowRemarks = remarksByRow.get(rowId) || [];
        const remarksText = rowRemarks
          .map((r: any) => {
            const datePart = new Date(r.created_at).toLocaleDateString('en-US', {
              month: 'short', day: 'numeric', year: 'numeric'
            });
            const timePart = new Date(r.created_at).toLocaleTimeString('en-US', {
              hour: 'numeric', minute: '2-digit', hour12: true
            });
            return `[${r.created_by_full_name} - ${datePart} - ${timePart}]: ${r.remark_text}`;
          })
          .join(" | ");

        rows.push([
          questionId.toString(),
          result.category,
          formatQuestionTitle(result.question, questionId),
          displayedAnswer,
          normalizedAns,
          unit,
          exportAnswer(pair.reference),
          confidence,
          pair.feedback || "",
          remarksText,
        ]);
      });
    });

    const csv = rows.map((row) => row.map((cell) => `"${cell}"`).join(",")).join("\n");

    const blob = new Blob([csv], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    const filename =
      projectId && projectName ? `${projectId}_${projectName}.csv` : `contract-analysis-${Date.now()}.csv`;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);

    toast({
      title: "CSV exported",
      description: "Results have been downloaded.",
    });
  };

  const exportJSON = async () => {
    const remarksByRow = projectHash ? await fetchRemarks(projectHash) : new Map();

    const exportData = results.map((result, resultIndex) => {
      const seen = new Map<string, any>();
      result.pairs.forEach((pair) => {
        if (resultIndex === 0 && !isValidBuildingCodeAnswer(pair.answer)) {
          return;
        }
        if (!seen.has(pair.answer) && !pair.excluded && !pair.deleted) {
          seen.set(pair.answer, pair);
        }
      });
      const uniquePairs = Array.from(seen.values());

      const questionId = resultIndex + 1;
      return {
        id: questionId,
        category: result.category,
        question: formatQuestionTitle(result.question, questionId),
        answers: uniquePairs.map((pair) => {
          const questionId = resultIndex + 1;
          const rowId = pair.id || `${resultIndex}-${pair.answer}`;
          const rowRemarks = remarksByRow.get(rowId) || [];

          return {
            extractedAnswer: exportAnswer(pair.answer),
            normalizedAnswer: exportAnswer(pair.normalizedAnswer || normalizeAnswer(pair.answer, questionId)),
            unit: extractUnit(pair.answer, questionId),
            reference: exportAnswer(pair.reference),
            confidence: (pair.confidence || 0) * 100,
            feedback: pair.feedback || null,
            remarks: rowRemarks.map((r: any) => ({
              author: r.created_by_full_name,
              text: r.remark_text,
              created_at: r.created_at,
            })),
          };
        }),
      };
    });

    const json = JSON.stringify(exportData, null, 2);
    const blob = new Blob([json], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    const filename =
      projectId && projectName ? `${projectId}_${projectName}.json` : `contract-analysis-${Date.now()}.json`;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);

    toast({
      title: "JSON exported",
      description: "Results have been downloaded.",
    });
  };

  if (authLoading) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <p className="text-muted-foreground">Loading...</p>
      </div>
    );
  }

  if (!user) {
    return <Auth onAuthSuccess={handleAuthSuccess} />;
  }

  if (showProfile) {
    return <Profile onSignOut={handleSignOut} />;
  }


  if (currentView === "approval-detail" && reviewingProjectHash) {
    return (
      <div className="h-screen bg-background flex flex-col overflow-hidden">
        <Navbar
          onNavigateToProfile={() => setShowProfile(true)}
          onNavigateToHome={handleNavigateToHome}
          onNavigateToApprovals={handleNavigateToApprovals}
          onNavigateToTickets={handleNavigateToTickets}
          onNavigateToFeedback={handleNavigateToFeedback}
          onNavigateToDashboard={handleNavigateToDashboard}
          onNavigateToAnalytics={handleNavigateToAnalytics}
          onNavigateToAdminSettings={handleNavigateToAdminSettings}
          onSignOut={handleSignOut}
          isSupervisor={isSupervisor}
          isAdmin={isAdmin}
        />
        <main className="flex-1 overflow-auto">
          <div className="container mx-auto px-6 py-6">
            <SupervisorReview
              projectHash={reviewingProjectHash}
              onBack={handleBackToApprovals}
              currentUserId={user?.id || ""}
              currentUserFullName={user?.full_name || user?.email || ""}
              onSaveAndExit={handleSupervisorSaveAndExitToHome}
              onDirtyStateChange={setIsSupervisorReviewDirty}
              onSaveDraft={(saveFn) => { supervisorSaveRef.current = saveFn; }}
              isSupervisor={isSupervisor}
              isAdmin={isAdmin}
            />
          </div>
        </main>
      </div>
    );
  }

  return (
    <div className="h-screen bg-background flex flex-col overflow-hidden">
      <Navbar
        onNavigateToProfile={() => setShowProfile(true)}
        onNavigateToHome={handleNavigateToHome}
        onNavigateToApprovals={handleNavigateToApprovals}
        onNavigateToTickets={handleNavigateToTickets}
        onNavigateToFeedback={handleNavigateToFeedback}
        onNavigateToDashboard={handleNavigateToDashboard}
        onNavigateToAnalytics={handleNavigateToAnalytics}
        onNavigateToAdminSettings={handleNavigateToAdminSettings}
        onSignOut={handleSignOut}
        isSupervisor={isSupervisor}
        isAdmin={isAdmin}
      />

      {/* Main Content */}
      <main className="flex-1 overflow-auto relative">
        <div
          className="fixed inset-0 bg-cover bg-center bg-no-repeat opacity-20 pointer-events-none"
          style={{ backgroundImage: `url(${workflowBackground})` }}
        />
        <div className="container mx-auto px-6 py-6 relative z-10">
          <div className="space-y-6">
            {/* Hero Section - Left aligned */}
            <div className="space-y-4">
              <div className="flex items-center gap-4">
                <img src={ClarkDietrichLogo} alt="ClarkDietrich" className="h-32 w-auto" />
              </div>
              <p className="text-base text-muted-foreground max-w-2xl">
                Upload your contract documents and get instant, structured analysis with AI-powered insights
              </p>
            </div>

            {/* Back to Home Button - Left aligned */}
            {(stage !== "idle" || results.length > 0) && (
              <div className="flex justify-start">
                <Button onClick={handleNewProject} variant="outline" className="gap-2">
                  <Plus className="h-4 w-4" />
                  New Project
                </Button>
              </div>
            )}

            {/* File Upload */}
            <FileUpload
              key={uploadKey}
              onFileSelect={handleFileSelect}
              isProcessing={stage !== "idle" && stage !== "complete" && stage !== "error"}
            />

            {/* Processing Status - Shown as a separate panel */}
            <ProcessingStatus stage={stage} progress={progress} error={error} />

            {/* Results - Shown when available - Full width */}
            {results.length > 0 && (
              <div id="results-section">
              <ResultsDisplay
                  results={results}
                  projectId={projectId}
                  projectName={projectName}
                  processingTimeSeconds={processingTimeSeconds}
                  processingTimeMinutes={debugTimestamps.durationMinutes || undefined}
                  processingRecordId={processingRecordId}
                  projectHash={projectHash}
                  filesMetadata={filesMetadata}
                  onProjectIdChange={setProjectId}
                  onProjectNameChange={setProjectName}
                  onExportCSV={exportCSV}
                  onExportJSON={exportJSON}
                  onUpdateAnswer={handleUpdateAnswer}
                  onUpdateNormalizedAnswer={handleUpdateNormalizedAnswer}
                  onUpdateFeedback={handleUpdateFeedback}
                  onDeleteAnswer={handleDeleteAnswer}
                  onSelectAnswer={handleSelectAnswer}
                  onExcludeAnswer={handleExcludeAnswer}
                  onIncludeAnswer={handleIncludeAnswer}
                  onMarkNotApplicable={handleMarkNotApplicable}
                  onRestoreApplicable={handleRestoreApplicable}
                  onSubmitSuccess={handleSubmitSuccess}
                  onDirtyStateChange={setIsResultsDirty}
                  onSaveCallback={(saveFn) => { saveCallbackRef.current = saveFn; }}
                  onSaveAndExit={handleSaveAndExitToHome}
                />
                {loadedFromCache && (
                  <p className="text-center text-sm text-muted-foreground mt-4">
                    Loaded from cache - no reprocessing needed
                  </p>
                )}
              </div>
            )}

            {/* Projects History - Hidden during processing or when results are displayed */}
            {stage === "idle" && results.length === 0 && (
              <ProjectsHistory
                onPendingProjectClick={handleApprovalProjectClick}
                isAdmin={isAdmin}
                isSupervisor={isSupervisor}
              />
            )}
          </div>
        </div>
      </main>

      {/* Unsaved Changes Dialog - guards internal navigation */}
      <UnsavedChangesDialog
        open={showUnsavedDialog}
        onSaveAndContinue={handleSaveAndContinue}
        onDiscard={handleDiscardChanges}
        onCancel={handleCancelNavigation}
        isSaving={isSavingProgress}
      />

      {/* Supervisor Review Unsaved Changes Dialog - guards navbar navigation from approval-detail */}
      <UnsavedChangesDialog
        open={showSupervisorUnsavedDialog}
        onSaveAndContinue={handleSupervisorSaveAndContinue}
        onDiscard={handleSupervisorDiscardChanges}
        onCancel={handleSupervisorCancelNavigation}
        isSaving={isSavingSupervisorProgress}
      />
    </div>
  );
};

export default Index;
