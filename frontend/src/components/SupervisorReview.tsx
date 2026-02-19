import { useState, useEffect, useRef, useCallback } from "react";
import { useAutosaveOnVisibilityChange, useBeforeUnloadWarning } from "@/hooks/useReviewDirtyState";
import { displayAnswer } from "@/lib/displayUtils";
import apiClient from "@/lib/apiClient";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { useToast } from "@/hooks/use-toast";
import { CheckCircle, XCircle, ArrowLeft, Download, RotateCcw, ChevronDown, ChevronRight, FileText, ChevronsUpDown, Check, Users, Loader2, LogOut } from "lucide-react";
import { ResultsDisplay, AnalysisResult, normalizeAnswer, extractUnit } from "./ResultsDisplay";
import { ProjectNotes } from "./ProjectNotes";
import { PDFViewer } from "./PDFViewer";
import { PDFSourceCarousel } from "./PDFSourceCarousel";
import { formatConfidence } from "@/lib/confidenceUtils";
import { generateSignedUrls, SignedUrlResult } from "@/lib/pdfUtils";

import { EditNoteIndicator } from "./EditNoteIndicator";

// Helper to build pending_snapshot_json from results array
// IMPORTANT: Applies normalization for Questions 3-7 (deflection criteria) to ensure structured JSON format
const buildPendingSnapshotJson = (results: AnalysisResult[]): any[] => {
  return results.flatMap((result, idx) => {
    const pairs = result.pairs || [];
    return pairs.map((p: any, pIdx: number) => {
      const questionId = idx + 1;
      let normalizedAnswerValue = p.normalizedAnswer || p.answer || "";
      
      // Apply normalization for Questions 3-7 (deflection criteria) if not already JSON
      if (questionId >= 3 && questionId <= 7 && normalizedAnswerValue && normalizedAnswerValue !== "Not Found" && normalizedAnswerValue !== "Not Available") {
        try {
          // Check if already valid JSON
          JSON.parse(normalizedAnswerValue);
        } catch {
          // Not JSON yet - apply normalization to convert to structured format
          normalizedAnswerValue = normalizeAnswer(normalizedAnswerValue, questionId);
        }
      }
      
      const unit = p.unit || "";
      const editedDetails = p.edited_details || [];
      
      return {
        row_id: `${idx}-${pIdx}`,
        question_id: questionId,
        category: result.category,
        question: result.question,
        extracted_answer: p.answer,
        normalized_answer: normalizedAnswerValue,
        unit: unit,
        reference: typeof p.reference === 'string' ? p.reference : displayAnswer(p.reference),
        confidence: p.confidence ? (typeof p.confidence === 'number' ? formatConfidence(p.answer, p.confidence) : p.confidence) : "",
        feedback: p.feedback === "up" ? "up" : p.feedback === "down" ? "down" : "",
        is_edited: p.is_edited || false,
        last_edited_by_full_name: p.last_edited_by_full_name || "",
        last_edited_at: p.last_edited_at || null,
        edited_details: editedDetails,
        excluded: p.excluded || false,
        excluded_by: p.excluded_by || null,
        excluded_at: p.excluded_at || null,
        restored_by: p.restored_by || null,
        restored_at: p.restored_at || null,
        deleted: p.deleted || false,
        deleted_by: p.deleted_by || null,
        deleted_at: p.deleted_at || null,
        is_selected: p.is_selected || false,
        is_not_applicable: p.is_not_applicable || false,
        not_applicable_by: p.not_applicable_by || null,
        not_applicable_at: p.not_applicable_at || null,
        not_applicable_restored_by: p.not_applicable_restored_by || null,
        not_applicable_restored_at: p.not_applicable_restored_at || null,
      };
    });
  });
};
import { UnsavedChangesDialog } from "./UnsavedChangesDialog";
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
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
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

interface SupervisorReviewProps {
  projectHash: string;
  onBack: () => void;
  currentUserId: string;
  currentUserFullName: string;
  onSaveAndExit?: () => void; // Callback to navigate home after saving
  onDirtyStateChange?: (isDirty: boolean) => void; // Notify parent of dirty state changes
  onSaveDraft?: (saveFn: () => Promise<void>) => void; // Expose save function to parent
  isSupervisor?: boolean;
  isAdmin?: boolean;
}

