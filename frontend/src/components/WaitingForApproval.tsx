import { useState, useEffect, useRef, useCallback } from "react";
import apiClient from "@/lib/apiClient";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { useToast } from "@/hooks/use-toast";
import { Eye, Download, RefreshCw, Search, Trash2, Pencil, Check } from "lucide-react";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { formatProcessedTime } from "@/lib/timeUtils";
import { fetchProjectRemarks, formatRemarksForJSON, downloadContent } from "@/lib/exportUtils";
import { exportAnswer } from "@/lib/displayUtils";
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

interface PendingProject {
  id: string;
  project_hash: string;
  project_name: string;
  project_id: string;
  assigned_supervisor_name: string;
  assigned_supervisor_id: string;
  submitted_by_full_name: string;
  submitted_at: string;
  approval_status: string;
  final_version: number;
  csv_file_path: string;
  json_file_path: string;
  initial_accuracy?: number;
  final_accuracy?: number;
  processed_time?: number;
  saved_time?: number;
}

interface WaitingForApprovalProps {
  onProjectClick: (projectHash: string) => void;
  currentUserId: string | null;
}

export function WaitingForApproval({ onProjectClick, currentUserId }: WaitingForApprovalProps) {
  const [projects, setProjects] = useState<PendingProject[]>([]);
  const [filteredProjects, setFilteredProjects] = useState<PendingProject[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState("");
  const [assignedToMeOnly, setAssignedToMeOnly] = useState(true);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [projectToDelete, setProjectToDelete] = useState<PendingProject | null>(null);
  const [editingProjectId, setEditingProjectId] = useState<string | null>(null);
  const [editedName, setEditedName] = useState("");
  const [editedProjectIdValue, setEditedProjectIdValue] = useState("");
  const [autoSaveStatus, setAutoSaveStatus] = useState<'idle' | 'saving' | 'saved'>('idle');
  const autoSaveTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const { toast } = useToast();

  const fetchPendingProjects = async (showLoading = true) => {
    try {
      if (showLoading) setLoading(true);
      const data = await apiClient.listPendingProjects();
      setProjects(Array.isArray(data) ? data : (data?.projects || []));
    } catch (error: any) {
      if (showLoading) {
        toast({
          title: "Error",
          description: `Failed to fetch pending projects: ${error.message}`,
          variant: "destructive",
        });
      }
    } finally {
      if (showLoading) setLoading(false);
    }
  };

  useEffect(() => {
    fetchPendingProjects();

    // Listen for save-to-waiting events from navigation guard
    const handleProjectSaved = () => {
      console.log('[WaitingForApproval] Project saved event received, refetching...');
      fetchPendingProjects(false);
    };
    window.addEventListener('project-saved-to-waiting', handleProjectSaved);

    // Poll for updates every 30 seconds (replaces Supabase realtime)
    const interval = setInterval(() => fetchPendingProjects(false), 30000);

    return () => {
      window.removeEventListener('project-saved-to-waiting', handleProjectSaved);
      clearInterval(interval);
      if (autoSaveTimeoutRef.current) {
        clearTimeout(autoSaveTimeoutRef.current);
      }
    };
  }, []);

  useEffect(() => {
    let filtered = projects;

    // Filter by search term
    if (searchTerm) {
      filtered = filtered.filter(
        (p) =>
          p.project_name?.toLowerCase().includes(searchTerm.toLowerCase()) ||
          p.project_id?.toLowerCase().includes(searchTerm.toLowerCase()) ||
          p.assigned_supervisor_name?.toLowerCase().includes(searchTerm.toLowerCase()) ||
          p.submitted_by_full_name?.toLowerCase().includes(searchTerm.toLowerCase())
      );
    }

    // Filter by assigned to me
    if (assignedToMeOnly && currentUserId) {
      filtered = filtered.filter((p) => p.assigned_supervisor_id === currentUserId);
    }

    setFilteredProjects(filtered);
  }, [projects, searchTerm, assignedToMeOnly, currentUserId]);

  // Generate fresh CSV with latest remarks
  const handleDownloadFreshCSV = async (project: PendingProject) => {
    try {
      // Fetch project data to get snapshot
      const projectData = await apiClient.getProjectByHash(project.project_hash);

      const resultsArray = Array.isArray(projectData?.results) ? projectData.results : [];
      const snapshotData = (Array.isArray(projectData?.pending_snapshot_json) ? projectData.pending_snapshot_json : null) ||
        (Array.isArray(projectData?.final_table_snapshot_json) ? projectData.final_table_snapshot_json : null) ||
        resultsArray.map((r: any, idx: number) => ({
          ...r,
          row_id: r.row_id || r.id || `${idx}`,
          question_id: r.question_id || idx + 1,
        }));

      const remarksByRow = await fetchProjectRemarks(project.project_hash);

      const headers = ["ID", "Category", "Question", "Extracted Answer", "Normalized Answer", "Unit", "Reference", "Confidence", "AI Extraction Accuracy", "Remarks"];

      const escapeCSV = (val: any): string => {
        const strVal = String(val ?? "");
        if (strVal.includes(",") || strVal.includes('"') || strVal.includes("\n") || strVal.includes("\r")) {
          return `"${strVal.replace(/"/g, '""')}"`;
        }
        return strVal;
      };

      const rows = snapshotData
        .filter((row: any) => !row.excluded && !row.deleted)
        .map((row: any) => {
          const rowId = row.row_id || row.id || "";
          const rowRemarks = remarksByRow.get(rowId) || [];
          const remarksText = rowRemarks.map((r: any) => {
            const datePart = new Date(r.created_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
            const timePart = new Date(r.created_at).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true });
            return `[${r.created_by_full_name} - ${datePart} - ${timePart}]: ${r.remark_text}`;
          }).join(" | ");

          return [
            row.question_id || "",
            row.category || "",
            row.question || "",
            exportAnswer(row.extracted_answer) || "",
            exportAnswer(row.normalized_answer) || "",
            row.unit || "",
            exportAnswer(row.reference) || "",
            row.confidence ? `${(Number(row.confidence) * 100).toFixed(0)}%` : "",
            row.feedback || "",
            remarksText,
          ].map(escapeCSV).join(",");
        });

      const csvContent = [headers.join(","), ...rows].join("\n");
      const fileName = `${project.project_id}_${project.project_name}.csv`;
      downloadContent(csvContent, fileName, "text/csv;charset=utf-8");

      toast({
        title: "Success",
        description: `Downloaded ${fileName} with latest remarks`,
      });
    } catch (error: any) {
      console.error("CSV download error:", error);
      toast({
        title: "Download Failed",
        description: error.message,
        variant: "destructive",
      });
    }
  };

  // Generate fresh JSON with latest remarks
  const handleDownloadFreshJSON = async (project: PendingProject) => {
    try {
      // Fetch project data to get snapshot
      const projectData = await apiClient.getProjectByHash(project.project_hash);

      const resultsArray = Array.isArray(projectData?.results) ? projectData.results : [];
      const snapshotData = (Array.isArray(projectData?.pending_snapshot_json) ? projectData.pending_snapshot_json : null) ||
        (Array.isArray(projectData?.final_table_snapshot_json) ? projectData.final_table_snapshot_json : null) ||
        resultsArray.map((r: any, idx: number) => ({
          ...r,
          row_id: r.row_id || r.id || `${idx}`,
          question_id: r.question_id || idx + 1,
        }));

      const remarksByRow = await fetchProjectRemarks(project.project_hash);

      const results = snapshotData
        .filter((row: any) => !row.excluded && !row.deleted)
        .map((row: any) => {
          const rowId = row.row_id || row.id || "";
          const rowRemarks = remarksByRow.get(rowId) || [];

          return {
            id: row.question_id || null,
            category: row.category || "",
            question: row.question || "",
            extracted_answer: exportAnswer(row.extracted_answer) || "",
            normalized_answer: exportAnswer(row.normalized_answer) || "",
            unit: row.unit || "",
            reference: exportAnswer(row.reference) || "",
            confidence: row.confidence ? Number(row.confidence) * 100 : null,
            feedback: row.feedback || null,
            row_id: rowId,
            is_edited: row.is_edited || false,
            remarks: formatRemarksForJSON(rowRemarks),
          };
        });

      const jsonContent = JSON.stringify({
        project_id: project.project_id,
        project_name: project.project_name,
        project_hash: project.project_hash,
        submitted_at: project.submitted_at,
        files: projectData?.files_metadata || [],
        results,
      }, null, 2);

      const fileName = `${project.project_id}_${project.project_name}.json`;
      downloadContent(jsonContent, fileName, "application/json;charset=utf-8");

      toast({
        title: "Success",
        description: `Downloaded ${fileName} with latest remarks`,
      });
    } catch (error: any) {
      console.error("JSON download error:", error);
      toast({
        title: "Download Failed",
        description: error.message,
        variant: "destructive",
      });
    }
  };

  const handleDeleteClick = (project: PendingProject) => {
    setProjectToDelete(project);
    setDeleteDialogOpen(true);
  };

  const handleStartEdit = (project: PendingProject) => {
    setEditingProjectId(project.id);
    setEditedName(project.project_name || "");
    setEditedProjectIdValue(project.project_id || "");
  };

  const handleCancelEdit = () => {
    if (autoSaveTimeoutRef.current) {
      clearTimeout(autoSaveTimeoutRef.current);
    }
    setEditingProjectId(null);
    setEditedName("");
    setEditedProjectIdValue("");
    setAutoSaveStatus('idle');
  };

  // Debounced autosave function
  const triggerAutosave = useCallback((projectId: string, name: string, projectIdVal: string) => {
    // Clear any pending autosave
    if (autoSaveTimeoutRef.current) {
      clearTimeout(autoSaveTimeoutRef.current);
    }

    // Don't save if name is empty
    if (!name.trim()) {
      setAutoSaveStatus('idle');
      return;
    }

    // Debounce: wait 1 second of no typing before saving
    autoSaveTimeoutRef.current = setTimeout(async () => {
      setAutoSaveStatus('saving');
      try {
        await apiClient.updateProjectById(projectId, {
          project_name: name.trim(),
          project_id: projectIdVal.trim(),
        });

        setAutoSaveStatus('saved');
        // Refresh list in background
        fetchPendingProjects(false);
        // Reset status after 2 seconds
        setTimeout(() => setAutoSaveStatus('idle'), 2000);
      } catch (error) {
        console.error('Autosave failed:', error);
        setAutoSaveStatus('idle');
      }
    }, 1000);
  }, []);

  const handleDeleteConfirm = async () => {
    if (!projectToDelete) return;

    try {
      await apiClient.deleteProjectById(projectToDelete.id);

      toast({
        title: "Success",
        description: "Pending project deleted.",
      });

      // Refresh the list
      await fetchPendingProjects();
    } catch (error: any) {
      toast({
        title: "Delete Failed",
        description: error.message,
        variant: "destructive",
      });
    } finally {
      setDeleteDialogOpen(false);
      setProjectToDelete(null);
    }
  };

  if (loading) {
    return (
      <Card className="p-6">
        <p className="text-muted-foreground">Loading pending approvals...</p>
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-3xl font-bold">Waiting For Approval</h2>
          <p className="text-muted-foreground mt-1">
            Projects pending supervisor review
          </p>
        </div>
        <Button onClick={() => fetchPendingProjects()} variant="outline" size="icon">
          <RefreshCw className="h-4 w-4" />
        </Button>
      </div>

      <Card className="p-4">
        <div className="space-y-4">
          <div className="flex items-center gap-4">
            <div className="flex-1 relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input
                placeholder="Search by project name, ID, supervisor, or submitter..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="pl-10"
              />
            </div>
            <div className="flex items-center space-x-2">
              <Switch
                id="assigned-to-me"
                checked={assignedToMeOnly}
                onCheckedChange={setAssignedToMeOnly}
              />
              <Label htmlFor="assigned-to-me" className="cursor-pointer">
                Assigned to Me
              </Label>
            </div>
          </div>
        </div>
      </Card>

      {filteredProjects.length === 0 ? (
        <Card className="p-12 text-center">
          <p className="text-muted-foreground">
            {searchTerm || assignedToMeOnly
              ? "No projects match your filters"
              : "No projects waiting for approval"}
          </p>
        </Card>
      ) : (
        <div className="space-y-4">
          {filteredProjects.map((project) => (
            <Card key={project.id} className="p-6">
              <div className="flex items-start justify-between">
                <div className="space-y-2 flex-1">
                  <div className="flex items-center gap-3">
                    {editingProjectId === project.id ? (
                      <>
                        <Input
                          value={editedName}
                          onChange={(e) => {
                            const newName = e.target.value;
                            setEditedName(newName);
                            triggerAutosave(project.id, newName, editedProjectIdValue);
                          }}
                          className="text-xl font-semibold max-w-md h-9"
                          placeholder="Project Name"
                          onKeyDown={(e) => {
                            if (e.key === 'Escape') handleCancelEdit();
                          }}
                        />
                        <span className="text-xs text-muted-foreground whitespace-nowrap">
                          {autoSaveStatus === 'saving' && "Saving..."}
                          {autoSaveStatus === 'saved' && "✓ Saved"}
                        </span>
                      </>
                    ) : (
                      <button
                        onClick={() => onProjectClick(project.project_hash)}
                        className="text-xl font-semibold hover:underline text-primary"
                      >
                        {project.project_name || "Untitled Project"}
                      </button>
                    )}
                    {project.assigned_supervisor_id === currentUserId && (
                      <Badge variant="secondary">Assigned to You</Badge>
                    )}
                  </div>
                  <div className="grid grid-cols-2 gap-x-8 gap-y-2 text-sm">
                    <div className="flex items-center gap-2">
                      <span className="text-muted-foreground">Project ID:</span>{" "}
                      {editingProjectId === project.id ? (
                        <Input
                          value={editedProjectIdValue}
                          onChange={(e) => {
                            const newId = e.target.value;
                            setEditedProjectIdValue(newId);
                            triggerAutosave(project.id, editedName, newId);
                          }}
                          className="inline-block w-40 h-7 text-sm"
                          placeholder="Project ID"
                          onKeyDown={(e) => {
                            if (e.key === 'Escape') handleCancelEdit();
                          }}
                        />
                      ) : (
                        <span className="font-medium">{project.project_id}</span>
                      )}
                    </div>
                    <div>
                      <span className="text-muted-foreground">Supervisor:</span>{" "}
                      <span className="font-medium">
                        {project.assigned_supervisor_name}
                      </span>
                    </div>
                    <div>
                      <span className="text-muted-foreground">Submitted By:</span>{" "}
                      <span className="font-medium">
                        {project.submitted_by_full_name}
                      </span>
                    </div>
                    <div>
                      <span className="text-muted-foreground">Submitted:</span>{" "}
                      <span className="font-medium">
                        {new Date(project.submitted_at).toLocaleString()}
                      </span>
                    </div>
                    <div>
                      <span className="text-muted-foreground">Status:</span>{" "}
                      <Badge
                        variant="outline"
                        className={
                          project.approval_status === "IN_REVIEW_SAVED"
                            ? "bg-blue-50 text-blue-700 border-blue-200"
                            : ""
                        }
                      >
                        {project.approval_status === "IN_REVIEW_SAVED"
                          ? "In Review (Saved)"
                          : project.approval_status}
                      </Badge>
                    </div>
                    <div>
                      <span className="text-muted-foreground">Version:</span>{" "}
                      <span className="font-medium">{project.final_version}</span>
                    </div>
                    {project.processed_time !== undefined && project.processed_time !== null && (
                      <div>
                        <span className="text-muted-foreground">Processing Time:</span>{" "}
                        <span className="font-medium">{formatProcessedTime(project.processed_time)}</span>
                      </div>
                    )}
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  {editingProjectId === project.id ? (
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={handleCancelEdit}
                    >
                      <Check className="h-4 w-4 mr-2" />
                      Done
                    </Button>
                  ) : (
                    <>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => handleStartEdit(project)}
                      >
                        <Pencil className="h-4 w-4 mr-2" />
                        Edit
                      </Button>
                      <Button
                        variant="default"
                        size="sm"
                        onClick={() => onProjectClick(project.project_hash)}
                      >
                        <Eye className="h-4 w-4 mr-2" />
                        Review
                      </Button>
                      <Button
                        variant="destructive"
                        size="sm"
                        onClick={() => handleDeleteClick(project)}
                      >
                        <Trash2 className="h-4 w-4 mr-2" />
                        Delete
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => handleDownloadFreshCSV(project)}
                      >
                        <Download className="h-4 w-4 mr-2" />
                        CSV
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => handleDownloadFreshJSON(project)}
                      >
                        <Download className="h-4 w-4 mr-2" />
                        JSON
                      </Button>
                    </>
                  )}
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}

      <AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete this pending project?</AlertDialogTitle>
            <AlertDialogDescription>
              This will remove the pending project from Waiting For Approval. This action cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={handleDeleteConfirm} className="bg-destructive text-destructive-foreground hover:bg-destructive/90">
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
