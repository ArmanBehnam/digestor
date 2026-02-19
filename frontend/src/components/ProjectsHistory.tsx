import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import apiClient from "@/lib/apiClient";
import { useAuth } from "@/hooks/useAuth";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Loader2, Download, Trash2, FileText, CheckCircle, FolderOpen, Eye, Search, AlertCircle } from "lucide-react";
import { toast } from "sonner";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { formatProcessedTime } from "@/lib/timeUtils";
import { exportAnswer } from "@/lib/displayUtils";
import { 
  exportProjectResultsWithRemarks,
  downloadFreshCSV,
  downloadFreshJSON
} from "@/lib/exportUtils";
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

interface ProjectRecord {
  project_hash: string;
  project_name: string;
  project_id?: string;
  files_metadata: any;
  last_processed_at: string;
  file_count: number;
  final_version?: number;
  finalized_by_full_name?: string;
  submitted_by_full_name?: string;
  submitted_at?: string;
  processing_records: any[];
  initial_accuracy?: number;
  final_accuracy?: number;
  processed_time?: number;
  saved_time?: number;
  created_at?: string;
  finalized_at?: string;
}

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
  created_at?: string;
  file_count?: number;
  files_metadata?: any;
}

interface ProjectsHistoryProps {
  onPendingProjectClick?: (projectHash: string) => void;
  isAdmin?: boolean;
  isSupervisor?: boolean;
}