export function SupervisorReview({
  projectHash,
  onBack,
  currentUserId,
  currentUserFullName,
  onSaveAndExit,
  onDirtyStateChange,
  onSaveDraft,
  isSupervisor = false,
  isAdmin = false,
}: SupervisorReviewProps) {
  const [project, setProject] = useState<any>(null);
  const [results, setResults] = useState<AnalysisResult[]>([]);
  const [localProjectName, setLocalProjectName] = useState<string>("");
  const [localProjectId, setLocalProjectId] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [showApproveDialog, setShowApproveDialog] = useState(false);
  const [showReassignDialog, setShowReassignDialog] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [approvalError, setApprovalError] = useState<string | null>(null);
  const [snapshotMismatch, setSnapshotMismatch] = useState<string | null>(null);
  const [expandedExcluded, setExpandedExcluded] = useState<{[key: number]: boolean}>({});
  const [pdfUrls, setPdfUrls] = useState<SignedUrlResult[]>([]);
  const [loadingPdfs, setLoadingPdfs] = useState(false);
  const [currentPdfIndex, setCurrentPdfIndex] = useState(0);
  
  // Re-assignment state
  const [users, setUsers] = useState<Array<{ user_id: string; full_name: string }>>([]);
  const [selectedReassignUser, setSelectedReassignUser] = useState<string>("");
  const [reassignPopoverOpen, setReassignPopoverOpen] = useState(false);
  const [reassigning, setReassigning] = useState(false);
  
  // Edit history state for immediate pencil icon display
  const [editHistory, setEditHistory] = useState<Record<string, any[]>>({});
  
  // Track unsaved changes for autosave
  const [hasChanges, setHasChanges] = useState(false);
  
  // State for unsaved changes dialog
  const [showUnsavedDialog, setShowUnsavedDialog] = useState(false);
  const [isSavingProgress, setIsSavingProgress] = useState(false);
  const pendingNavigationRef = useRef<(() => void) | null>(null);
  
  // Ref to always have the latest results for database persistence (prevents race conditions)
  const resultsRef = useRef<AnalysisResult[]>(results);
  useEffect(() => {
    resultsRef.current = results;
  }, [results]);
  
  // Autosave function that persists current state to database (including pending_snapshot_json)
  const saveAllChanges = useCallback(async () => {
    if (!project?.id || resultsRef.current.length === 0) return;

    console.log('[SupervisorReview] Auto-saving all changes including snapshot...');

    try {
      // Build the pending snapshot from current results
      const pendingSnapshotJson = buildPendingSnapshotJson(resultsRef.current);

      await apiClient.updateProjectById(project.id, {
        results: resultsRef.current,
        pending_snapshot_json: pendingSnapshotJson,
        is_edited: true,
        updated_at: new Date().toISOString(),
      });

      setHasChanges(false);
      console.log('[SupervisorReview] Auto-save completed with snapshot');

      // Notify any listening components
      window.dispatchEvent(new CustomEvent("project-saved-to-waiting"));
    } catch (error) {
      console.error('[SupervisorReview] Auto-save failed:', error);
    }
  }, [project?.id]);

  // Trigger autosave when tab becomes hidden
  useAutosaveOnVisibilityChange(hasChanges, saveAllChanges);

  // Show browser warning when closing/refreshing with unsaved changes
  useBeforeUnloadWarning(hasChanges);
  
  // Notify parent of dirty state changes
  useEffect(() => {
    if (onDirtyStateChange) {
      onDirtyStateChange(hasChanges);
    }
  }, [hasChanges, onDirtyStateChange]);
  
  // Cleanup timeouts on unmount
  useEffect(() => {
    return () => {
      if (projectNameTimeoutRef.current) {
        clearTimeout(projectNameTimeoutRef.current);
      }
      if (projectIdTimeoutRef.current) {
        clearTimeout(projectIdTimeoutRef.current);
      }
    };
  }, []);
  
  const { toast } = useToast();
  
  // Guarded back handler that checks for unsaved changes
  const handleGuardedBack = useCallback(() => {
    if (hasChanges) {
      pendingNavigationRef.current = onBack;
      setShowUnsavedDialog(true);
      return;
    }
    onBack();
  }, [hasChanges, onBack]);
  
  // Save and continue handler for dialog (saves both results AND pending_snapshot_json)
  const handleSaveAndContinue = useCallback(async () => {
    if (!project?.id) return;

    setIsSavingProgress(true);
    try {
      // Build the pending snapshot from current results
      const pendingSnapshotJson = buildPendingSnapshotJson(resultsRef.current);

      await apiClient.updateProjectById(project.id, {
        results: resultsRef.current,
        pending_snapshot_json: pendingSnapshotJson,
        is_edited: true,
        updated_at: new Date().toISOString(),
        approval_status: "IN_REVIEW_SAVED",
        last_saved_at: new Date().toISOString(),
        saved_by_user_id: currentUserId,
        saved_by_full_name: currentUserFullName,
      });

      setHasChanges(false);
      setShowUnsavedDialog(false);

      toast({
        title: "Changes Saved",
        description: "Your review progress has been saved.",
      });

      // Notify any listening components
      window.dispatchEvent(new CustomEvent("project-saved-to-waiting"));

      // Execute pending navigation
      if (pendingNavigationRef.current) {
        pendingNavigationRef.current();
        pendingNavigationRef.current = null;
      }
    } catch (error) {
      console.error("Save error:", error);
      toast({
        title: "Save Failed",
        description: "Failed to save progress. Please try again.",
        variant: "destructive",
      });
    } finally {
      setIsSavingProgress(false);
    }
  }, [project?.id, currentUserId, currentUserFullName, toast]);
  
  // Expose save function to parent for external dialog handling
  useEffect(() => {
    if (onSaveDraft) {
      onSaveDraft(handleSaveAndContinue);
    }
  }, [onSaveDraft, handleSaveAndContinue]);
  
  // Discard changes handler for dialog
  const handleDiscardChanges = useCallback(() => {
    setShowUnsavedDialog(false);
    setHasChanges(false);
    
    if (pendingNavigationRef.current) {
      pendingNavigationRef.current();
      pendingNavigationRef.current = null;
    }
  }, []);
  
  // Cancel navigation handler for dialog
  const handleCancelNavigation = useCallback(() => {
    setShowUnsavedDialog(false);
    pendingNavigationRef.current = null;
  }, []);

  // Handle save and exit - saves changes and navigates home
  const handleSaveAndExitClick = useCallback(async () => {
    setIsSavingProgress(true);
    try {
      // Build the pending snapshot from current results
      const pendingSnapshotJson = buildPendingSnapshotJson(resultsRef.current);

      await apiClient.updateProjectById(project?.id, {
        results: resultsRef.current,
        pending_snapshot_json: pendingSnapshotJson,
        is_edited: true,
        updated_at: new Date().toISOString(),
        approval_status: "IN_REVIEW_SAVED",
        last_saved_at: new Date().toISOString(),
        saved_by_user_id: currentUserId,
        saved_by_full_name: currentUserFullName,
      });

      setHasChanges(false);

      toast({
        title: "Changes Saved",
        description: "Your review progress has been saved.",
      });

      // Notify any listening components
      window.dispatchEvent(new CustomEvent("project-saved-to-waiting"));

      // Navigate home via callback
      if (onSaveAndExit) {
        onSaveAndExit();
      }
    } catch (error) {
      console.error("Save and exit error:", error);
      toast({
        title: "Save Failed",
        description: "Failed to save progress. Please try again.",
        variant: "destructive",
      });
    } finally {
      setIsSavingProgress(false);
    }
  }, [project?.id, currentUserId, currentUserFullName, toast, onSaveAndExit]);

  useEffect(() => {
    fetchProject();
  }, [projectHash]);

  // Fetch all users for re-assignment
  useEffect(() => {
    const fetchUsers = async () => {
      try {
        const data = await apiClient.getUsersForAssignment();
        if (data) {
          setUsers(Array.isArray(data) ? data : []);
        }
      } catch (error) {
        console.error('Error fetching users for reassignment:', error);
      }
    };

    fetchUsers();
  }, []);

  // Fetch edit history for this project
  useEffect(() => {
    const fetchEditHistory = async () => {
      if (!projectHash) return;

      try {
        const data = await apiClient.getEditHistory(projectHash);

        if (data && Array.isArray(data)) {
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

  // Handle project name changes with debounced autosave
  const projectNameTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const handleProjectNameChange = (newName: string) => {
    setLocalProjectName(newName);

    // Debounced autosave to database
    if (projectNameTimeoutRef.current) {
      clearTimeout(projectNameTimeoutRef.current);
    }
    projectNameTimeoutRef.current = setTimeout(async () => {
      if (!project?.id) return;
      try {
        await apiClient.updateProjectById(project.id, {
          project_name: newName.trim(),
          updated_at: new Date().toISOString(),
        });
      } catch (error) {
        console.error('Error saving project name:', error);
      }
    }, 1000);
  };

  // Handle project ID changes with debounced autosave
  const projectIdTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const handleProjectIdChange = (newId: string) => {
    setLocalProjectId(newId);

    // Debounced autosave to database
    if (projectIdTimeoutRef.current) {
      clearTimeout(projectIdTimeoutRef.current);
    }
    projectIdTimeoutRef.current = setTimeout(async () => {
      if (!project?.id) return;
      try {
        await apiClient.updateProjectById(project.id, {
          project_id: newId.trim(),
          updated_at: new Date().toISOString(),
        });
      } catch (error) {
        console.error('Error saving project ID:', error);
      }
    }, 1000);
  };

  // Handle re-assignment
  const handleReassign = async () => {
    if (!selectedReassignUser) {
      toast({
        title: "Selection Required",
        description: "Please select a user to re-assign this project to.",
        variant: "destructive",
      });
      return;
    }

    const newAssignee = users.find(u => u.user_id === selectedReassignUser);
    if (!newAssignee) return;

    setReassigning(true);
    try {
      // Update project assignment
      await apiClient.updateProjectByHash(projectHash, {
        assigned_supervisor_id: selectedReassignUser,
        assigned_supervisor_name: newAssignee.full_name,
      });

      // Audit log is handled by backend automatically

      toast({
        title: "Project Re-assigned",
        description: `Project has been re-assigned to ${newAssignee.full_name}.`,
      });

      setShowReassignDialog(false);
      setSelectedReassignUser("");
      
      // Refresh project data
      fetchProject();
    } catch (error: any) {
      console.error('Error re-assigning project:', error);
      toast({
        title: "Re-assignment Failed",
        description: error.message || "Failed to re-assign project. Please try again.",
        variant: "destructive",
      });
    } finally {
      setReassigning(false);
    }
  };

  // Load PDFs when project data is available
  useEffect(() => {
    const loadPdfs = async () => {
      if (!project?.files_metadata || project.files_metadata.length === 0) {
        console.log('SupervisorReview: No files metadata found');
        setLoadingPdfs(false);
        return;
      }

      try {
        setLoadingPdfs(true);
        console.log('SupervisorReview: Generating signed URLs for PDFs');
        const signedUrls = await generateSignedUrls(project.files_metadata);
        setPdfUrls(signedUrls);
        console.log('SupervisorReview: PDFs loaded:', signedUrls.length);
      } catch (error) {
        console.error('SupervisorReview: Error loading PDFs:', error);
        toast({
          title: "Error",
          description: "Failed to load PDF previews",
          variant: "destructive",
        });
      } finally {
        setLoadingPdfs(false);
      }
    };

    if (project) {
      loadPdfs();
    }
  }, [project, toast]);

  const fetchProject = async () => {
    try {
      setLoading(true);
      setSnapshotMismatch(null);

      const data = await apiClient.getProjectByHash(projectHash);

      // Enrich files_metadata with individual file paths from all processing records
      if (data.files_metadata && Array.isArray(data.files_metadata)) {
        try {
          const allRecords = await apiClient.getProjectRecordsByHash(projectHash);

          if (allRecords && Array.isArray(allRecords)) {
            // Create a map of file names to file paths
            const filePathMap = new Map(
              allRecords.map((r: any) => [r.file_name, r.file_path])
            );

            // Add the individual file path to each file metadata entry
            data.files_metadata = (data.files_metadata as any[]).map((file: any) => ({
              ...file,
              path: filePathMap.get(file.name) || file.path || file.file_path
            }));

            console.log('SupervisorReview: Updated files_metadata with individual paths:', data.files_metadata);
          }
        } catch (recordsError) {
          console.error('SupervisorReview: Error fetching individual file paths:', recordsError);
        }
      }
      
      // Set project first so UI can render even if snapshot is missing
      setProject(data);
      // Initialize local state for editable fields
      setLocalProjectName(data.project_name || "");
      setLocalProjectId(data.project_id || "");
      
      // CRITICAL: Block if submitted snapshot is missing
      if (!data.pending_snapshot_json || !Array.isArray(data.pending_snapshot_json) || data.pending_snapshot_json.length === 0) {
        setSnapshotMismatch("Submitted snapshot missing. Editor must resubmit the project.");
        setLoading(false);
        return;
      }
      
      // BIND TO PENDING SNAPSHOT ONLY (source of truth for supervisor review)
      // This ensures supervisor sees exact values from submit time, never recomputed
      const snapshotRows = data.pending_snapshot_json as any[];
      
      // Group by question_id to reconstruct the nested structure
      const groupedByQuestion = snapshotRows.reduce((acc: any, row: any) => {
        const qid = row.question_id;
        if (!acc[qid]) {
          acc[qid] = {
            category: row.category,
            question: row.question,
            pairs: []
          };
        }
        acc[qid].pairs.push({
          answer: row.extracted_answer,
          normalizedAnswer: row.normalized_answer,
          unit: row.unit,
          reference: row.reference,
          confidence: row.confidence,
          feedback: row.feedback,
          is_edited: row.is_edited,
          last_edited_by_full_name: row.last_edited_by_full_name,
          last_edited_at: row.last_edited_at,
          originalAnswer: row.is_edited ? row.extracted_answer : undefined,
          edited_details: row.edited_details || [], // Preserve audit history
          excluded: row.excluded || false,
          excluded_by: row.excluded_by,
          excluded_at: row.excluded_at,
          restored_by: row.restored_by,
          restored_at: row.restored_at,
          deleted: row.deleted || false,
          deleted_by: row.deleted_by,
          deleted_at: row.deleted_at,
          is_selected: row.is_selected || false,
          // N/A (Not Applicable) fields for question-level exclusion
          is_not_applicable: row.is_not_applicable || false,
          not_applicable_by: row.not_applicable_by || null,
          not_applicable_at: row.not_applicable_at || null,
          not_applicable_restored_by: row.not_applicable_restored_by || null,
          not_applicable_restored_at: row.not_applicable_restored_at || null,
        });
        return acc;
      }, {});

      const reconstructedResults = Object.values(groupedByQuestion) as AnalysisResult[];
      setResults(reconstructedResults);

      // RUNTIME VALIDATION: Verify UI matches snapshot after render
      setTimeout(() => validateSnapshot(reconstructedResults, snapshotRows), 100);
    } catch (error: any) {
      toast({
        title: "Error",
        description: `Failed to load project: ${error.message}`,
        variant: "destructive",
      });
    } finally {
      setLoading(false);
    }
  };

  // Runtime validation: ensure UI matches submitted snapshot
  const validateSnapshot = (uiResults: AnalysisResult[], snapshotRows: any[]) => {
    try {
      // Build flat representation from UI
      const uiFlat = uiResults.flatMap((result, idx) =>
        result.pairs.map((pair, pairIdx) => ({
          row_id: `${idx}-${pairIdx}`,
          extracted_answer: pair.answer,
          normalized_answer: pair.normalizedAnswer || "",
          unit: pair.unit || "",
        }))
      );

      // Compare each row
      for (const snapshotRow of snapshotRows) {
        const uiRow = uiFlat.find(r => r.row_id === snapshotRow.row_id);
        if (!uiRow) {
          setSnapshotMismatch(`Row ${snapshotRow.row_id} missing in UI. Reloading...`);
          setTimeout(() => fetchProject(), 2000);
          return;
        }

        if (
          uiRow.extracted_answer !== snapshotRow.extracted_answer ||
          uiRow.normalized_answer !== snapshotRow.normalized_answer ||
          uiRow.unit !== snapshotRow.unit
        ) {
          console.error("Snapshot mismatch detected:", {
            row_id: snapshotRow.row_id,
            snapshot: snapshotRow,
            ui: uiRow,
          });
          setSnapshotMismatch(
            `Snapshot mismatch on row ${snapshotRow.row_id}: UI values differ from submitted snapshot. Reloading latest submitted values...`
          );
          setTimeout(() => fetchProject(), 2000);
          return;
        }
      }

      console.log("✅ Snapshot validation passed: UI matches submitted snapshot");
    } catch (error) {
      console.error("Snapshot validation error:", error);
    }
  };

  const handleApprove = async () => {
    try {
      setSubmitting(true);
      setApprovalError(null);

      // Validate required fields before approval - use localProjectId (user's current edit) not project.project_id (stale DB value)
      if (!localProjectId || localProjectId.trim() === '') {
        toast({
          title: "Project ID Required",
          description: "Please enter a Project ID in the 'Waiting for Approval' section before approving this project.",
          variant: "destructive",
        });
        setSubmitting(false);
        setShowApproveDialog(false);
        return;
      }

      // Block if snapshot mismatch detected
      if (snapshotMismatch) {
        toast({
          title: "Cannot Approve",
          description: "Snapshot validation failed. Please wait for reload to complete.",
          variant: "destructive",
        });
        return;
      }

      // NO RECOMPUTATION: Use current UI state directly (from snapshot + any supervisor edits)
      const currentResults = results;

      // Update pending snapshot with supervisor edits (if any)
      // CRITICAL: Ensure normalized_answer and unit are populated for ALL rows
      const updatedSnapshotJson = currentResults.map((result, idx) => {
        const pairs = result.pairs || [];
        return pairs.map((p, pIdx) => {
          // Ensure normalized_answer and unit are always populated (use existing value or fallback to answer)
          const normalizedAnswer = p.normalizedAnswer || p.answer || "";
          const unit = p.unit || "";
          
          // Preserve existing edited_details from snapshot (contains full audit history)
          // This ensures all edit history from users is maintained through supervisor approval
          const editedDetails = (p as any).edited_details || [];
          
          return {
            row_id: `${idx}-${pIdx}`,
            question_id: idx + 1,
            category: result.category,
            question: result.question,
            extracted_answer: p.answer,
            normalized_answer: normalizedAnswer,
            unit: unit,
            reference: displayAnswer(p.reference),
            confidence: p.confidence ? (typeof p.confidence === 'number' ? formatConfidence(p.answer, p.confidence) : p.confidence) : "",
            feedback: p.feedback === "up" ? "up" : p.feedback === "down" ? "down" : "",
            is_edited: p.is_edited || false,
            last_edited_by_full_name: p.last_edited_by_full_name || "",
            last_edited_at: p.last_edited_at || null,
            edited_details: editedDetails,
            excluded: (p as any).excluded || false,
            excluded_by: (p as any).excluded_by || null,
            excluded_at: (p as any).excluded_at || null,
            restored_by: (p as any).restored_by || null,
            restored_at: (p as any).restored_at || null,
            deleted: (p as any).deleted || false,
            deleted_by: (p as any).deleted_by || null,
            deleted_at: (p as any).deleted_at || null,
            is_selected: (p as any).is_selected || false,
            // Not Applicable fields - CRITICAL for crossed-out styling in Approved Projects
            is_not_applicable: (p as any).is_not_applicable || false,
            not_applicable_by: (p as any).not_applicable_by || null,
            not_applicable_at: (p as any).not_applicable_at || null,
            not_applicable_restored_by: (p as any).not_applicable_restored_by || null,
            not_applicable_restored_at: (p as any).not_applicable_restored_at || null,
          };
        });
      }).flat();

      // Generate updated snapshot HTML
      const generateSnapshotHtml = (rows: any[], projectName: string) => {
        const tableRows = rows
          .map((row) => {
            const isExcluded = row.excluded === true;
            const isDeleted = row.deleted === true;
            const isNotApplicable = row.is_not_applicable === true;
            const isGrayed = isExcluded || isDeleted || isNotApplicable;
            
            // Build tooltip text
            let tooltipText = '';
            if (isNotApplicable && row.not_applicable_by && row.not_applicable_at) {
              const naDate = new Date(row.not_applicable_at).toLocaleString();
              tooltipText = `Marked as Not Applicable by ${row.not_applicable_by} on ${naDate}`;
            } else if (isExcluded && row.excluded_by && row.excluded_at) {
              const excludedDate = new Date(row.excluded_at).toLocaleString();
              tooltipText = `This answer was excluded by ${row.excluded_by} on ${excludedDate}`;
            } else if (isDeleted && row.deleted_by && row.deleted_at) {
              const deletedDate = new Date(row.deleted_at).toLocaleString();
              tooltipText = `This answer was deleted by ${row.deleted_by} on ${deletedDate}`;
            }
            
            // N/A rows get line-through styling
            const rowStyle = isNotApplicable
              ? 'background-color: #f5f5f5; color: #888888; text-decoration: line-through;'
              : isGrayed 
                ? 'background-color: #f2f2f2; color: #888888; font-style: italic;' 
                : '';
            const cellStyle = isNotApplicable
              ? 'border: 1px solid #ddd; padding: 8px; color: #888888; text-decoration: line-through;'
              : isGrayed 
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
            <td style="${cellStyle}">${row.confidence}</td>
            <td style="${cellStyle}">${row.feedback}</td>
            <td style="${cellStyle}">${row.is_edited ? "✏️" : ""}${isExcluded ? " ❌" : ""}${isDeleted ? " 🗑️" : ""}${isNotApplicable ? " 🚫" : ""}</td>
          </tr>
        `;
          })
          .join("");
        return `
        <div style="font-family: Arial, sans-serif;">
          <h2 style="color: #333;">${projectName} - Finalized Results</h2>
          <table style="width: 100%; border-collapse: collapse; margin-top: 20px;">
            <thead>
              <tr style="background-color: #f2f2f2;">
                <th style="border: 1px solid #ddd; padding: 8px;">Category</th>
                <th style="border: 1px solid #ddd; padding: 8px;">Question</th>
                <th style="border: 1px solid #ddd; padding: 8px;">Extracted Answer</th>
                <th style="border: 1px solid #ddd; padding: 8px;">Normalized Answer</th>
                <th style="border: 1px solid #ddd; padding: 8px;">Unit</th>
                <th style="border: 1px solid #ddd; padding: 8px;">Reference</th>
                <th style="border: 1px solid #ddd; padding: 8px;">Confidence</th>
                <th style="border: 1px solid #ddd; padding: 8px;">AI Extraction Accuracy</th>
                <th style="border: 1px solid #ddd; padding: 8px;">Edited</th>
              </tr>
            </thead>
            <tbody>
              ${tableRows}
            </tbody>
          </table>
        </div>
      `;
      };

      const updatedSnapshotHtml = generateSnapshotHtml(updatedSnapshotJson, project.project_name);

      // Save updated snapshot to database
      await apiClient.updateProjectByHash(projectHash, {
        results: currentResults,
        pending_snapshot_json: updatedSnapshotJson,
        pending_snapshot_html: updatedSnapshotHtml,
      });

      // Prepare submission results (from snapshot, no recomputation)
      const submissionResults = updatedSnapshotJson;

      // Prepare feedback data
      const feedbackData = currentResults.map((result: any, idx: number) => ({
        question_id: idx + 1,
        question: result.question,
        feedback: (result.pairs || []).map((pair: any) => ({
          answer: pair.answer,
          feedback: pair.feedback,
        })),
      }));

      // Submit with approval
      const responseData = await apiClient.submitProjectForApproval({
        projectHash,
        projectId: project.project_id,
        projectName: project.project_name,
        results: submissionResults,
        feedback: feedbackData,
        hasEdits: project.is_edited || false,
        supervisorApproval: true,
        supervisorId: currentUserId,
        supervisorName: currentUserFullName,
        // Pass snapshot directly for final promotion
        pendingSnapshotJson: updatedSnapshotJson,
        pendingSnapshotHtml: updatedSnapshotHtml,
      });

      if (!responseData?.success) {
        throw new Error("Approval response did not confirm success");
      }

      toast({
        title: "✅ Approved",
        description: "Project approved and published to Previous Projects.",
      });

      onBack();
    } catch (error: any) {
      const errorMessage = error.message || "Unknown error occurred";
      setApprovalError(errorMessage);
      
      // Update project status to ERROR
      try {
        await apiClient.updateProjectByHash(projectHash, {
          approval_status: "ERROR",
          review_note: `Approval failed: ${errorMessage}`,
        });
      } catch (updateErr) {
        console.error('Failed to update error status:', updateErr);
      }

      toast({
        title: "Approval Failed",
        description: errorMessage,
        variant: "destructive",
      });
    } finally {
      setSubmitting(false);
      setShowApproveDialog(false);
    }
  };


  const handleUpdateAnswer = async (resultIndex: number, pairIndex: number, newAnswer: string) => {
    // Extracted Answer is now non-editable - this function is disabled
    toast({
      title: "Edit Not Allowed",
      description: "The Extracted Answer column cannot be edited.",
      variant: "destructive",
    });
    return;
  };

  const handleUpdateNormalizedAnswer = async (
    resultIndex: number,
    pairIndex: number,
    newAnswer: string
  ) => {
    const updatedResults = [...results];
    const pair = updatedResults[resultIndex].pairs[pairIndex];
    
    if (!pair.originalNormalizedAnswer) {
      pair.originalNormalizedAnswer = pair.normalizedAnswer || "";
    }
    
    pair.normalizedAnswer = newAnswer;
    pair.is_edited = true;
    pair.last_edited_by_full_name = currentUserFullName;
    pair.last_edited_at = new Date().toISOString();
    
    if (!pair.last_edited_changes) {
      pair.last_edited_changes = {};
    }
    pair.last_edited_changes["Normalized Answer"] = {
      old: pair.originalNormalizedAnswer,
      new: newAnswer,
    };

    // Automatically trigger dislike feedback when normalized answer is edited
    const previousFeedback = pair.feedback;
    let feedbackWasChanged = false;
    if (previousFeedback !== "down") {
      pair.feedback = "down";
      feedbackWasChanged = true;
    }

    setResults(updatedResults);
    
    // CRITICAL: Synchronously update resultsRef so UI immediately reflects the edited value
    resultsRef.current = updatedResults;
    setHasChanges(true);

    // Regenerate pending snapshot with supervisor edits
    const pendingSnapshotJson = updatedResults.map((result, idx) => {
      const pairs = result.pairs || [];
      return pairs.map((p, pIdx) => {
        // Ensure normalized_answer and unit are always populated
        const normalizedAnswer = p.normalizedAnswer || p.answer || "";
        const unit = p.unit || "";
        
        // ONLY add new edit to the specific row being edited (idx === resultIndex && pIdx === pairIndex)
        const existingDetails = (p as any).edited_details || [];
        let editedDetails = existingDetails;
        
        if (idx === resultIndex && pIdx === pairIndex) {
          const newEdit = {
            column_name: "Normalized Answer",
            old_value: pair.originalNormalizedAnswer,
            new_value: newAnswer,
            edited_by_full_name: currentUserFullName,
            edited_at: new Date().toISOString(),
          };
          editedDetails = [...existingDetails, newEdit];
        }
        
        return {
          row_id: `${idx}-${pIdx}`,
          question_id: idx + 1,
          category: result.category,
          question: result.question,
          extracted_answer: p.answer,
          normalized_answer: normalizedAnswer,
          unit: unit,
          reference: displayAnswer(p.reference),
          confidence: p.confidence ? (typeof p.confidence === 'number' ? formatConfidence(p.answer, p.confidence) : p.confidence) : "",
          feedback: p.feedback === "up" ? "up" : p.feedback === "down" ? "down" : "",
          is_edited: p.is_edited || false,
          last_edited_by_full_name: p.last_edited_by_full_name || "",
          last_edited_at: p.last_edited_at || null,
          edited_details: editedDetails,
          excluded: (p as any).excluded || false,
          excluded_by: (p as any).excluded_by || null,
          excluded_at: (p as any).excluded_at || null,
          restored_by: (p as any).restored_by || null,
          restored_at: (p as any).restored_at || null,
          deleted: (p as any).deleted || false,
          deleted_by: (p as any).deleted_by || null,
          deleted_at: (p as any).deleted_at || null,
          is_selected: (p as any).is_selected || false,
        };
      });
    }).flat();

    // Save to database with updated pending snapshot (use project.id for consistency)
    await apiClient.updateProjectById(project.id, {
      results: updatedResults,
      is_edited: true,
      pending_snapshot_json: pendingSnapshotJson,
    });

    // Record edit in audit log with question metadata
    const result = updatedResults[resultIndex];
    const editData = await apiClient.createResultEdit({
      project_hash: projectHash,
      row_id: `${resultIndex}-${pairIndex}`,
      column_name: "Normalized Answer",
      old_value: pair.originalNormalizedAnswer,
      new_value: newAnswer,
      edited_by_user_id: currentUserId,
      edited_by_full_name: currentUserFullName,
      question_id: resultIndex + 1,
      question_text: result.question,
      category: result.category,
    });

    // Update local editHistory immediately so pencil icon shows right away
    const rowId = `${resultIndex}-${pairIndex}`;
    const newEditEntry = {
      id: editData?.id,
      project_hash: projectHash,
      row_id: rowId,
      column_name: "Normalized Answer",
      old_value: pair.originalNormalizedAnswer,
      new_value: newAnswer,
      edited_by_user_id: currentUserId,
      edited_by_full_name: currentUserFullName,
      edited_at: new Date().toISOString(),
      question_id: resultIndex + 1,
      question_text: result.question,
      category: result.category,
    };
    setEditHistory(prev => ({
      ...prev,
      [rowId]: [newEditEntry, ...(prev[rowId] || [])],
    }));

    // Log automatic feedback change to dislike if it was changed
    if (feedbackWasChanged) {
      await apiClient.createResultEdit({
        project_hash: projectHash,
        row_id: `${resultIndex}-${pairIndex}`,
        column_name: "Feedback",
        old_value: previousFeedback || "none",
        new_value: "down",
        edited_by_user_id: currentUserId,
        edited_by_full_name: currentUserFullName,
        question_id: resultIndex + 1,
        question_text: result.question,
        category: result.category,
      });
    }

  };

  const handleUpdateFeedback = async (
    resultIndex: number,
    pairIndex: number,
    feedback: "up" | "down" | null
  ) => {
    // Store previous state for rollback (use ref for latest state)
    const previousResults = JSON.parse(JSON.stringify(resultsRef.current));
    const oldFeedback = resultsRef.current[resultIndex]?.pairs[pairIndex]?.feedback;
    
    try {
      // CRITICAL: Use resultsRef.current to get the LATEST state for database persistence
      // This prevents race conditions when multiple feedback clicks happen rapidly
      const latestResults = JSON.parse(JSON.stringify(resultsRef.current));
      const result = latestResults[resultIndex];
      
      latestResults[resultIndex].pairs[pairIndex].feedback = feedback;
      
      // Update local state optimistically
      setResults(latestResults);
      resultsRef.current = latestResults;
      setHasChanges(true);
      
      // Build pending snapshot with updated feedback
      const pendingSnapshotJson = buildPendingSnapshotJson(latestResults);

      // Persist to database using the latest merged state (BOTH results AND pending_snapshot_json)
      await apiClient.updateProjectById(project.id, {
        results: latestResults,
        pending_snapshot_json: pendingSnapshotJson,
        is_edited: true,
      });

      // Create audit log entry and get the ID for optional note
      await apiClient.createResultEdit({
        project_hash: projectHash,
        row_id: `${resultIndex}-${pairIndex}`,
        column_name: "Feedback",
        old_value: oldFeedback || "none",
        new_value: feedback || "none",
        edited_by_user_id: currentUserId,
        edited_by_full_name: currentUserFullName,
        question_id: resultIndex + 1,
        question_text: result.question,
        category: result.category,
      });
      
      // Toast notification suppressed for feedback actions
      
    } catch (error) {
      console.error('Error saving feedback:', error);
      
      // Rollback optimistic update
      setResults(previousResults);
      resultsRef.current = previousResults;
      
      toast({
        title: "Couldn't save feedback",
        description: "Please try again.",
        variant: "destructive",
      });
    }
  };

  const handleDeleteAnswer = async (resultIndex: number, pairIndex: number) => {
    const updatedResults = JSON.parse(JSON.stringify(resultsRef.current));
    updatedResults[resultIndex].pairs.splice(pairIndex, 1);
    setResults(updatedResults);
    resultsRef.current = updatedResults;
    setHasChanges(true);
    
    // Build pending snapshot
    const pendingSnapshotJson = buildPendingSnapshotJson(updatedResults);

    await apiClient.updateProjectById(project.id, {
      results: updatedResults,
      pending_snapshot_json: pendingSnapshotJson,
      is_edited: true,
    });
  };

  const handleSelectAnswer = async (resultIndex: number, pairIndex: number) => {
    const latestResults = JSON.parse(JSON.stringify(resultsRef.current));
    const result = latestResults[resultIndex];
    
    // Find the currently selected answer (if any)
    const previousSelectedIndex = result.pairs.findIndex((p: any) => 
      p.is_selected === true && !p.excluded && !p.deleted
    );
    
    // If clicking on the already-selected answer, do nothing
    if (previousSelectedIndex === pairIndex) return;
    
    // Update pairs with proper selection and exclusion logic
    const updatedPairs = result.pairs.map((pair: any, pIdx: number) => {
      if (pIdx === pairIndex) {
        // This is the newly selected answer - make it selected and not excluded
        return {
          ...pair,
          is_selected: true,
          excluded: false,
          restored_by: currentUserFullName,
          restored_at: new Date().toISOString(),
        };
      } else if (pIdx === previousSelectedIndex && previousSelectedIndex >= 0) {
        // This was the previously selected answer - exclude it
        return {
          ...pair,
          is_selected: false,
          excluded: true,
          excluded_by: currentUserFullName,
          excluded_at: new Date().toISOString(),
        };
      } else {
        // For all other answers, just update is_selected to false
        return {
          ...pair,
          is_selected: false,
        };
      }
    });
    
    latestResults[resultIndex].pairs = updatedPairs;
    setResults(latestResults);
    resultsRef.current = latestResults;
    setHasChanges(true);
    
    // Build pending snapshot with updated selection
    const pendingSnapshotJson = buildPendingSnapshotJson(latestResults);
    
    // Persist to database immediately (BOTH results AND pending_snapshot_json)
    try {
      await apiClient.updateProjectById(project.id, {
        results: latestResults,
        pending_snapshot_json: pendingSnapshotJson,
        is_edited: true,
      });
    } catch (error) {
      console.error('Error saving selection:', error);
    }
  };

  // Mark entire question as Not Applicable
  const handleMarkNotApplicable = async (resultIndex: number) => {
    const now = new Date().toISOString();
    const latestResults = JSON.parse(JSON.stringify(resultsRef.current));
    latestResults[resultIndex].pairs = latestResults[resultIndex].pairs.map((pair: any) => ({
      ...pair,
      is_not_applicable: true,
      not_applicable_by: currentUserFullName,
      not_applicable_at: now,
    }));
    
    setResults(latestResults);
    resultsRef.current = latestResults;
    setHasChanges(true);
    
    const pendingSnapshotJson = buildPendingSnapshotJson(latestResults);
    
    await apiClient.updateProjectById(project.id, {
      results: latestResults,
      pending_snapshot_json: pendingSnapshotJson,
      is_edited: true,
    });

    await apiClient.createResultEdit({
      project_hash: projectHash,
      row_id: `${resultIndex}-question`,
      column_name: 'Question Applicability',
      old_value: 'applicable',
      new_value: 'not_applicable',
      edited_by_user_id: currentUserId,
      edited_by_full_name: currentUserFullName,
      question_id: resultIndex + 1,
      question_text: results[resultIndex].question,
      category: results[resultIndex].category,
    });

    toast({ title: "Question marked as Not Applicable" });
  };

  // Restore question from Not Applicable state
  const handleRestoreApplicable = async (resultIndex: number) => {
    const now = new Date().toISOString();
    const latestResults = JSON.parse(JSON.stringify(resultsRef.current));
    latestResults[resultIndex].pairs = latestResults[resultIndex].pairs.map((pair: any) => ({
      ...pair,
      is_not_applicable: false,
      not_applicable_restored_by: currentUserFullName,
      not_applicable_restored_at: now,
    }));
    
    setResults(latestResults);
    resultsRef.current = latestResults;
    setHasChanges(true);
    
    const pendingSnapshotJson = buildPendingSnapshotJson(latestResults);
    
    await apiClient.updateProjectById(project.id, {
      results: latestResults,
      pending_snapshot_json: pendingSnapshotJson,
      is_edited: true,
    });

    await apiClient.createResultEdit({
      project_hash: projectHash,
      row_id: `${resultIndex}-question`,
      column_name: 'Question Applicability',
      old_value: 'not_applicable',
      new_value: 'applicable',
      edited_by_user_id: currentUserId,
      edited_by_full_name: currentUserFullName,
      question_id: resultIndex + 1,
      question_text: results[resultIndex].question,
      category: results[resultIndex].category,
    });

    toast({ title: "Question restored" });
  };


  const handleExcludeAnswer = async (resultIndex: number, pairIndex: number, currentUser: any) => {
    const latestResults = JSON.parse(JSON.stringify(resultsRef.current));
    latestResults[resultIndex].pairs[pairIndex] = {
      ...latestResults[resultIndex].pairs[pairIndex],
      excluded: true,
      excluded_by: currentUser?.fullName || '',
      excluded_at: new Date().toISOString(),
      is_selected: false
    };
    setResults(latestResults);
    resultsRef.current = latestResults;
    setHasChanges(true);
    
    // Build pending snapshot with updated exclusion
    const pendingSnapshotJson = buildPendingSnapshotJson(latestResults);
    
    // Persist to database immediately (BOTH results AND pending_snapshot_json)
    try {
      await apiClient.updateProjectById(project.id, {
        results: latestResults,
        pending_snapshot_json: pendingSnapshotJson,
        is_edited: true,
      });
    } catch (error) {
      console.error('Error saving exclusion:', error);
    }
  };

  const handleIncludeAnswer = async (resultIndex: number, pairIndex: number, currentUser: any) => {
    const latestResults = JSON.parse(JSON.stringify(resultsRef.current));
    latestResults[resultIndex].pairs[pairIndex] = {
      ...latestResults[resultIndex].pairs[pairIndex],
      excluded: false,
      restored_by: currentUser?.fullName || '',
      restored_at: new Date().toISOString()
    };
    setResults(latestResults);
    resultsRef.current = latestResults;
    setHasChanges(true);
    
    // Build pending snapshot with updated inclusion
    const pendingSnapshotJson = buildPendingSnapshotJson(latestResults);
    
    // Persist to database immediately (BOTH results AND pending_snapshot_json)
    try {
      await apiClient.updateProjectById(project.id, {
        results: latestResults,
        pending_snapshot_json: pendingSnapshotJson,
        is_edited: true,
      });
    } catch (error) {
      console.error('Error saving inclusion:', error);
    }
  };

  const handleRestoreAnswer = async (resultIndex: number, pairIndex: number) => {
    const latestResults = JSON.parse(JSON.stringify(resultsRef.current));
    latestResults[resultIndex].pairs[pairIndex] = {
      ...latestResults[resultIndex].pairs[pairIndex],
      excluded: false,
      restored_by: currentUserFullName,
      restored_at: new Date().toISOString()
    };
    
    setResults(latestResults);
    resultsRef.current = latestResults;
    setHasChanges(true);
    
    // Build pending snapshot with restored answer
    const pendingSnapshotJson = buildPendingSnapshotJson(latestResults);

    await apiClient.updateProjectById(project.id, {
      results: latestResults,
      pending_snapshot_json: pendingSnapshotJson,
      is_edited: true,
    });

    const result = latestResults[resultIndex];
    await apiClient.createResultEdit({
      project_hash: projectHash,
      row_id: `${resultIndex}-${pairIndex}`,
      column_name: "Conflict Resolution",
      old_value: "excluded",
      new_value: "restored",
      edited_by_user_id: currentUserId,
      edited_by_full_name: currentUserFullName,
      question_id: resultIndex + 1,
      question_text: result.question,
      category: result.category,
    });

    toast({
      title: "Answer Restored",
      description: "This answer has been restored.",
    });
  };

  if (loading) {
    return (
      <Card className="p-6">
        <p>Loading project...</p>
      </Card>
    );
  }

  if (!project) {
    return (
      <Card className="p-6">
        <p>Project not found</p>
        <Button onClick={handleGuardedBack} className="mt-4">
          <ArrowLeft className="h-4 w-4 mr-2" />
          Back
        </Button>
      </Card>
    );
  }

  // Show snapshot mismatch error if present
  if (snapshotMismatch) {
    return (
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <Button onClick={handleGuardedBack} variant="ghost" size="sm" className="mb-2">
              <ArrowLeft className="h-4 w-4 mr-2" />
              Back to Waiting For Approval
            </Button>
            <h2 className="text-3xl font-bold">{project.project_name}</h2>
            <div className="flex items-center gap-2 mt-2">
              <Badge variant="outline">{project.approval_status}</Badge>
              <span className="text-sm text-muted-foreground">
                Submitted by {project.submitted_by_full_name} on{" "}
                {new Date(project.submitted_at).toLocaleString()}
              </span>
            </div>
          </div>
        </div>

        <Card className="p-6 bg-destructive/10 border-destructive/20">
          <div className="flex items-start gap-3">
            <XCircle className="h-5 w-5 text-destructive flex-shrink-0 mt-0.5" />
            <div className="flex-1">
              <p className="font-semibold text-destructive">Snapshot Validation Failed</p>
              <p className="text-sm text-destructive/90 mt-1">{snapshotMismatch}</p>
              <p className="text-sm text-muted-foreground mt-2">
                The editor needs to resubmit this project to generate a proper snapshot for review.
              </p>
            </div>
          </div>
        </Card>

        <Button onClick={handleGuardedBack} variant="outline">
          <ArrowLeft className="h-4 w-4 mr-2" />
          Back to Waiting For Approval
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <Button onClick={handleGuardedBack} variant="ghost" size="sm" className="mb-2">
            <ArrowLeft className="h-4 w-4 mr-2" />
            Back to Waiting For Approval
          </Button>
          <h2 className="text-3xl font-bold">{project.project_name}</h2>
          <div className="flex items-center gap-2 mt-2">
            <Badge variant="outline">{project.approval_status}</Badge>
            <span className="text-sm text-muted-foreground">
              Submitted by {project.submitted_by_full_name} on{" "}
              {new Date(project.submitted_at).toLocaleString()}
            </span>
          </div>
        </div>
      </div>

      {/* Re-assignment Section */}
      <Card className="p-4 border-border">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Users className="h-5 w-5 text-muted-foreground" />
            <div>
              <p className="text-sm font-medium">Currently Assigned To</p>
              <p className="text-lg font-semibold">
                {project.assigned_supervisor_name || "Unassigned"}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Popover open={reassignPopoverOpen} onOpenChange={setReassignPopoverOpen}>
              <PopoverTrigger asChild>
                <Button variant="outline" size="sm" className="gap-2">
                  <Users className="h-4 w-4" />
                  Re-Assign To
                  <ChevronsUpDown className="h-3 w-3 opacity-50" />
                </Button>
              </PopoverTrigger>
              <PopoverContent className="w-[300px] p-0" align="end">
                <Command>
                  <CommandInput placeholder="Search users..." />
                  <CommandList>
                    <CommandEmpty>No users found.</CommandEmpty>
                    <CommandGroup>
                      {users
                        .filter(u => u.user_id !== project.assigned_supervisor_id)
                        .map((user) => (
                          <CommandItem
                            key={user.user_id}
                            value={user.full_name}
                            onSelect={() => {
                              setSelectedReassignUser(user.user_id);
                              setReassignPopoverOpen(false);
                              setShowReassignDialog(true);
                            }}
                          >
                            <Check
                              className={`mr-2 h-4 w-4 ${
                                selectedReassignUser === user.user_id
                                  ? "opacity-100"
                                  : "opacity-0"
                              }`}
                            />
                            {user.full_name}
                          </CommandItem>
                        ))}
                    </CommandGroup>
                  </CommandList>
                </Command>
              </PopoverContent>
            </Popover>
          </div>
        </div>
      </Card>

      <ResultsDisplay
        results={results}
        projectId={localProjectId}
        projectName={localProjectName}
        processingTimeSeconds={0}
        processingTimeMinutes={undefined}
        processingRecordId={project.id}
        projectHash={project.project_hash}
        filesMetadata={project.files_metadata}
        onProjectIdChange={handleProjectIdChange}
        onProjectNameChange={handleProjectNameChange}
        onExportCSV={() => {}}
        onExportJSON={() => {}}
        onUpdateAnswer={handleUpdateAnswer}
        onUpdateNormalizedAnswer={handleUpdateNormalizedAnswer}
        onUpdateFeedback={handleUpdateFeedback}
        onDeleteAnswer={handleDeleteAnswer}
        onSelectAnswer={handleSelectAnswer}
        onExcludeAnswer={handleExcludeAnswer}
        onIncludeAnswer={handleIncludeAnswer}
        onMarkNotApplicable={handleMarkNotApplicable}
        onRestoreApplicable={handleRestoreApplicable}
        hideSubmitButton={true}
        persistEditsLocally={false}
        externalEditHistory={editHistory}
      />

      {/* Hidden from all users - kept for potential future use */}
      {false && results.some((result) => result.pairs.some((pair: any) => pair.excluded)) && (
        <Card className="mt-6 border-amber-200 bg-amber-50 dark:bg-amber-950/20">
          <div className="p-4">
            <h3 className="text-lg font-semibold mb-4 text-amber-800 dark:text-amber-200">
              Excluded Answers
            </h3>
            <div className="space-y-4">
              {results.map((result, resultIndex) => {
                const excludedPairs = result.pairs.filter((pair: any) => pair.excluded);
                if (excludedPairs.length === 0) return null;
                
                const isExpanded = expandedExcluded[resultIndex];
                
                return (
                  <Collapsible
                    key={resultIndex}
                    open={isExpanded}
                    onOpenChange={(open) => setExpandedExcluded(prev => ({ ...prev, [resultIndex]: open }))}
                  >
                    <div className="border border-amber-300 rounded-lg p-3 bg-white dark:bg-gray-900">
                      <div className="flex items-center justify-between">
                        <div className="flex-1">
                          <p className="font-medium text-sm">Q{resultIndex + 1}: {result.question}</p>
                          <p className="text-xs text-muted-foreground mt-1">{excludedPairs.length} excluded</p>
                        </div>
                        <CollapsibleTrigger asChild>
                          <Button variant="ghost" size="sm">
                            {isExpanded ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
                          </Button>
                        </CollapsibleTrigger>
                      </div>
                      <CollapsibleContent className="mt-3 space-y-2">
                        {excludedPairs.map((pair: any) => {
                          const originalPairIndex = result.pairs.findIndex((p: any) => p === pair);
                          return (
                            <div key={originalPairIndex} className="p-3 bg-amber-100 dark:bg-amber-900/30 rounded border">
                              <p className="text-xs mb-2"><strong>Answer:</strong> {displayAnswer(pair.answer)}</p>
                              <p className="text-xs mb-2"><strong>Excluded by:</strong> {pair.excluded_by}</p>
                              <Button size="sm" variant="outline" onClick={() => handleRestoreAnswer(resultIndex, originalPairIndex)}>
                                <RotateCcw className="h-3 w-3 mr-1" />Restore
                              </Button>
                            </div>
                          );
                        })}
                      </CollapsibleContent>
                    </div>
                  </Collapsible>
                );
              })}
            </div>
          </div>
        </Card>
      )}

      {approvalError && (
        <div className="p-4 bg-destructive/10 border border-destructive/20 rounded-lg mt-6">
          <div className="flex items-start gap-2">
            <XCircle className="h-5 w-5 text-destructive flex-shrink-0 mt-0.5" />
            <div className="flex-1">
              <p className="font-semibold text-destructive">Approval Failed</p>
              <p className="text-sm text-destructive/90 mt-1">{approvalError}</p>
              <Button
                onClick={() => {
                  setApprovalError(null);
                  setShowApproveDialog(true);
                }}
                size="sm"
                variant="outline"
                className="mt-3"
              >
                Retry Approval
              </Button>
            </div>
          </div>
        </div>
      )}

      <div className="mt-6 grid grid-cols-2 gap-3">
        <Button
          variant="outline"
          onClick={handleSaveAndExitClick}
          disabled={isSavingProgress || submitting}
          size="lg"
          className="w-full"
        >
          <LogOut className="h-5 w-5 mr-2" />
          {isSavingProgress ? "Saving..." : "Save and Exit"}
        </Button>
        <Button
          onClick={() => setShowApproveDialog(true)}
          disabled={submitting}
          size="lg"
          className="w-full"
        >
          <CheckCircle className="h-5 w-5 mr-2" />
          Approve & Submit to Approved Projects
        </Button>
      </div>

      {/* Approve Dialog */}
      <AlertDialog open={showApproveDialog} onOpenChange={setShowApproveDialog}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Approve Project?</AlertDialogTitle>
            <AlertDialogDescription>
              This will finalize all edits and publish the project to Approved Projects.
              All users will be able to view this approved project.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={handleApprove} disabled={submitting}>
              Approve & Publish
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Re-assign Confirmation Dialog */}
      <AlertDialog open={showReassignDialog} onOpenChange={setShowReassignDialog}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Re-assign Project?</AlertDialogTitle>
            <AlertDialogDescription>
              This project will be re-assigned to <strong>{users.find(u => u.user_id === selectedReassignUser)?.full_name}</strong> for review.
              <br /><br />
              They will be able to review, edit, and approve this project.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel onClick={() => {
              setShowReassignDialog(false);
              setSelectedReassignUser("");
            }}>
              Cancel
            </AlertDialogCancel>
            <AlertDialogAction onClick={handleReassign} disabled={reassigning}>
              {reassigning ? "Re-assigning..." : "Confirm Re-assign"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Unsaved Changes Dialog */}
      <UnsavedChangesDialog
        open={showUnsavedDialog}
        onSaveAndContinue={handleSaveAndContinue}
        onDiscard={handleDiscardChanges}
        onCancel={handleCancelNavigation}
        isSaving={isSavingProgress}
      />

    </div>
  );
}
