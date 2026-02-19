import { useState, useEffect, useRef } from "react";
import apiClient from "@/lib/apiClient";
import { useAuth } from "@/hooks/useAuth";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Download, ArrowLeft, RotateCw, FileText, CheckCircle, XCircle, AlertCircle, Loader2, ExternalLink, Pencil, Save, X, Undo2, Trash2, ThumbsUp, ThumbsDown, RotateCcw } from "lucide-react";
import { VerificationCheckmark } from "./VerificationCheckmark";
import { toast } from "sonner";
import { useNavigate } from "react-router-dom";
import { PDFViewerWithAnnotations } from "@/components/PDFViewerWithAnnotations";
import { PDFReference } from "@/components/PDFViewer";
import { PDFSourceCarousel } from "@/components/PDFSourceCarousel";
import { formatQuestionTitle } from "@/lib/questionTitleUtils";
import { ProjectNotes } from "./ProjectNotes";
import { usePdfPreloader } from "@/hooks/usePdfPreloader";
import { useUserRole } from "@/hooks/useUserRole";
import { displayAnswer } from "@/lib/displayUtils";
import { EditNoteIndicator } from "./EditNoteIndicator";
import { 
  buildStructuredReferenceFromRow, 
  waitForPdfReady, 
  jumpToPdfLocation as executeJumpToPdfLocation,
  parseReferencePage,
  parseReferenceFilename,
  findFileIndex
} from "@/lib/referenceNavigation";
import {
  downloadFreshCSV,
  downloadFreshJSON
} from "@/lib/exportUtils";

import { DeflectionCriteriaEditor } from "./DeflectionCriteriaEditor";
import { RemarksColumn } from "./RemarksColumn";
import { normalizeAnswer } from "@/components/ResultsDisplay";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";

interface ProjectDetailProps {
  projectHash: string;
  onBack: () => void;
  onRerun?: (projectData: any) => void;
  requestedVersion?: number;
  isAdmin?: boolean;
  isSupervisorProp?: boolean;
}