export const ProjectsHistory = ({ onPendingProjectClick, isAdmin, isSupervisor }: ProjectsHistoryProps) => {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [projects, setProjects] = useState<ProjectRecord[]>([]);
  const [pendingProjects, setPendingProjects] = useState<PendingProject[]>([]);
  const [filteredPendingProjects, setFilteredPendingProjects] = useState<PendingProject[]>([]);
  const [loading, setLoading] = useState(true);
  const [pendingLoading, setPendingLoading] = useState(true);
  const [initialLoadComplete, setInitialLoadComplete] = useState(false);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [projectToDelete, setProjectToDelete] = useState<string | null>(null);
  const [pendingSearchTerm, setPendingSearchTerm] = useState("");
  const [assignedToMeOnly, setAssignedToMeOnly] = useState(true);
  const [currentUserId, setCurrentUserId] = useState<string | null>(null);
  const [projectSearchTerm, setProjectSearchTerm] = useState("");
  
  // Polling interval ref (replaces realtime subscription)

  const fetchPendingProjects = async (showLoading = true) => {
    try {
      if (showLoading) setPendingLoading(true);
      const data = await apiClient.listPendingProjects();
      setPendingProjects(data || []);
    } catch (error: any) {
      console.error("Error fetching pending projects:", error);
      if (showLoading) toast.error("Failed to load pending approvals");
    } finally {
      if (showLoading) setPendingLoading(false);
    }
  };

  const fetchProjects = async () => {
    try {
      setLoading(true);
      // Fetch finalized and approved projects via API
      const data = await apiClient.listProjects("APPROVED", 1, 200);
      const records = data?.items || data || [];

      // Group by project_hash to show unique projects
      const projectsMap = new Map<string, any>();
      records.forEach((record: any) => {
        const hash = record.project_hash;
        if (!projectsMap.has(hash)) {
          projectsMap.set(hash, {
            project_hash: hash,
            project_name: record.project_name,
            project_id: record.project_id,
            files_metadata: record.files_metadata,
            last_processed_at: record.finalized_at,
            file_count: record.files_metadata?.length || 0,
            final_version: record.final_version,
            finalized_by_full_name: record.finalized_by_full_name,
            submitted_by_full_name: record.submitted_by_full_name,
            submitted_at: record.submitted_at,
            initial_accuracy: record.initial_accuracy,
            final_accuracy: record.final_accuracy,
            processed_time: record.processed_time,
            saved_time: record.saved_time,
            created_at: record.created_at,
            finalized_at: record.finalized_at,
            processing_records: [record]
          });
        } else {
          // Add to existing project's records
          const existing = projectsMap.get(hash);
          existing.processing_records.push(record);
          // Keep the latest finalization date
          if (record.finalized_at > existing.last_processed_at) {
            existing.last_processed_at = record.finalized_at;
            existing.final_version = record.final_version;
            existing.finalized_by_full_name = record.finalized_by_full_name;
            existing.submitted_by_full_name = record.submitted_by_full_name;
            existing.submitted_at = record.submitted_at;
            existing.initial_accuracy = record.initial_accuracy;
            existing.final_accuracy = record.final_accuracy;
            existing.created_at = record.created_at;
            existing.finalized_at = record.finalized_at;
            existing.file_count = record.files_metadata ? record.files_metadata.length : 1;
          }
        }
      });

      setProjects(Array.from(projectsMap.values()) as ProjectRecord[]);
    } catch (error: any) {
      console.error("Error fetching projects:", error);
      // Silently fail - don't show error toast to user
    } finally {
      setLoading(false);
    }
  };

  // Set current user ID from auth hook
  useEffect(() => {
    setCurrentUserId(user?.id || null);
  }, [user]);

  useEffect(() => {
    // Load both data sources in parallel and mark initial load complete
    const loadInitialData = async () => {
      await Promise.all([fetchProjects(), fetchPendingProjects()]);
      setInitialLoadComplete(true);
    };
    loadInitialData();

    // Listen for project submission events to refresh the list
    const handleProjectSubmitted = () => {
      fetchProjects();
      fetchPendingProjects();
    };

    // Listen for save-to-waiting events from navigation guard modal
    const handleProjectSavedToWaiting = () => {
      console.log('[ProjectsHistory] Project saved to waiting event received');
      fetchPendingProjects(false); // Refresh without loading spinner
    };

    window.addEventListener('project-submitted', handleProjectSubmitted);
    window.addEventListener('project-saved-to-waiting', handleProjectSavedToWaiting);

    // Poll for updates every 30 seconds (replaces Supabase realtime subscription)
    const pollInterval = setInterval(() => {
      console.log('Polling update - refreshing both project lists');
      fetchPendingProjects(false);
      fetchProjects();
    }, 30000);

    return () => {
      window.removeEventListener('project-submitted', handleProjectSubmitted);
      window.removeEventListener('project-saved-to-waiting', handleProjectSavedToWaiting);
      clearInterval(pollInterval);
    };
  }, []);

  // Filter pending projects based on search and assignment
  useEffect(() => {
    let filtered = pendingProjects;

    if (pendingSearchTerm) {
      filtered = filtered.filter(
        (p) =>
          p.project_name?.toLowerCase().includes(pendingSearchTerm.toLowerCase()) ||
          p.project_id?.toLowerCase().includes(pendingSearchTerm.toLowerCase()) ||
          p.assigned_supervisor_name?.toLowerCase().includes(pendingSearchTerm.toLowerCase()) ||
          p.submitted_by_full_name?.toLowerCase().includes(pendingSearchTerm.toLowerCase())
      );
    }

    if (assignedToMeOnly && currentUserId) {
      filtered = filtered.filter((p) => p.assigned_supervisor_id === currentUserId);
    }

    setFilteredPendingProjects(filtered);
  }, [pendingProjects, pendingSearchTerm, assignedToMeOnly, currentUserId]);

  const handleDeleteProject = async () => {
    if (!projectToDelete) return;

    try {
      // Delete all records with this project_hash via API
      const result = await apiClient.deleteProjectById(projectToDelete);

      toast.success("Project deleted successfully");

      // Refresh both lists
      await Promise.all([fetchProjects(), fetchPendingProjects()]);
    } catch (error: any) {
      console.error("Error deleting project:", error);
      toast.error(error.message || "Failed to delete project");
    } finally {
      setDeleteDialogOpen(false);
      setProjectToDelete(null);
    }
  };

  const exportProjectResults = async (project: ProjectRecord) => {
    try {
      const completedRecords = project.processing_records.filter(
        (r: any) => (r.status === "complete" || r.status === "completed") && r.results
      );
      const allResults = completedRecords.flatMap((r: any) => r.results || []);

      // Use the shared export function that includes fresh remarks
      await exportProjectResultsWithRemarks(
        project.project_hash,
        project.project_name,
        project.last_processed_at,
        project.files_metadata,
        allResults
      );

      toast.success("Project results exported with remarks");
    } catch (error: any) {
      console.error("Export error:", error);
      toast.error("Failed to export project results");
    }
  };

  // Download fresh CSV with latest remarks
  const handleDownloadFreshCSV = async (project: any, displayName: string) => {
    try {
      const firstRecord = project.processing_records?.[0] || project;
      const snapshotData = firstRecord.final_table_snapshot_json || 
        (firstRecord.results ? firstRecord.results.map((r: any, idx: number) => ({
          ...r,
          row_id: r.row_id || r.id || `${idx}`,
          question_id: r.question_id || idx + 1,
        })) : []);
      
      await downloadFreshCSV(
        project.project_hash,
        snapshotData,
        `${displayName}.csv`
      );
      toast.success(`Downloaded ${displayName}.csv with latest remarks`);
    } catch (error: any) {
      console.error("CSV download error:", error);
      toast.error("Failed to download CSV");
    }
  };

  // Download fresh JSON with latest remarks
  const handleDownloadFreshJSON = async (project: any, displayName: string) => {
    try {
      const firstRecord = project.processing_records?.[0] || project;
      const snapshotData = firstRecord.final_table_snapshot_json || 
        (firstRecord.results ? firstRecord.results.map((r: any, idx: number) => ({
          ...r,
          row_id: r.row_id || r.id || `${idx}`,
          question_id: r.question_id || idx + 1,
        })) : []);
      
      await downloadFreshJSON(
        project.project_hash,
        snapshotData,
        {
          project_name: project.project_name,
          project_id: firstRecord.project_id,
          finalized_at: project.finalized_at,
          files_metadata: project.files_metadata,
        },
        `${displayName}.json`
      );
      toast.success(`Downloaded ${displayName}.json with latest remarks`);
    } catch (error: any) {
      console.error("JSON download error:", error);
      toast.error("Failed to download JSON");
    }
  };

  const downloadFile = async (filePath: string, fileName: string) => {
    try {
      const urlData = await apiClient.getPresignedUrl(filePath);

      if (urlData?.signed_url) {
        // Fetch the file as a blob to force download
        const response = await fetch(urlData.signed_url);
        const blob = await response.blob();

        // Create object URL and download
        const blobUrl = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = blobUrl;
        link.download = fileName;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);

        // Clean up the object URL
        URL.revokeObjectURL(blobUrl);

        toast.success(`Downloading ${fileName}`);
      }
    } catch (error: any) {
      console.error('Download error:', error);
      toast.error('Failed to download file');
    }
  };

  const handleOpenReview = (projectHash: string) => {
    // Use the onPendingProjectClick callback to navigate to approval review
    if (onPendingProjectClick) {
      onPendingProjectClick(projectHash);
    }
  };

  // Show loading state until initial load is complete
  if (!initialLoadComplete) {
    return (
      <Card className="p-6 bg-gradient-card border-border shadow-card">
        <div className="flex items-center justify-center">
          <Loader2 className="h-6 w-6 animate-spin text-primary" />
          <span className="ml-2 text-foreground">Loading projects...</span>
        </div>
      </Card>
    );
  }

  // Filter projects based on search term
  const filteredProjects = projects.filter((project) => {
    if (!projectSearchTerm) return true;
    
    const firstRecord = project.processing_records?.[0] || {};
    const projectId = firstRecord.project_id || project.project_hash.substring(0, 8);
    const searchLower = projectSearchTerm.toLowerCase();
    
    return (
      project.project_name.toLowerCase().includes(searchLower) ||
      projectId.toLowerCase().includes(searchLower) ||
      project.project_hash.toLowerCase().includes(searchLower)
    );
  });

  // Show empty state only after initial load is complete and both lists are empty
  if (projects.length === 0 && pendingProjects.length === 0) {
    return (
      <Card className="p-6 bg-gradient-card border-border shadow-card">
        <div className="text-center text-muted-foreground">
          <FolderOpen className="h-12 w-12 mx-auto mb-3 opacity-50" />
          <p>No previous projects found</p>
          <p className="text-sm mt-1">Process your first project to see it here</p>
        </div>
      </Card>
    );
  }

  return (
    <>
      {/* Waiting For Approval Section */}
      <Card className="p-6 bg-gradient-card border-border shadow-card mb-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold text-foreground flex items-center gap-2">
            <AlertCircle className="h-5 w-5 text-orange-500" />
            Waiting For Approval
            <Badge variant="secondary" className="ml-2">
              {filteredPendingProjects.length}
            </Badge>
          </h3>
        </div>

        {/* Search and Filter */}
        <div className="mb-4 space-y-3">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="Search by project name, ID, supervisor, or submitter..."
              value={pendingSearchTerm}
              onChange={(e) => setPendingSearchTerm(e.target.value)}
              className="pl-10"
            />
          </div>
          <div className="flex items-center space-x-2">
            <Switch
              id="assigned-to-me"
              checked={assignedToMeOnly}
              onCheckedChange={setAssignedToMeOnly}
            />
            <Label htmlFor="assigned-to-me" className="cursor-pointer text-sm">
              Assigned to Me
            </Label>
          </div>
        </div>

        {pendingLoading ? (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="h-6 w-6 animate-spin text-primary" />
            <span className="ml-2 text-muted-foreground">Loading pending approvals...</span>
          </div>
        ) : filteredPendingProjects.length === 0 ? (
          <div className="text-center py-8 text-muted-foreground">
            <AlertCircle className="h-12 w-12 mx-auto mb-3 opacity-50" />
            <p className="font-medium">No projects are waiting for approval.</p>
            {(pendingSearchTerm || assignedToMeOnly) && (
              <p className="text-sm mt-1">Try adjusting your filters</p>
            )}
          </div>
        ) : (
          <div className="space-y-3 max-h-96 overflow-y-auto">
            {filteredPendingProjects.map((project) => (
              <div
                key={project.id}
                className="p-4 border border-orange-500/20 rounded-lg bg-card hover:bg-accent/5 transition-colors"
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1 space-y-2">
                    <div className="flex items-center gap-2 flex-wrap">
                      <button
                        onClick={() => handleOpenReview(project.project_hash)}
                        className="font-semibold text-foreground hover:text-primary transition-colors"
                      >
                        {project.project_id}_{project.project_name || "Untitled Project"}
                      </button>
                      <Badge 
                        variant={project.approval_status === "PENDING" ? "secondary" : "outline"}
                        className={
                          project.approval_status === "CHANGES_REQUESTED" 
                            ? "border-orange-500 text-orange-600" 
                            : project.approval_status === "ERROR"
                            ? "border-destructive text-destructive"
                            : project.approval_status === "IN_REVIEW_SAVED"
                            ? "border-blue-500 text-blue-600 bg-blue-50 dark:bg-blue-950"
                            : ""
                        }
                      >
                        {project.approval_status === "IN_REVIEW_SAVED" ? "In Review (Saved)" : project.approval_status}
                      </Badge>
                      {project.assigned_supervisor_id === currentUserId && (
                        <Badge variant="default" className="bg-blue-600">
                          Assigned to You
                        </Badge>
                      )}
                    </div>
                    <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm text-muted-foreground">
                      <div>
                        <span className="font-medium">Supervisor:</span> {project.assigned_supervisor_name || "Unassigned"}
                      </div>
                      <div>
                        <span className="font-medium">Submitted By:</span> {project.submitted_by_full_name || "Unknown"}
                      </div>
                      <div>
                        <span className="font-medium">Submitted:</span>{" "}
                        {project.submitted_at ? new Date(project.submitted_at).toLocaleDateString() : "N/A"}
                      </div>
                      <div>
                        <span className="font-medium">Version:</span> {project.final_version || 1}
                      </div>
                      {project.initial_accuracy !== undefined && project.initial_accuracy !== null && (
                        <div>
                          <span className="font-medium">Initial Accuracy:</span>{" "}
                          <span className="text-blue-600 dark:text-blue-400 font-semibold">
                            {project.initial_accuracy.toFixed(2)}% <span className="text-xs text-muted-foreground">(initial)</span>
                          </span>
                        </div>
                      )}
                      {project.final_accuracy !== undefined && project.final_accuracy !== null && (
                        <div>
                          <span className="font-medium">Final Accuracy:</span>{" "}
                          <span className="text-green-600 dark:text-green-400 font-semibold">
                            {project.final_accuracy.toFixed(2)}% <span className="text-xs text-muted-foreground">(final)</span>
                          </span>
                        </div>
                      )}
                      {project.processed_time !== undefined && project.processed_time !== null && (
                        <div>
                          <span className="font-medium">Processing Time:</span>{" "}
                          <span className="text-blue-600 dark:text-blue-400 font-semibold">
                            {formatProcessedTime(project.processed_time)}
                          </span>
                        </div>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center gap-2 flex-shrink-0">
                    <Button
                      size="sm"
                      variant="default"
                      onClick={() => handleOpenReview(project.project_hash)}
                    >
                      <Eye className="h-4 w-4 mr-1" />
                      Open
                    </Button>
                    {(isAdmin || isSupervisor) && (
                      <Button
                        size="sm"
                        variant="destructive"
                        onClick={() => {
                          setProjectToDelete(project.project_hash);
                          setDeleteDialogOpen(true);
                        }}
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>

      {/* Approved Projects Section */}
      <Card className="p-6 bg-gradient-card border-border shadow-card">
        <h3 className="text-lg font-semibold mb-4 text-foreground flex items-center gap-2">
          <FolderOpen className="h-5 w-5" />
          Approved Projects ({filteredProjects.length})
        </h3>
        
        {/* Search Bar for Approved Projects */}
        <div className="mb-4">
          <Input
            id="projectSearch"
            type="text"
            placeholder="Search by Project Name or Project ID"
            value={projectSearchTerm}
            onChange={(e) => setProjectSearchTerm(e.target.value)}
            className="w-full"
          />
        </div>

        <div className="space-y-3 max-h-96 overflow-y-auto">
          {filteredProjects.map((project) => {
            const firstRecord = project.processing_records?.[0] || {};
            const projectId = firstRecord.project_id || project.project_hash.substring(0, 8);
            const displayName = `${projectId}_${project.project_name}`;
            const isSubmitted = firstRecord.submission_status === 'submitted';
            const csvPath = firstRecord.csv_file_path;
            const jsonPath = firstRecord.json_file_path;

            return (
              <div
                key={project.project_hash}
                className="p-4 border border-border rounded-lg bg-card hover:bg-accent/5 transition-colors"
              >
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <h4 
                        className="font-medium text-foreground hover:text-primary cursor-pointer transition-colors"
                        onClick={() => {
                          const version = project.final_version || 1;
                          navigate(`/projects/${project.project_hash}?version=${version}`);
                        }}
                      >
                        {displayName}
                      </h4>
                      {isSubmitted && (
                        <Badge variant="secondary" className="bg-green-500/10 text-green-600 dark:text-green-400 border-green-500/20">
                          <CheckCircle className="h-3 w-3 mr-1" />
                          Submitted
                        </Badge>
                      )}
                    </div>
                    <p className="text-sm text-muted-foreground mt-1">
                      {project.file_count} file{project.file_count !== 1 ? "s" : ""} •{" "}
                      Finalized {new Date(project.last_processed_at).toLocaleDateString()}
                    </p>
                    {project.submitted_by_full_name && project.submitted_at && (
                      <p className="text-xs text-muted-foreground mt-1">
                        Submitted by {project.submitted_by_full_name} on {new Date(project.submitted_at).toLocaleDateString()}
                      </p>
                    )}
                    {project.finalized_by_full_name && (
                      <p className="text-xs text-muted-foreground">
                        Finalized by {project.finalized_by_full_name}
                      </p>
                    )}
                    <div className="flex flex-wrap gap-3 mt-2 text-xs">
                      {project.initial_accuracy !== undefined && project.initial_accuracy !== null && (
                        <div className="flex items-center gap-1">
                          <span className="font-medium text-muted-foreground">Initial Accuracy:</span>
                          <span className="text-blue-600 dark:text-blue-400 font-semibold">
                            {project.initial_accuracy.toFixed(2)}% <span className="text-xs opacity-70">(initial)</span>
                          </span>
                        </div>
                      )}
                      {project.final_accuracy !== undefined && project.final_accuracy !== null && (
                        <div className="flex items-center gap-1">
                          <span className="font-medium text-muted-foreground">Final Accuracy:</span>
                          <span className="text-green-600 dark:text-green-400 font-semibold">
                            {project.final_accuracy.toFixed(2)}% <span className="text-xs opacity-70">(final)</span>
                          </span>
                        </div>
                      )}
                      {project.processed_time !== undefined && project.processed_time !== null && (
                        <div className="flex items-center gap-1">
                          <span className="font-medium text-muted-foreground">Processing Time:</span>
                          <span className="font-semibold">
                            {formatProcessedTime(project.processed_time)}
                          </span>
                        </div>
                      )}
                    </div>
                  {project.files_metadata && (
                    <div className="mt-2 flex flex-wrap gap-1">
                      {project.files_metadata.map((file: any, idx: number) => (
                        <span
                          key={idx}
                          className="inline-flex items-center gap-1 text-xs bg-secondary/50 px-2 py-1 rounded"
                        >
                          <FileText className="h-3 w-3" />
                          {file.name}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
                <div className="flex gap-2 ml-4 flex-wrap">
                  {/* Always use fresh export functions to include latest remarks */}
                  <Button
                    size="sm"
                    variant="secondary"
                    className="bg-green-600 hover:bg-green-700 text-white"
                    onClick={() => handleDownloadFreshCSV(project, displayName)}
                  >
                    <Download className="h-4 w-4 mr-1" />
                    CSV
                  </Button>
                  <Button
                    size="sm"
                    variant="secondary"
                    className="bg-blue-600 hover:bg-blue-700 text-white"
                    onClick={() => handleDownloadFreshJSON(project, displayName)}
                  >
                    <Download className="h-4 w-4 mr-1" />
                    JSON
                  </Button>
                  <Button
                    size="sm"
                    variant="destructive"
                    onClick={() => {
                      setProjectToDelete(project.project_hash);
                      setDeleteDialogOpen(true);
                    }}
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              </div>
            </div>
          );
        })}
        </div>
      </Card>

      <AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete Project</AlertDialogTitle>
            <AlertDialogDescription>
              Are you sure you want to delete this project? This action cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={handleDeleteProject}>Delete</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
};