export const ProjectDetail = ({ projectHash, onBack, onRerun, requestedVersion, isAdmin, isSupervisorProp }: ProjectDetailProps) => {
  const [project, setProject] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [repairing, setRepairing] = useState(false);
  const [needsRepair, setNeedsRepair] = useState(false);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [diagnostics, setDiagnostics] = useState({
    has_html_snapshot: false,
    has_json_snapshot: false,
    has_csv_artifact: false,
    has_json_artifact: false,
    audit_entries_count: 0,
  });
  const [showDiagnostics, setShowDiagnostics] = useState(false);
  const [loadingPdf, setLoadingPdf] = useState(false);
  const [pdfSources, setPdfSources] = useState<Array<{ name: string; url: string; pageCount?: number; size?: number }>>([]);
  const [selectedPdfIndex, setSelectedPdfIndex] = useState(0);
  const [currentUser, setCurrentUser] = useState<{ id: string; fullName: string; email?: string } | null>(null);
  const [editHistory, setEditHistory] = useState<Record<string, any[]>>({});
  const { preloadMultiplePdfs, getCachedPdf, getPrerenderedFirstPage } = usePdfPreloader();
  const { isSupervisor: isSupervisorFromHook, isAdmin: isAdminFromHook } = useUserRole(currentUser?.id || null);
  
  // Use props if provided, otherwise fall back to hook values
  const canEdit = isAdmin || isSupervisorProp || isAdminFromHook || isSupervisorFromHook;
  const isSupervisor = isSupervisorProp || isSupervisorFromHook;
  
  // Editing state for approved projects
  const [editingRowId, setEditingRowId] = useState<string | null>(null);
  const [editValue, setEditValue] = useState<string>("");
  const [savingEdit, setSavingEdit] = useState(false);
  const [snapshotData, setSnapshotData] = useState<any[] | null>(null);
  
  
  // Deflection Criteria popup editor state
  const [deflectionDialogOpen, setDeflectionDialogOpen] = useState(false);
  const [deflectionEditContext, setDeflectionEditContext] = useState<{
    rowId: string;
    row: any;
  } | null>(null);
  
  // Delete answer confirmation dialog state
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  
  // Feedback loading state for approved projects
  const [feedbackLoading, setFeedbackLoading] = useState<Record<string, boolean>>({});
  const [pendingDeleteRow, setPendingDeleteRow] = useState<{ row: any; rowIndex: number } | null>(null);
  
  // Ref to always have the latest snapshotData for database persistence (prevents race conditions)
  const snapshotDataRef = useRef<any[] | null>(snapshotData);
  useEffect(() => {
    snapshotDataRef.current = snapshotData;
  }, [snapshotData]);
  
  // Regenerate exports state
  const [regeneratingExports, setRegeneratingExports] = useState(false);

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

  // Poll for audit log updates (replaces realtime subscription)
  useEffect(() => {
    if (!projectHash) return;

    const pollEditHistory = async () => {
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

          // Update project.audit_log from the edits (exclude Feedback entries)
          const auditEntries = data
            .filter((edit: any) => edit.column_name !== 'Feedback')
            .map((edit: any) => ({
              row_id: edit.row_id,
              column: edit.column_name,
              old_value: edit.old_value,
              new_value: edit.new_value,
              edited_by: edit.edited_by_full_name,
              edited_by_user_id: edit.edited_by_user_id,
              edited_at: edit.edited_at,
              question_id: edit.question_id,
              question_text: edit.question_text,
              category: edit.category,
            }));

          setProject((prev: any) => {
            if (!prev) return prev;
            return { ...prev, audit_log: auditEntries };
          });
        }
      } catch (error) {
        console.error('Error polling edit history:', error);
      }
    };

    const intervalId = setInterval(pollEditHistory, 30000);
    return () => clearInterval(intervalId);
  }, [projectHash]);

  useEffect(() => {
    const fetchUser = async () => {
      try {
        const me = await apiClient.getMe();
        if (me) {
          setCurrentUser({
            id: me.id,
            fullName: me.full_name || me.email || "Unknown User",
            email: me.email,
          });
        }
      } catch (error) {
        console.error('Error fetching current user:', error);
      }
    };
    fetchUser();
  }, []);

  useEffect(() => {
    fetchProjectDetails();
  }, [projectHash, requestedVersion]);

  // Preload ALL PDF documents immediately when project loads for instant display
  useEffect(() => {
    const preloadAllPdfs = async () => {
      if (!project?.files_metadata || project.files_metadata.length === 0) {
        console.log('ProjectDetail: No files metadata found in project');
        setLoadingPdf(false);
        return;
      }
      
      console.log('ProjectDetail: Starting parallel PDF preload...', project.files_metadata);
      
      try {
        setLoadingPdf(true);
        
        // Get all PDF files
        const pdfFiles = project.files_metadata.filter((f: any) => 
          (f.name || f.file_name || '').toLowerCase().endsWith('.pdf')
        );
        
        if (pdfFiles.length === 0) {
          console.log('ProjectDetail: No PDF files found');
          setLoadingPdf(false);
          return;
        }

        console.log('ProjectDetail: Found PDF files, generating signed URLs:', pdfFiles.length);

        // Generate signed URLs for all PDFs
        const { generateSignedUrls } = await import('@/lib/pdfUtils');
        const signedUrls = await generateSignedUrls(pdfFiles);
        
        if (signedUrls.length === 0) {
          console.error('ProjectDetail: No valid signed URLs generated');
          setLoadingPdf(false);
          return;
        }
        
        // Build pdfSources with metadata for carousel
        const sources = signedUrls.map((signedUrl, idx) => ({
          name: pdfFiles[idx]?.name || pdfFiles[idx]?.file_name || `Document ${idx + 1}`,
          url: signedUrl.signedUrl,
          pageCount: signedUrl.pageCount || pdfFiles[idx]?.pageCount,
          size: pdfFiles[idx]?.size,
        }));
        
        console.log('ProjectDetail: Starting parallel PDF.js document preload for', sources.length, 'PDFs');
        setPdfSources(sources);
        setSelectedPdfIndex(0);
        
        // Preload ALL PDFs in parallel (this is the key optimization)
        await preloadMultiplePdfs(sources.map(s => s.url));
        
        console.log('ProjectDetail: All PDFs preloaded and ready for instant display');
      } catch (error: any) {
        console.error('ProjectDetail: Error preloading PDFs:', error);
        toast.error(`Failed to load PDF previews: ${error.message}`);
      } finally {
        setLoadingPdf(false);
      }
    };

    if (project) {
      console.log('ProjectDetail: Starting PDF preload for project:', project.project_name);
      preloadAllPdfs();
    }
  }, [project, preloadMultiplePdfs]);

  const fetchProjectDetails = async () => {
    try {
      setLoading(true);
      setFetchError(null);

      const data = await apiClient.getFinalizedProject(projectHash, requestedVersion);

      if (data.error) {
        if (data.error === 'NOT_FINALIZED') {
          setFetchError('This project version is not finalized.');
          return;
        }
        throw new Error(data.error);
      }

      // Transform API response to match existing component structure
      const transformedProject = {
        id: data.meta.id, // UUID primary key for notes and other features
        project_hash: data.project_key,
        project_id: data.meta.project_id,
        project_name: data.meta.project_name,
        final_version: data.version,
        submitted_by_full_name: data.meta.submitted_by_full_name,
        submitted_at: data.meta.submitted_at,
        approved_by_full_name: data.meta.approved_by_full_name,
        approved_at: data.meta.approved_at,
        finalized_by_full_name: data.meta.finalized_by_full_name,
        finalized_at: data.meta.finalized_at,
        approval_status: data.meta.approval_status,
        files_metadata: data.meta.files_metadata,
        file_path: data.meta.file_path,
        final_table_snapshot_html: data.snapshots.html,
        final_table_snapshot_json: data.snapshots.json,
        csv_file_path: data.artifacts.find((a: any) => a.type === 'CSV')?.path || null,
        json_file_path: data.artifacts.find((a: any) => a.type === 'JSON')?.path || null,
        audit_log: data.audit || [],
        notes: data.meta.notes || [], // Include all historical notes
        is_finalized: true,
        status: 'completed',
      };

      // Fetch ALL processing records for this project to get individual file paths
      try {
        const allRecords = await apiClient.getProjectRecordsByHash(projectHash);

        if (allRecords && Array.isArray(allRecords) && transformedProject.files_metadata) {
          // Create a map of file names to file paths
          const filePathMap = new Map(
            allRecords.map((r: any) => [r.file_name, r.file_path])
          );

          // Add the individual file path to each file metadata entry
          transformedProject.files_metadata = transformedProject.files_metadata.map((file: any) => ({
            ...file,
            path: filePathMap.get(file.name) || file.path || file.file_path
          }));

          console.log('Updated files_metadata with individual paths:', transformedProject.files_metadata);
        }
      } catch (recordsError) {
        console.error('Error fetching individual file paths:', recordsError);
      }

      setProject(transformedProject);
      // Initialize snapshot data for editing - apply normalization for questions 3-7 if not already JSON
      if (transformedProject.final_table_snapshot_json) {
        const normalizedSnapshot = transformedProject.final_table_snapshot_json.map((row: any) => {
          const questionId = row.question_id;
          if (questionId >= 3 && questionId <= 7 && row.normalized_answer &&
              row.normalized_answer !== "Not Found" && row.normalized_answer !== "Not Available") {
            try {
              JSON.parse(row.normalized_answer);
              return row; // Already valid JSON
            } catch {
              // Apply normalization to convert raw text to structured JSON
              return {
                ...row,
                normalized_answer: normalizeAnswer(row.normalized_answer, questionId)
              };
            }
          }
          return row;
        });
        setSnapshotData(normalizedSnapshot);
      }

      // Build diagnostics
      const diag = {
        has_html_snapshot: !!(data.snapshots.html && typeof data.snapshots.html === 'string' && data.snapshots.html.length > 100),
        has_json_snapshot: !!(data.snapshots.json && Array.isArray(data.snapshots.json) && data.snapshots.json.length > 0),
        has_csv_artifact: !!data.artifacts.find((a: any) => a.type === 'CSV'),
        has_json_artifact: !!data.artifacts.find((a: any) => a.type === 'JSON'),
        audit_entries_count: data.audit?.length || 0,
      };
      setDiagnostics(diag);

      // Check if repair is needed
      if (transformedProject.is_finalized) {
        const needsSnapshot = !diag.has_html_snapshot || !diag.has_json_snapshot;
        const needsArtifacts = !diag.has_csv_artifact || !diag.has_json_artifact;

        if (needsSnapshot || needsArtifacts) {
          console.log("Project needs repair", { needsSnapshot, needsArtifacts });
          setNeedsRepair(true);
          // Automatically trigger repair
          await repairProject();
        }
      }
    } catch (error: any) {
      console.error("Error fetching project:", error);
      toast.error("Failed to load project details");
    } finally {
      setLoading(false);
    }
  };

  const repairProject = async () => {
    try {
      setRepairing(true);
      console.log("Starting project repair...");

      const data = await apiClient.repairProject(projectHash, project?.final_version);

      console.log("Repair result:", data);
      toast.success(data.message || "Project repaired successfully");

      // Refresh project details
      setNeedsRepair(false);
      await fetchProjectDetails();
    } catch (error: any) {
      console.error("Error repairing project:", error);
      toast.error(`Failed to repair project: ${error.message}`);
    } finally {
      setRepairing(false);
    }
  };

  const downloadFile = async (filePath: string, fileName: string) => {
    if (!filePath) {
      toast.error('File is not available for download');
      return;
    }

    try {
      // Get presigned URL from backend
      const presignedData = await apiClient.getPresignedUrl(filePath);

      if (!presignedData?.signed_url) {
        throw new Error('Could not generate download link');
      }

      // Add cache-busting parameter to ensure latest file
      const urlToFetch = `${presignedData.signed_url}${presignedData.signed_url.includes('?') ? '&' : '?'}t=${Date.now()}`;
      const response = await fetch(urlToFetch, { cache: 'no-store' });

      if (!response.ok) {
        throw new Error(`Download failed (${response.status})`);
      }

      const blob = await response.blob();
      const blobUrl = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = blobUrl;
      link.download = fileName;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(blobUrl);
      toast.success(`Downloading ${fileName}`);
    } catch (error: any) {
      console.error('Download error:', error);
      toast.error('Failed to download file');
    }
  };

  const handleRerun = () => {
    if (onRerun && project) {
      onRerun({
        projectName: project.project_name,
        files: project.files_metadata,
      });
    }
  };

  // Download fresh CSV with latest remarks (instead of stale storage files)
  const handleDownloadFreshCSV = async () => {
    if (!project || !snapshotData) return;
    
    try {
      await downloadFreshCSV(
        projectHash,
        snapshotData,
        `${displayName}.csv`
      );
      toast.success(`Downloaded ${displayName}.csv with latest remarks`);
    } catch (error: any) {
      console.error("CSV export error:", error);
      toast.error("Failed to generate CSV");
    }
  };

  // Download fresh JSON with latest remarks (instead of stale storage files)
  const handleDownloadFreshJSON = async () => {
    if (!project || !snapshotData) return;
    
    try {
      await downloadFreshJSON(
        projectHash,
        snapshotData,
        {
          project_name: project.project_name,
          project_id: project.project_id,
          finalized_at: project.finalized_at,
          files_metadata: project.files_metadata,
        },
        `${displayName}.json`
      );
      toast.success(`Downloaded ${displayName}.json with latest remarks`);
    } catch (error: any) {
      console.error("JSON export error:", error);
      toast.error("Failed to generate JSON");
    }
  };

  // Check if a row is a Deflection Criteria question (questions 3-7)
  const isDeflectionCriteria = (row: any): boolean => {
    // Check by category
    if (row.category === 'Deflection Criteria') return true;
    // Check by question_id (3-7)
    const qId = row.question_id;
    if (qId && qId >= 3 && qId <= 7) return true;
    return false;
  };

  // Handle starting to edit a normalized answer
  const handleEditClick = (rowId: string, currentValue: string, row?: any) => {
    // If this is a Deflection Criteria question, open the popup editor
    if (row && isDeflectionCriteria(row)) {
      setDeflectionEditContext({ rowId, row });
      setDeflectionDialogOpen(true);
      return;
    }
    
    // Otherwise use inline editing
    setEditingRowId(rowId);
    setEditValue(currentValue || '');
  };

  // Handle canceling the edit
  const handleCancelEdit = () => {
    setEditingRowId(null);
    setEditValue('');
  };

  // Handle saving deflection criteria from popup editor
  const handleDeflectionSave = async (newValue: string) => {
    if (!deflectionEditContext || !currentUser || !snapshotData || !project) return;
    
    const { rowId, row } = deflectionEditContext;
    const oldValue = row.normalized_answer || '';
    
    // Skip if value hasn't changed
    if (newValue === oldValue) {
      setDeflectionDialogOpen(false);
      setDeflectionEditContext(null);
      return;
    }
    
    setSavingEdit(true);
    
    try {
      // 1. Insert record into result_edits table (audit log)
      const editData = await apiClient.createResultEdit({
        project_hash: projectHash,
        row_id: rowId,
        column_name: 'Normalized Answer',
        old_value: oldValue,
        new_value: newValue,
        edited_by_user_id: currentUser.id,
        edited_by_full_name: currentUser.fullName,
        question_id: row.question_id || null,
        question_text: row.question || null,
        category: row.category || null,
      });

      // 2. Update the local snapshot data
      const updatedSnapshot = snapshotData.map(item => {
        const itemRowId = item.row_id || `${item.question}-${item.category}`;
        if (itemRowId === rowId) {
          return {
            ...item,
            normalized_answer: newValue,
            is_edited: true,
          };
        }
        return item;
      });
      setSnapshotData(updatedSnapshot);

      // 3. Call the API to update the project and regenerate CSV/JSON
      const updateData = await apiClient.updateApprovedProject(
        projectHash,
        updatedSnapshot,
        project.final_version,
      );

      console.log('update-approved-project response:', updateData);

      // 4. Update local project state with new file paths
      if (updateData && updateData.csvPath && updateData.jsonPath) {
        setProject((prev: any) => ({
          ...prev,
          final_table_snapshot_json: updatedSnapshot,
          csv_file_path: updateData.csvPath,
          json_file_path: updateData.jsonPath,
        }));
      } else {
        // Fallback: Refresh project data from server to get new paths
        console.warn('API did not return expected file paths, refreshing project data');
        await fetchProjectDetails();
      }

      // 5. Update edit history
      setEditHistory(prev => ({
        ...prev,
        [rowId]: [editData, ...(prev[rowId] || [])],
      }));

      toast.success('Deflection criteria updated successfully');

      // 6. Close dialog
      setDeflectionDialogOpen(false);
      setDeflectionEditContext(null);
    } catch (error: any) {
      console.error('Error saving deflection edit:', error);
      toast.error(`Failed to save edit: ${error.message}`);
    } finally {
      setSavingEdit(false);
    }
  };

  // Toggle feedback (like/dislike) for approved projects
  const toggleFeedback = async (rowIndex: number, rowId: string, feedbackType: "up" | "down", row: any) => {
    if (!currentUser || !snapshotDataRef.current || !project) return;
    
    const loadingKey = `${rowId}-${feedbackType}`;
    const currentFeedback = row.feedback;
    
    // Toggle: if same feedback type clicked, remove it; otherwise set to new type
    const isSameFeedback = 
      (feedbackType === 'up' && (currentFeedback === 'up' || currentFeedback === 'like' || currentFeedback === 'Up')) ||
      (feedbackType === 'down' && (currentFeedback === 'down' || currentFeedback === 'dislike' || currentFeedback === 'Down'));
    
    const newFeedback = isSameFeedback ? null : feedbackType;
    
    // Store previous state for rollback
    const previousSnapshot = snapshotDataRef.current ? [...snapshotDataRef.current] : null;
    
    setFeedbackLoading(prev => ({ ...prev, [loadingKey]: true }));
    
    try {
      // CRITICAL: Use snapshotDataRef.current to get the LATEST state for database persistence
      // This prevents race conditions when multiple feedback clicks happen rapidly
      const latestSnapshot = snapshotDataRef.current ? [...snapshotDataRef.current] : [];
      latestSnapshot[rowIndex] = { ...latestSnapshot[rowIndex], feedback: newFeedback };
      
      // Update local state optimistically
      setSnapshotData(latestSnapshot);
      
      // Log the feedback change in result_edits
      await apiClient.createResultEdit({
        project_hash: projectHash,
        row_id: rowId,
        column_name: 'Feedback',
        old_value: currentFeedback || 'none',
        new_value: newFeedback || 'none',
        edited_by_user_id: currentUser.id,
        edited_by_full_name: currentUser.fullName || '',
        question_id: row.question_id,
        question_text: row.question,
        category: row.category,
      });

      // Call the API to update and regenerate CSV/JSON exports
      const updateData = await apiClient.updateApprovedProject(
        projectHash,
        latestSnapshot,
        project.final_version,
      );
      
      // Update local project state with new file paths
      if (updateData?.csvPath && updateData?.jsonPath) {
        setProject((prev: any) => ({
          ...prev,
          final_table_snapshot_json: latestSnapshot,
          csv_file_path: updateData.csvPath,
          json_file_path: updateData.jsonPath,
        }));
      } else {
        // Fallback: Refresh project data from server to get new paths
        console.warn('toggleFeedback: API did not return expected file paths, refreshing project data');
        await fetchProjectDetails();
      }

      toast.success('Feedback updated');
    } catch (error) {
      // Rollback on error
      if (previousSnapshot) {
        setSnapshotData(previousSnapshot);
      }
      toast.error('Failed to update feedback');
      console.error('Feedback update error:', error);
    } finally {
      setFeedbackLoading(prev => ({ ...prev, [loadingKey]: false }));
    }
  };

  // Handle saving an edit to a normalized answer
  const handleSaveEdit = async (row: any) => {
    if (!currentUser || !snapshotData || !project) return;
    
    const rowId = row.row_id || `${row.question}-${row.category}`;
    const oldValue = row.normalized_answer || '';
    const newValue = editValue.trim();
    
    // Skip if value hasn't changed
    if (newValue === oldValue) {
      handleCancelEdit();
      return;
    }
    
    setSavingEdit(true);
    
    try {
      // 1. Insert record into result_edits table (audit log)
      const editData = await apiClient.createResultEdit({
        project_hash: projectHash,
        row_id: rowId,
        column_name: 'Normalized Answer',
        old_value: oldValue,
        new_value: newValue,
        edited_by_user_id: currentUser.id,
        edited_by_full_name: currentUser.fullName,
        question_id: row.question_id || null,
        question_text: row.question || null,
        category: row.category || null,
      });

      // 2. Update the local snapshot data
      const updatedSnapshot = snapshotData.map(item => {
        const itemRowId = item.row_id || `${item.question}-${item.category}`;
        if (itemRowId === rowId) {
          return {
            ...item,
            normalized_answer: newValue,
            is_edited: true,
          };
        }
        return item;
      });
      setSnapshotData(updatedSnapshot);

      // 3. Call the API to update the project and regenerate CSV/JSON
      const updateData = await apiClient.updateApprovedProject(
        projectHash,
        updatedSnapshot,
        project.final_version,
      );

      console.log('update-approved-project response:', updateData);

      // 4. Update local project state with new file paths
      if (updateData && updateData.csvPath && updateData.jsonPath) {
        setProject((prev: any) => ({
          ...prev,
          final_table_snapshot_json: updatedSnapshot,
          csv_file_path: updateData.csvPath,
          json_file_path: updateData.jsonPath,
        }));
      } else {
        // Fallback: Refresh project data from server to get new paths
        console.warn('API did not return expected file paths, refreshing project data');
        await fetchProjectDetails();
      }

      // 5. Update edit history
      const key = rowId;
      setEditHistory(prev => ({
        ...prev,
        [key]: [editData, ...(prev[key] || [])],
      }));

      toast.success('Answer updated successfully');

      // Reset editing state
      handleCancelEdit();
    } catch (error: any) {
      console.error('Error saving edit:', error);
      toast.error(`Failed to save edit: ${error.message}`);
    } finally {
      setSavingEdit(false);
    }
  };


  // Handle restoring an excluded/deleted answer
  const handleRestoreAnswer = async (row: any, rowIndex: number) => {
    if (!currentUser || !snapshotData || !project) return;
    
    setSavingEdit(true);
    const rowId = row.row_id || `${row.question}-${row.category}`;
    const wasExcluded = row.excluded === true;
    const wasDeleted = row.deleted === true;
    
    try {
      // 1. Update the local snapshot - remove excluded/deleted flags
      const updatedSnapshot = snapshotData.map((item, idx) => {
        if (idx === rowIndex) {
          const { excluded, deleted, excluded_by, excluded_at, deleted_by, deleted_at, ...rest } = item;
          return {
            ...rest,
            restored_by: currentUser.fullName,
            restored_at: new Date().toISOString(),
          };
        }
        return item;
      });
      setSnapshotData(updatedSnapshot);
      
      // 2. Insert audit log entry
      try {
        await apiClient.createResultEdit({
          project_hash: projectHash,
          row_id: rowId,
          column_name: 'Answer Status',
          old_value: wasExcluded ? 'excluded' : 'deleted',
          new_value: 'restored',
          edited_by_user_id: currentUser.id,
          edited_by_full_name: currentUser.fullName,
          question_id: row.question_id || null,
          question_text: row.question || null,
          category: row.category || null,
        });
      } catch (editError) {
        console.error('Error inserting audit log:', editError);
        // Continue anyway - audit log failure shouldn't block restore
      }

      // 3. Call API to regenerate CSV/JSON
      const updateData = await apiClient.updateApprovedProject(
        projectHash,
        updatedSnapshot,
        project.final_version,
      );
      
      // 4. Update local project state with new file paths
      if (updateData?.csvPath && updateData?.jsonPath) {
        setProject((prev: any) => ({
          ...prev,
          final_table_snapshot_json: updatedSnapshot,
          csv_file_path: updateData.csvPath,
          json_file_path: updateData.jsonPath,
        }));
      } else {
        await fetchProjectDetails();
      }
      
      toast.success('Answer restored and files regenerated');
    } catch (error: any) {
      console.error('Error restoring answer:', error);
      toast.error(`Failed to restore answer: ${error.message}`);
      // Revert local state on failure
      await fetchProjectDetails();
    } finally {
      setSavingEdit(false);
    }
  };

  // Helper function to get all answers for a question_id
  const getAnswersForQuestion = (questionId: number | string | undefined): any[] => {
    if (!snapshotData || !questionId) return [];
    return snapshotData.filter((item: any) => item.question_id === questionId);
  };

  // Helper: Filter rows to show appropriate answers
  // - If user explicitly selected an answer (is_selected: true), show ALL alternatives
  // - If no explicit selection (AI duplicates), show only the FIRST answer
  // - This applies to ALL rows including excluded/deleted (to filter AI duplicates)
  const getDisplayRows = (rows: any[]): any[] => {
    if (!rows) return [];
    
    return rows.filter((row) => {
      // Get ALL rows for this question (including excluded/deleted)
      const allAnswersForQuestion = rows.filter(
        (r: any) => r.question_id === row.question_id
      );
      
      // Single row total - always show
      if (allAnswersForQuestion.length === 1) return true;
      
      // Check if user explicitly selected any answer (on ANY row, including excluded/deleted)
      const hasExplicitSelection = allAnswersForQuestion.some(
        (r: any) => r.is_selected === true
      );
      
      if (hasExplicitSelection) {
        // User made a selection - show ALL rows (user-managed alternatives)
        return true;
      } else {
        // AI-generated duplicates - show only first row (filter duplicates regardless of status)
        const sortedAnswers = [...allAnswersForQuestion].sort((a, b) => {
          const aIndex = parseInt(a.row_id?.split('-')[1] || '0');
          const bIndex = parseInt(b.row_id?.split('-')[1] || '0');
          return aIndex - bIndex;
        });
        return row.row_id === sortedAnswers[0]?.row_id;
      }
    });
  };

  // Helper function to count active (non-deleted/excluded) answers for a question
  const getAnswerCountForQuestion = (questionId: number | string | undefined): number => {
    if (!snapshotData || !questionId) return 0;
    return snapshotData.filter(
      (item) => item.question_id === questionId && !item.excluded && !item.deleted
    ).length;
  };

  // Handle deleting an answer (only when multiple answers exist for the same question)
  const handleDeleteAnswer = async (row: any, rowIndex: number) => {
    if (!currentUser || !snapshotData || !project) return;
    
    setSavingEdit(true);
    const rowId = row.row_id || `${row.question}-${row.category}`;
    
    try {
      // 1. Update the local snapshot - mark as deleted
      const updatedSnapshot = snapshotData.map((item, idx) => {
        if (idx === rowIndex) {
          return {
            ...item,
            deleted: true,
            deleted_by: currentUser.fullName,
            deleted_at: new Date().toISOString(),
          };
        }
        return item;
      });
      setSnapshotData(updatedSnapshot);
      
      // 2. Insert audit log entry
      try {
        await apiClient.createResultEdit({
          project_hash: projectHash,
          row_id: rowId,
          column_name: 'Answer Status',
          old_value: 'active',
          new_value: 'deleted',
          edited_by_user_id: currentUser.id,
          edited_by_full_name: currentUser.fullName,
          question_id: row.question_id || null,
          question_text: row.question || null,
          category: row.category || null,
        });
      } catch (editError) {
        console.error('Error inserting audit log:', editError);
        // Continue anyway - audit log failure shouldn't block delete
      }

      // 3. Call API to regenerate CSV/JSON
      const updateData = await apiClient.updateApprovedProject(
        projectHash,
        updatedSnapshot,
        project.final_version,
      );
      
      // 4. Update local project state with new file paths
      if (updateData?.csvPath && updateData?.jsonPath) {
        setProject((prev: any) => ({
          ...prev,
          final_table_snapshot_json: updatedSnapshot,
          csv_file_path: updateData.csvPath,
          json_file_path: updateData.jsonPath,
        }));
      } else {
        await fetchProjectDetails();
      }
      
      toast.success('Answer deleted and files regenerated');
    } catch (error: any) {
      console.error('Error deleting answer:', error);
      toast.error(`Failed to delete answer: ${error.message}`);
      // Revert local state on failure
      await fetchProjectDetails();
    } finally {
      setSavingEdit(false);
      setDeleteDialogOpen(false);
      setPendingDeleteRow(null);
    }
  };

  // Confirm delete action
  const confirmDeleteAnswer = (row: any, rowIndex: number) => {
    setPendingDeleteRow({ row, rowIndex });
    setDeleteDialogOpen(true);
  };

  // Manually regenerate CSV/JSON exports (for admin/supervisor)
  const regenerateExports = async () => {
    if (!project || !snapshotData) {
      toast.error('No project data available');
      return;
    }
    
    setRegeneratingExports(true);
    
    try {
      const updateData = await apiClient.updateApprovedProject(
        projectHash,
        snapshotData,
        project.final_version,
      );
      
      // Update local project state with new file paths
      if (updateData?.csvPath && updateData?.jsonPath) {
        setProject((prev: any) => ({
          ...prev,
          csv_file_path: updateData.csvPath,
          json_file_path: updateData.jsonPath,
        }));
        
        const activeCount = snapshotData.filter((r: any) => !r.excluded && !r.deleted).length;
        const totalCount = snapshotData.length;
        toast.success(`Exports regenerated: ${activeCount} of ${totalCount} rows exported`);
      } else {
        // Fallback: Refresh project data from server
        await fetchProjectDetails();
        toast.success('Exports regenerated successfully');
      }
    } catch (error: any) {
      console.error('Error regenerating exports:', error);
      toast.error(`Failed to regenerate exports: ${error.message}`);
    } finally {
      setRegeneratingExports(false);
    }
  };

  const handleReferenceClick = async (reference: PDFReference, referenceString?: string) => {
    // Parse filename from reference string to switch to correct PDF if needed
    if (referenceString && pdfSources.length > 0) {
      const targetFileName = parseReferenceFilename(referenceString);
      if (targetFileName) {
        const pdfFiles = pdfSources.map(p => ({ name: p.name, url: p.url }));
        const pdfIndex = findFileIndex(targetFileName, pdfFiles);
        
        if (pdfIndex !== -1) {
          const needsFileSwitch = pdfIndex !== selectedPdfIndex;
          if (needsFileSwitch) {
            setSelectedPdfIndex(pdfIndex);
          }
          
          // Wait for PDF viewer to be ready
          const isReady = await waitForPdfReady(5000);
          
          if (!isReady) {
            toast.error('PDF viewer not ready. Please try again.');
            return;
          }
          
          // Extra delay if file switch happened
          if (needsFileSwitch) {
            await new Promise(resolve => setTimeout(resolve, 200));
          }
          
          executeJumpToPdfLocation(reference.page, reference.x !== undefined ? {
            x: reference.x,
            y: reference.y!,
            width: reference.width!,
            height: reference.height!,
          } : undefined);
          return;
        }
      }
    }
    
    // Direct jump if already on correct PDF or no file switching needed
    const isReady = await waitForPdfReady(2000);
    if (isReady) {
      executeJumpToPdfLocation(reference.page, reference.x !== undefined ? {
        x: reference.x,
        y: reference.y!,
        width: reference.width!,
        height: reference.height!,
      } : undefined);
    } else {
      toast.error('PDF viewer not ready. Please try again.');
    }
  };

  const parseReferenceString = (refString: string, item?: any): PDFReference | null => {
    if (!refString || refString === 'Not Found') return null;
    
    // Parse "filename, Page X" format
    const pageMatch = refString.match(/Page\s+(\d+)/i);
    if (!pageMatch) return null;
    
    const reference: PDFReference = { page: parseInt(pageMatch[1]) };
    
    // Try to extract bounding box coordinates from metadata if available
    if (item?.reference_metadata) {
      const meta = item.reference_metadata;
      if (meta.x !== undefined && meta.y !== undefined && meta.width && meta.height) {
        reference.x = meta.x;
        reference.y = meta.y;
        reference.width = meta.width;
        reference.height = meta.height;
      }
    }
    
    return reference;
  };

  // Format normalized answer for Deflection Criteria as rich text
  const formatNormalizedAnswer = (value: string, category: string): React.ReactNode => {
    // Only apply rich formatting for Deflection Criteria category
    if (category !== 'Deflection Criteria') {
      return displayAnswer(value) || 'N/A';
    }

    try {
      const parsed = JSON.parse(value);
      const items = Array.isArray(parsed) ? parsed : [parsed];

      return (
        <div className="space-y-2 text-xs">
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
                <span className="text-muted-foreground">{item.LimitRatio ?? '—'}</span>
              </div>
              <div>
                <span className="font-medium">Max:</span>{' '}
                <span className="text-muted-foreground">{item.Max ?? '—'}</span>
              </div>
            </div>
          ))}
        </div>
      );
    } catch {
      // If JSON parsing fails, return as-is
      return displayAnswer(value) || 'N/A';
    }
  };

  const renderCellWithReference = (item: any, key: string, category?: string) => {
    const value = item[key];
    let reference = item[`${key}_reference`];

    // Special case: if key is "reference", the value itself is the reference string
    if (key === 'reference' && typeof value === 'string') {
      reference = parseReferenceString(value, item);
    }
    // Handle both object and string references for other fields
    else if (typeof reference === 'string') {
      reference = parseReferenceString(reference, item);
    }

    // Use rich text formatting for normalized_answer in Deflection Criteria
    const displayContent = key === 'normalized_answer' && category
      ? formatNormalizedAnswer(value, category)
      : displayAnswer(value) || 'N/A';

    if (reference && reference.page) {
      const refString = key === 'reference' ? value : item[`${key}_reference`];
      return (
        <button
          type="button"
          className="text-blue-600 hover:text-blue-800 hover:underline cursor-pointer text-left"
          onClick={() => handleReferenceClick(reference, typeof refString === 'string' ? refString : undefined)}
          title={`Jump to page ${reference.page}${reference.x !== undefined ? ' and zoom to highlight' : ''}`}
        >
          {displayContent}
        </button>
      );
    }

    return displayContent;
  };

  if (loading) {
    return (
      <Card className="p-6">
        <div className="flex flex-col items-center justify-center py-12">
          <Loader2 className="h-8 w-8 animate-spin text-primary mb-4" />
          <p className="text-muted-foreground">Loading project details...</p>
        </div>
      </Card>
    );
  }

  if (fetchError) {
    return (
      <Card className="p-6">
        <div className="flex flex-col items-center justify-center py-12">
          <XCircle className="h-12 w-12 text-destructive mb-4" />
          <p className="text-destructive font-semibold mb-2">{fetchError}</p>
          <Button onClick={onBack} variant="outline" className="mt-4">
            <ArrowLeft className="h-4 w-4 mr-2" />
            Back to Projects
          </Button>
        </div>
      </Card>
    );
  }

  if (repairing) {
    return (
      <Card className="p-6">
        <div className="flex flex-col items-center justify-center py-12">
          <Loader2 className="h-8 w-8 animate-spin text-primary mb-4" />
          <p className="text-muted-foreground font-medium">Repairing project data...</p>
          <p className="text-sm text-muted-foreground mt-2">
            Regenerating missing snapshots and artifacts
          </p>
        </div>
      </Card>
    );
  }

  if (!project) {
    return (
      <Card className="p-6">
        <p className="text-center text-muted-foreground">Project not found</p>
      </Card>
    );
  }

  const displayName = project.project_id 
    ? `${project.project_id}_${project.project_name}`
    : project.project_name;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between mb-6">
        <div>
          <Button onClick={onBack} variant="ghost" size="sm" className="mb-2">
            <ArrowLeft className="h-4 w-4 mr-2" />
            Back to Projects History
          </Button>
          <h2 className="text-3xl font-bold">{project.project_name}</h2>
          <div className="flex items-center gap-2 mt-2">
            <Badge variant="outline">Version {project.final_version || 1}</Badge>
            {project.approval_status && (
              <Badge variant={project.approval_status === "APPROVED" ? "default" : "secondary"}>
                {project.approval_status}
              </Badge>
            )}
          </div>
        </div>
        <div className="flex gap-2">
          <Button
            onClick={() => setShowDiagnostics(!showDiagnostics)}
            variant="outline"
            size="sm"
          >
            {showDiagnostics ? "Hide" : "Show"} Diagnostics
          </Button>
          {onRerun && (
            <Button variant="outline" onClick={handleRerun}>
              <RotateCw className="h-4 w-4 mr-2" />
              Re-run with Changes
            </Button>
          )}
        </div>
      </div>

      {/* Diagnostics Panel */}
      {showDiagnostics && (
        <Card className="p-4 mb-4 bg-muted/30">
          <h3 className="font-semibold mb-3 text-sm">Project Diagnostics</h3>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3 text-sm">
            <div className="flex items-center gap-2">
              {diagnostics.has_html_snapshot ? (
                <CheckCircle className="h-4 w-4 text-green-600" />
              ) : (
                <XCircle className="h-4 w-4 text-destructive" />
              )}
              <span>HTML Snapshot</span>
            </div>
            <div className="flex items-center gap-2">
              {diagnostics.has_json_snapshot ? (
                <CheckCircle className="h-4 w-4 text-green-600" />
              ) : (
                <XCircle className="h-4 w-4 text-destructive" />
              )}
              <span>JSON Snapshot</span>
            </div>
            <div className="flex items-center gap-2">
              {diagnostics.has_csv_artifact ? (
                <CheckCircle className="h-4 w-4 text-green-600" />
              ) : (
                <XCircle className="h-4 w-4 text-destructive" />
              )}
              <span>CSV Artifact</span>
            </div>
            <div className="flex items-center gap-2">
              {diagnostics.has_json_artifact ? (
                <CheckCircle className="h-4 w-4 text-green-600" />
              ) : (
                <XCircle className="h-4 w-4 text-destructive" />
              )}
              <span>JSON Artifact</span>
            </div>
            <div className="flex items-center gap-2">
              <FileText className="h-4 w-4 text-muted-foreground" />
              <span>Audit Entries: {diagnostics.audit_entries_count}</span>
            </div>
          </div>
        </Card>
      )}

      {/* Repair Banner */}
      {needsRepair && (
        <Card className="p-4 mb-4 bg-destructive/10 border-destructive/20">
          <div className="flex items-start gap-3">
            <AlertCircle className="h-5 w-5 text-destructive flex-shrink-0 mt-0.5" />
            <div className="flex-1">
              <p className="font-semibold text-destructive">Missing Project Data</p>
              <p className="text-sm text-destructive/90 mt-1">
                Some finalized data is missing. Auto-repair will regenerate it.
              </p>
              <Button
                onClick={repairProject}
                size="sm"
                variant="outline"
                className="mt-3 border-destructive text-destructive hover:bg-destructive hover:text-destructive-foreground"
                disabled={repairing}
              >
                {repairing ? (
                  <>
                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                    Repairing...
                  </>
                ) : (
                  "Run Auto-Repair"
                )}
              </Button>
            </div>
          </div>
        </Card>
      )}

      {/* Analysis Results - Full Width */}
      <Card className="p-6 mb-6">
        <div className="flex items-start justify-between mb-4">
          <div>
            <h2 className="text-2xl font-bold">{displayName}</h2>
            <div className="flex gap-2 mt-2">
              {project.is_finalized && (
                <Badge variant="secondary" className="bg-green-500/10 text-green-600 dark:text-green-400 border-green-500/20">
                  Finalized
                </Badge>
              )}
              {project.final_version && (
                <Badge variant="outline" className="text-xs">
                  Version {project.final_version}
                </Badge>
              )}
            </div>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-4 text-sm">
          <div>
            <span className="text-muted-foreground">Submitted By:</span>
            <p className="font-medium">{project.submitted_by_full_name || "—"}</p>
          </div>
          <div>
            <span className="text-muted-foreground">Submitted At:</span>
            <p className="font-medium">
              {project.submitted_at 
                ? new Date(project.submitted_at).toLocaleString()
                : "—"}
            </p>
          </div>
          <div>
            <span className="text-muted-foreground">Finalized By:</span>
            <p className="font-medium">{project.finalized_by_full_name || "Unknown"}</p>
          </div>
          <div>
            <span className="text-muted-foreground">Finalized At:</span>
            <p className="font-medium">
              {project.finalized_at 
                ? new Date(project.finalized_at).toLocaleString()
                : "N/A"}
            </p>
          </div>
        </div>
      </Card>

      {/* Extracted Results - Full Width */}
      <Card className="p-6">
        <Tabs defaultValue="output" className="w-full">
          <TabsList className="grid w-full grid-cols-5">
            <TabsTrigger value="output">Finalized Output</TabsTrigger>
            <TabsTrigger value="summary">Summary</TabsTrigger>
            <TabsTrigger value="artifacts">Artifacts</TabsTrigger>
            <TabsTrigger value="audit">Audit Log</TabsTrigger>
            <TabsTrigger value="notes">Notes</TabsTrigger>
          </TabsList>

          <TabsContent value="output" className="space-y-4">
            {project.is_finalized ? (
              <div className="space-y-4">
                <div className="flex justify-end gap-2">
                  {/* Regenerate Exports button for admin/supervisor */}
                  {canEdit && (
                    <Button
                      variant="outline"
                      onClick={regenerateExports}
                      disabled={regeneratingExports}
                    >
                      {regeneratingExports ? (
                        <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                      ) : (
                        <RotateCw className="h-4 w-4 mr-2" />
                      )}
                      Regenerate Exports
                    </Button>
                  )}
                  {snapshotData && snapshotData.length > 0 && (
                    <Button
                      variant="secondary"
                      className="bg-green-600 hover:bg-green-700 text-white"
                      onClick={handleDownloadFreshCSV}
                    >
                      <Download className="h-4 w-4 mr-2" />
                      Download CSV
                    </Button>
                  )}
                  {snapshotData && snapshotData.length > 0 && (
                    <Button
                      variant="secondary"
                      className="bg-blue-600 hover:bg-blue-700 text-white"
                      onClick={handleDownloadFreshJSON}
                    >
                      <Download className="h-4 w-4 mr-2" />
                      Download JSON
                    </Button>
                  )}
                </div>
                
                {/* Always use JSON rendering for clickable references */}
                {(snapshotData || project.final_table_snapshot_json) ? (
                  <div className="border rounded-lg overflow-auto max-h-[600px]">
                    <table className="w-full text-sm table-fixed">
                      <thead className="bg-muted sticky top-0">
                        <tr>
                          <th className="px-4 py-2 text-left w-[9%]">Category</th>
                          <th className="px-4 py-2 text-left w-[15%]">Question</th>
                          <th className="px-4 py-2 text-left w-[12%]">Extracted Answer</th>
                          <th className="px-4 py-2 text-left w-[14%]">Normalized Answer</th>
                          <th className="px-4 py-2 text-left w-[5%]">Unit</th>
                          <th className="px-4 py-2 text-left w-[11%]">Reference</th>
                          <th className="px-4 py-2 text-left w-[9%]">AI Extraction Accuracy</th>
                          <th className="px-4 py-2 text-left w-[13%]">Remarks</th>
                          {canEdit && <th className="px-4 py-2 text-left w-[12%]">Actions</th>}
                        </tr>
                      </thead>
                      <tbody>
                        {getDisplayRows(snapshotData || project.final_table_snapshot_json).map((row: any, idx: number) => {
                          const rowId = row.row_id || `${row.question}-${row.category}`;
                          const isEditing = editingRowId === rowId;
                          const isExcluded = row.excluded === true;
                          const isDeleted = row.deleted === true;
                          const isNotApplicable = row.is_not_applicable === true;
                          
                          // Multi-answer detection for verification checkmarks
                          const answersForQuestion = getAnswersForQuestion(row.question_id)
                            .filter((r: any) => !r.excluded && !r.deleted);
                          const hasMultipleAnswers = answersForQuestion.length > 1;
                          const hasExplicitSelection = hasMultipleAnswers && answersForQuestion.some(
                            (r: any) => r.is_selected === true
                          );
                          const isSelected = row.is_selected === true;
                          
                          // Determine if this is the first answer (for fallback when no explicit selection)
                          const isFirstAnswer = hasMultipleAnswers ? (() => {
                            const sortedAnswers = [...answersForQuestion].sort((a, b) => {
                              const aIdx = parseInt(a.row_id?.split('-')[1] || '0');
                              const bIdx = parseInt(b.row_id?.split('-')[1] || '0');
                              return aIdx - bIdx;
                            });
                            return sortedAnswers[0]?.row_id === row.row_id;
                          })() : true;
                          
                          const isUnselectedAlternative = hasMultipleAnswers && !isExcluded && !isDeleted && 
                            (hasExplicitSelection ? !isSelected : !isFirstAnswer);
                          
                          const isGrayed = isExcluded || isDeleted || isUnselectedAlternative;
                          const hasEdits = row.is_edited === true;
                          
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
                          } else if (isUnselectedAlternative) {
                            tooltipText = 'Alternative answer (not selected)';
                          }
                          
                          // N/A questions get special styling with line-through on all columns
                          const rowStyle = isNotApplicable 
                            ? 'bg-gray-100 dark:bg-gray-800/30' 
                            : isGrayed 
                              ? 'bg-[#f2f2f2] dark:bg-gray-800/50' 
                              : '';
                          const textStyle = isNotApplicable
                            ? 'text-[#888888] dark:text-gray-500 line-through'
                            : isGrayed 
                              ? 'text-[#888888] dark:text-gray-500 italic' 
                              : '';
                          const questionStyle = isNotApplicable
                            ? 'text-[#888888] dark:text-gray-500 line-through'
                            : textStyle;
                          
                          return (
                            <tr 
                              key={idx} 
                              className={`border-t transition-all duration-300 ${rowStyle}`}
                              title={tooltipText}
                            >
                              <td className={`px-4 py-2 ${textStyle}`}>{row.category}</td>
                              <td className={`px-4 py-2 ${questionStyle}`}>
                                <div className="flex items-center gap-2">
                                  <span>{formatQuestionTitle(row.question)}</span>
                                  {isNotApplicable && (
                                    <Badge variant="outline" className="text-xs bg-gray-200 dark:bg-gray-700 text-[#888888]">
                                      N/A
                                    </Badge>
                                  )}
                                </div>
                              </td>
                              <td className={`px-4 py-2 ${textStyle}`}>{renderCellWithReference(row, 'extracted_answer')}</td>
                              <td className={`px-4 py-2 ${textStyle}`}>
                                {isEditing ? (
                                  <div className="flex items-center gap-1">
                                    <Input
                                      value={editValue}
                                      onChange={(e) => setEditValue(e.target.value)}
                                      className="h-8 text-sm"
                                      autoFocus
                                      disabled={savingEdit}
                                    />
                                  </div>
                                ) : (
                                  <div className="flex items-center gap-1">
                                    {/* Show proper checkmark colors: green for selected, red for edited, grey for alternatives */}
                                    <VerificationCheckmark
                                      isEdited={hasEdits && !isExcluded && !isDeleted && !isUnselectedAlternative}
                                      isSelected={!isExcluded && !isDeleted && !isUnselectedAlternative}
                                      isExcluded={isExcluded}
                                      isDeleted={isDeleted}
                                      hasMultipleAnswers={hasMultipleAnswers}
                                      isClickable={false}
                                      excludedBy={row.excluded_by}
                                      excludedAt={row.excluded_at}
                                      deletedBy={row.deleted_by}
                                      deletedAt={row.deleted_at}
                                    />
                                    {renderCellWithReference(row, 'normalized_answer', row.category)}
                                    <EditNoteIndicator
                                      projectHash={projectHash}
                                      rowId={rowId}
                                      questionText={row.question}
                                    />
                                  </div>
                                )}
                              </td>
                              <td className={`px-4 py-2 ${textStyle}`}>{row.unit}</td>
                              <td className={`px-4 py-2 ${textStyle}`}>{renderCellWithReference(row, 'reference')}</td>
                              <td className={`px-4 py-2 ${textStyle}`}>
                                <div className="flex items-center gap-1">
                                  {/* Show static accuracy icons (read-only in approved projects) */}
                                  {isNotApplicable ? (
                                    <span className="text-muted-foreground text-sm" title="Accuracy rating not applicable for excluded questions">🚫</span>
                                  ) : (row.feedback === 'like' || row.feedback === 'Up' || row.feedback === 'up')
                                    ? <ThumbsUp className="h-4 w-4 text-green-500" />
                                    : (row.feedback === 'dislike' || row.feedback === 'Down' || row.feedback === 'down')
                                      ? <ThumbsDown className="h-4 w-4 text-red-500" />
                                      : null
                                  }
                                  {row.is_edited && (() => {
                                    const rowEdits = editHistory[rowId] || [];
                                    
                                    if (rowEdits.length > 0) {
                                      return (
                                        <TooltipProvider>
                                          <Tooltip>
                                            <TooltipTrigger asChild>
                                              <span className="text-lg cursor-help">✏️</span>
                                            </TooltipTrigger>
                                            <TooltipContent className="max-w-sm">
                                              <div className="space-y-2 text-xs">
                                                <p className="font-semibold">
                                                  Edited by {rowEdits[0].edited_by_full_name}
                                                </p>
                                                <p className="text-muted-foreground">
                                                  {new Date(rowEdits[0].edited_at).toLocaleString()}
                                                </p>
                                                <div className="mt-2 space-y-2">
                                                  {rowEdits.map((edit, editIdx) => (
                                                    <div key={editIdx} className="border-b border-border/50 pb-2 last:border-b-0 last:pb-0">
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
                                              </div>
                                            </TooltipContent>
                                          </Tooltip>
                                        </TooltipProvider>
                                      );
                                    }
                                    return <span className="text-lg">✏️</span>;
                                  })()}
                                  {isExcluded && ' ❌'}
                                  {isDeleted && ' 🗑️'}
                                  {isNotApplicable && ' 🚫'}
                                </div>
                              </td>
                              <td className="px-4 py-2">
                                <RemarksColumn
                                  projectHash={projectHash}
                                  rowId={rowId}
                                  canAddRemark={
                                    currentUser?.email?.toLowerCase() === 'neda.lotfi.ir@gmail.com' && 
                                    (isAdmin || isSupervisor)
                                  }
                                  currentUser={currentUser}
                                />
                              </td>
                              {canEdit && (
                                <td className="px-4 py-2">
                                  {isNotApplicable ? (
                                    // N/A questions are read-only in Approved Projects
                                    <span className="text-xs text-muted-foreground italic">Read-only</span>
                                  ) : isGrayed ? (
                                    // Show Restore button for excluded/deleted rows
                                    <Button
                                      size="sm"
                                      variant="outline"
                                      className="h-7 text-xs text-green-600 hover:text-green-700 hover:bg-green-50 border-green-300"
                                      onClick={() => handleRestoreAnswer(row, idx)}
                                      disabled={savingEdit}
                                    >
                                      {savingEdit ? (
                                        <Loader2 className="h-3 w-3 mr-1 animate-spin" />
                                      ) : (
                                        <Undo2 className="h-3 w-3 mr-1" />
                                      )}
                                      Restore
                                    </Button>
                                  ) : isEditing ? (
                                    <div className="flex items-center gap-1">
                                      <Button
                                        size="sm"
                                        variant="ghost"
                                        className="h-7 w-7 p-0 text-green-600 hover:text-green-700 hover:bg-green-50"
                                        onClick={() => handleSaveEdit(row)}
                                        disabled={savingEdit}
                                      >
                                        {savingEdit ? (
                                          <Loader2 className="h-4 w-4 animate-spin" />
                                        ) : (
                                          <Save className="h-4 w-4" />
                                        )}
                                      </Button>
                                      <Button
                                        size="sm"
                                        variant="ghost"
                                        className="h-7 w-7 p-0 text-destructive hover:text-destructive hover:bg-destructive/10"
                                        onClick={handleCancelEdit}
                                        disabled={savingEdit}
                                      >
                                        <X className="h-4 w-4" />
                                      </Button>
                                    </div>
                                  ) : (
                                    <div className="flex items-center gap-1">
                                      <Button
                                        size="sm"
                                        variant="ghost"
                                        className="h-7 w-7 p-0 text-muted-foreground hover:text-foreground"
                                        onClick={() => handleEditClick(rowId, row.normalized_answer || '', row)}
                                        disabled={editingRowId !== null}
                                        title="Edit answer"
                                      >
                                        <Pencil className="h-4 w-4" />
                                      </Button>
                                      {/* Show delete button only when multiple answers exist for this question */}
                                      {getAnswerCountForQuestion(row.question_id) > 1 && (
                                        <Button
                                          size="sm"
                                          variant="ghost"
                                          className="h-7 w-7 p-0 text-destructive hover:text-destructive hover:bg-destructive/10"
                                          onClick={() => confirmDeleteAnswer(row, idx)}
                                          disabled={editingRowId !== null || savingEdit}
                                          title="Delete this answer"
                                        >
                                          <Trash2 className="h-4 w-4" />
                                        </Button>
                                      )}
                                    </div>
                                  )}
                                </td>
                              )}
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                ) : project.final_table_snapshot_html ? (
                  <div 
                    className="border rounded-lg overflow-auto max-h-[600px] p-4"
                    dangerouslySetInnerHTML={{ __html: project.final_table_snapshot_html }}
                  />
                ) : (
                  <div className="flex flex-col items-center justify-center py-12 border rounded-lg bg-destructive/5">
                    <XCircle className="h-12 w-12 text-destructive mb-4" />
                    <p className="text-destructive font-semibold mb-2">Missing finalized snapshot</p>
                    <p className="text-sm text-muted-foreground mb-4">
                      Attempting auto-repair to regenerate missing data...
                    </p>
                    {!repairing && (
                      <Button onClick={repairProject} variant="destructive">
                        Run Auto-Repair
                      </Button>
                    )}
                  </div>
                )}


                {/* PDF Preview - Under the Output Table */}
                <div className="mt-6">
                  <h3 className="font-semibold mb-3">PDF Preview</h3>
                  
                  {/* PDF Source Carousel */}
                  {pdfSources.length > 0 && (
                    <div className="mb-4">
                      <PDFSourceCarousel
                        sources={pdfSources}
                        selectedIndex={selectedPdfIndex}
                        onSelect={setSelectedPdfIndex}
                      />
                    </div>
                  )}
                  
                  <div className="h-[800px]">
                    {pdfSources.length > 0 && pdfSources[selectedPdfIndex] && (
                      <PDFViewerWithAnnotations 
                        fileUrl={pdfSources[selectedPdfIndex].url} 
                        fileName={pdfSources[selectedPdfIndex].name}
                      />
                    )}
                    {loadingPdf && pdfSources.length === 0 && (
                      <Card className="p-6 h-full flex items-center justify-center">
                        <div className="text-center">
                          <Loader2 className="h-8 w-8 animate-spin text-primary mx-auto mb-4" />
                          <p className="text-muted-foreground">Loading PDF preview...</p>
                        </div>
                      </Card>
                    )}
                  </div>
                </div>
              </div>
            ) : (
              <p className="text-center text-muted-foreground py-8">
                No finalized output available
              </p>
            )}
          </TabsContent>

          <TabsContent value="summary" className="space-y-4">
            <div className="space-y-2">
              <h3 className="font-semibold">Project Information</h3>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <span className="text-sm text-muted-foreground">Project Hash:</span>
                  <p className="font-mono text-xs">{project.project_hash}</p>
                </div>
                <div>
                  <span className="text-sm text-muted-foreground">Status:</span>
                  <p>{project.status}</p>
                </div>
              </div>
            </div>

            {project.files_metadata && (
              <div className="space-y-2">
                <h3 className="font-semibold">Files Processed</h3>
                <div className="space-y-1">
                  {project.files_metadata.map((file: any, idx: number) => {
                    const handleFileClick = async () => {
                      try {
                        const filePath = file.path || file.file_path;

                        if (!filePath) {
                          console.error('No file path found for:', file);
                          toast.error("File not available");
                          return;
                        }

                        // Get presigned URL from backend
                        const presignedData = await apiClient.getPresignedUrl(filePath);

                        if (!presignedData?.signed_url) {
                          console.error('Failed to get presigned URL for:', filePath);
                          toast.error("Failed to open file");
                          return;
                        }

                        // Open in new tab
                        window.open(presignedData.signed_url, '_blank', 'noopener,noreferrer');
                      } catch (error) {
                        console.error("Error opening file:", error);
                        toast.error("Failed to open file");
                      }
                    };

                    return (
                      <button
                        key={idx}
                        onClick={handleFileClick}
                        className="flex items-center gap-2 text-sm p-2 bg-muted rounded hover:bg-muted/80 transition-colors cursor-pointer w-full text-left"
                        title="Click to open PDF in new tab"
                      >
                        <FileText className="h-4 w-4 flex-shrink-0" />
                        <span className="flex-1">{file.name}</span>
                        <span className="text-muted-foreground">({(file.size / 1024).toFixed(1)} KB)</span>
                        <ExternalLink className="h-3 w-3 text-muted-foreground" />
                      </button>
                    );
                  })}
                </div>
              </div>
            )}
          </TabsContent>

          <TabsContent value="artifacts" className="space-y-4">
            <div className="space-y-2">
              <h3 className="font-semibold mb-4">Download Artifacts</h3>
              {snapshotData && snapshotData.length > 0 ? (
                <div className="space-y-2">
                  <Button
                    variant="outline"
                    className="w-full justify-start"
                    onClick={handleDownloadFreshCSV}
                  >
                    <Download className="h-4 w-4 mr-2" />
                    CSV Export (with latest remarks)
                  </Button>
                  <Button
                    variant="outline"
                    className="w-full justify-start"
                    onClick={handleDownloadFreshJSON}
                  >
                    <Download className="h-4 w-4 mr-2" />
                    JSON Export (with latest remarks)
                  </Button>
                </div>
              ) : (
                <div className="flex flex-col items-center justify-center py-12 border rounded-lg bg-destructive/5">
                  <XCircle className="h-12 w-12 text-destructive mb-4" />
                  <p className="text-destructive font-semibold mb-2">No artifacts found for this version</p>
                  <p className="text-sm text-muted-foreground mb-4">
                    Attempting auto-repair to regenerate missing artifacts...
                  </p>
                  {!repairing && (
                    <Button onClick={repairProject} variant="destructive">
                      Run Auto-Repair
                    </Button>
                  )}
                </div>
              )}
            </div>
          </TabsContent>

          <TabsContent value="audit" className="space-y-4">
            {project.audit_log && project.audit_log.length > 0 ? (
              <div className="space-y-2">
                <h3 className="font-semibold mb-4">Complete Edit History</h3>
                <p className="text-sm text-muted-foreground mb-4">
                  All changes made to this project, including edits by users and supervisor approvals.
                </p>
                <div className="space-y-3 max-h-[600px] overflow-y-auto">
                  {project.audit_log.map((edit: any, idx: number) => (
                    <Card key={idx} className="p-4">
                      {/* Question Information */}
                      {edit.question_id && (
                        <div className="mb-3 pb-3 border-b">
                          <div className="flex items-start gap-2">
                            <div className="flex-1">
                              <div className="flex items-center gap-2 mb-1">
                                <Badge variant="secondary" className="text-xs">
                                  Question ID: {edit.question_id}
                                </Badge>
                                {edit.category && (
                                  <Badge variant="outline" className="text-xs">
                                    {edit.category}
                                  </Badge>
                                )}
                              </div>
                              <p className="text-sm font-medium">
                                {edit.question_text || edit.question || 'N/A'}
                              </p>
                            </div>
                          </div>
                        </div>
                      )}
                      
                      {/* Edit Details */}
                      <div className="space-y-2">
                        <div className="flex items-center justify-between text-xs text-muted-foreground">
                          <span>Row ID: {edit.row_id}</span>
                        </div>
                        <div className="pl-4 border-l-2 border-primary/20">
                          <div className="text-sm text-muted-foreground mt-1">
                            <span className="line-through opacity-60">"{edit.old_value || 'empty'}"</span>
                            {' → '}
                            <span className="font-medium text-foreground">"{edit.new_value || 'empty'}"</span>
                          </div>
                          <div className="text-xs text-muted-foreground mt-2">
                            Edited by {edit.edited_by} • {new Date(edit.edited_at).toLocaleString()}
                          </div>
                        </div>
                      </div>
                    </Card>
                  ))}
                </div>
              </div>
            ) : (
              <p className="text-center text-muted-foreground py-8">No edits recorded for this project</p>
            )}
          </TabsContent>

          <TabsContent value="notes" className="space-y-4">
            {currentUser && project ? (
              <ProjectNotes
                projectId={project.id}
                currentUserId={currentUser.id}
                currentUserFullName={currentUser.fullName}
                isSupervisor={isSupervisor}
                approvalStatus={project.approval_status}
              />
            ) : (
              <p className="text-center text-muted-foreground py-8">
                Please sign in to view and add notes
              </p>
            )}
          </TabsContent>
        </Tabs>
      </Card>
      
      {/* Deflection Criteria Popup Editor */}
      <Dialog 
        open={deflectionDialogOpen} 
        onOpenChange={(open) => {
          setDeflectionDialogOpen(open);
          if (!open) {
            setDeflectionEditContext(null);
          }
        }}
      >
        <DialogContent className="max-w-4xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="text-lg font-semibold">
              Edit Deflection Criteria
            </DialogTitle>
            {deflectionEditContext?.row?.question && (
              <p className="text-sm text-muted-foreground mt-1">
                {deflectionEditContext.row.question}
              </p>
            )}
          </DialogHeader>
          <div className="mt-4">
            {deflectionEditContext && (
              <DeflectionCriteriaEditor
                value={deflectionEditContext.row.normalized_answer || ''}
                onSave={handleDeflectionSave}
                onCancel={() => {
                  setDeflectionDialogOpen(false);
                  setDeflectionEditContext(null);
                }}
              />
            )}
          </div>
        </DialogContent>
      </Dialog>


      {/* Delete Answer Confirmation Dialog */}
      <Dialog open={deleteDialogOpen} onOpenChange={(open) => {
        setDeleteDialogOpen(open);
        if (!open) setPendingDeleteRow(null);
      }}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Delete Answer</DialogTitle>
            <DialogDescription>
              Are you sure you want to delete this answer? This action can be undone by restoring the answer later.
            </DialogDescription>
          </DialogHeader>
          {pendingDeleteRow && (
            <div className="py-4 space-y-3">
              <div className="p-3 bg-muted rounded-lg">
                <p className="text-sm font-medium mb-1">
                  {formatQuestionTitle(pendingDeleteRow.row.question, pendingDeleteRow.row.question_id)}
                </p>
                <p className="text-sm text-muted-foreground">
                  <span className="font-medium">Answer:</span> {displayAnswer(pendingDeleteRow.row.normalized_answer) || displayAnswer(pendingDeleteRow.row.extracted_answer) || 'N/A'}
                </p>
              </div>
            </div>
          )}
          <DialogFooter className="flex gap-2 sm:gap-0">
            <Button
              variant="outline"
              onClick={() => {
                setDeleteDialogOpen(false);
                setPendingDeleteRow(null);
              }}
              disabled={savingEdit}
            >
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={() => {
                if (pendingDeleteRow) {
                  handleDeleteAnswer(pendingDeleteRow.row, pendingDeleteRow.rowIndex);
                }
              }}
              disabled={savingEdit}
            >
              {savingEdit ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  Deleting...
                </>
              ) : (
                <>
                  <Trash2 className="h-4 w-4 mr-2" />
                  Delete
                </>
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};