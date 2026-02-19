import { useState, useEffect } from "react";
import apiClient from "@/lib/apiClient";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { MessageSquarePlus, Send, Loader2, MoreHorizontal, Pencil, Trash2 } from "lucide-react";
import { toast } from "sonner";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
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

interface Remark {
  id: string;
  row_id: string;
  remark_text: string;
  created_by_user_id: string;
  created_by_full_name: string;
  created_at: string;
  updated_at: string | null;
  deleted_at: string | null;
}

interface RemarksColumnProps {
  projectHash: string;
  rowId: string;
  canAddRemark: boolean;
  currentUser: { id: string; fullName: string } | null;
  onRemarkAdded?: () => void;
}

export const RemarksColumn = ({
  projectHash,
  rowId,
  canAddRemark,
  currentUser,
  onRemarkAdded,
}: RemarksColumnProps) => {
  const [remarks, setRemarks] = useState<Remark[]>([]);
  const [loading, setLoading] = useState(true);
  const [newRemark, setNewRemark] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [popoverOpen, setPopoverOpen] = useState(false);
  
  // Edit state
  const [editingRemarkId, setEditingRemarkId] = useState<string | null>(null);
  const [editText, setEditText] = useState("");
  const [saving, setSaving] = useState(false);
  
  // Delete state
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [remarkToDelete, setRemarkToDelete] = useState<Remark | null>(null);
  const [deleting, setDeleting] = useState(false);

  // Fetch remarks for this row (excluding soft-deleted)
  useEffect(() => {
    const fetchRemarks = async () => {
      if (!projectHash || !rowId) return;

      try {
        const data = await apiClient.getProjectRemarks(projectHash);
        // Filter by rowId and exclude soft-deleted, sort by created_at desc
        const filtered = (data || [])
          .filter((r: Remark) => r.row_id === rowId && !r.deleted_at)
          .sort((a: Remark, b: Remark) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());
        setRemarks(filtered);
      } catch (err) {
        console.error("Error fetching remarks:", err);
      } finally {
        setLoading(false);
      }
    };

    fetchRemarks();
  }, [projectHash, rowId]);

  const handleSubmitRemark = async () => {
    if (!newRemark.trim() || !currentUser || submitting) return;
    
    setSubmitting(true);
    
    try {
      const data = await apiClient.createRemark({
        project_hash: projectHash,
        row_id: rowId,
        remark_text: newRemark.trim(),
        created_by_user_id: currentUser.id,
        created_by_full_name: currentUser.fullName,
      });

      // Add new remark to the top of the list
      setRemarks(prev => [data, ...prev]);
      setNewRemark("");
      setPopoverOpen(false);
      toast.success("Remark added successfully");
      onRemarkAdded?.();
    } catch (error: any) {
      console.error("Error adding remark:", error);
      toast.error("Failed to add remark");
    } finally {
      setSubmitting(false);
    }
  };

  const startEditing = (remark: Remark) => {
    setEditingRemarkId(remark.id);
    setEditText(remark.remark_text);
  };

  const cancelEditing = () => {
    setEditingRemarkId(null);
    setEditText("");
  };

  const handleSaveEdit = async () => {
    if (!editingRemarkId || !editText.trim() || !currentUser || saving) return;
    
    const remark = remarks.find(r => r.id === editingRemarkId);
    if (!remark) return;
    
    setSaving(true);
    
    try {
      await apiClient.updateRemark(editingRemarkId, {
        remark_text: editText.trim(),
      });

      // Update local state - preserve all fields including created_by_user_id
      setRemarks(prev => prev.map(r => {
        if (r.id === editingRemarkId) {
          return {
            id: r.id,
            remark_text: editText.trim(),
            created_by_user_id: r.created_by_user_id,
            created_by_full_name: r.created_by_full_name,
            created_at: r.created_at,
            updated_at: new Date().toISOString(),
            deleted_at: r.deleted_at,
          };
        }
        return r;
      }));
      
      setEditingRemarkId(null);
      setEditText("");
      toast.success("Remark updated");
    } catch (error: any) {
      console.error("Error updating remark:", error);
      toast.error("Failed to update remark");
    } finally {
      setSaving(false);
    }
  };

  const confirmDelete = (remark: Remark) => {
    setRemarkToDelete(remark);
    setDeleteDialogOpen(true);
  };

  const handleDeleteRemark = async () => {
    if (!remarkToDelete || !currentUser || deleting) return;
    
    setDeleting(true);
    
    try {
      await apiClient.deleteRemark(remarkToDelete.id);

      // Clear edit state if deleting the currently edited remark
      if (editingRemarkId === remarkToDelete.id) {
        setEditingRemarkId(null);
        setEditText("");
      }
      
      // Remove from local state
      setRemarks(prev => prev.filter(r => r.id !== remarkToDelete.id));
      
      setDeleteDialogOpen(false);
      setRemarkToDelete(null);
      toast.success("Remark deleted");
    } catch (error: any) {
      console.error("Error deleting remark:", error);
      toast.error("Failed to delete remark");
    } finally {
      setDeleting(false);
    }
  };

  const formatTimestamp = (timestamp: string) => {
    const date = new Date(timestamp);
    return date.toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-1">
        <Loader2 className="h-3 w-3 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="space-y-1">
      {/* Display remarks inline */}
      {remarks.length > 0 && (
        <div className="space-y-1">
          {remarks.map((remark) => {
            const isEditing = editingRemarkId === remark.id;
            // Menu visibility is ONLY based on ownership
            const showMenu = !!currentUser && remark.created_by_user_id === currentUser.id;
            
            return (
              <div
                key={remark.id}
                className="text-xs bg-muted/50 rounded p-1.5 border border-border/50"
              >
                <div className="flex items-center justify-between gap-1">
                  {/* Left: metadata - can shrink */}
                  <div className="flex items-center gap-1 text-[10px] text-muted-foreground min-w-0 flex-1 flex-wrap">
                    <span className="font-medium truncate max-w-[80px]">
                      {remark.created_by_full_name}
                    </span>
                    <span>•</span>
                    <span className="whitespace-nowrap">
                      {formatTimestamp(remark.created_at)}
                    </span>
                    {remark.updated_at && (
                      <span className="italic text-muted-foreground/70">(edited)</span>
                    )}
                  </div>
                  
                  {/* Right: actions menu - ownership-based only, always visible for author */}
                  {showMenu && (
                    <div className="shrink-0">
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-4 w-4 p-0 text-muted-foreground hover:text-foreground"
                          >
                            <MoreHorizontal className="h-3 w-3" />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end" className="w-32">
                          <DropdownMenuItem 
                            onClick={() => startEditing(remark)}
                            disabled={isEditing}
                          >
                            <Pencil className="h-3 w-3 mr-2" />
                            {isEditing ? "Editing..." : "Edit"}
                          </DropdownMenuItem>
                          <DropdownMenuItem 
                            onClick={() => confirmDelete(remark)}
                            className="text-destructive focus:text-destructive"
                          >
                            <Trash2 className="h-3 w-3 mr-2" />
                            Delete
                          </DropdownMenuItem>
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </div>
                  )}
                </div>
                
                {isEditing ? (
                  <div className="mt-1 space-y-1">
                    <Textarea
                      value={editText}
                      onChange={(e) => setEditText(e.target.value)}
                      className="min-h-[40px] text-xs resize-none"
                      autoFocus
                    />
                    <div className="flex justify-end gap-1">
                      <Button
                        variant="outline"
                        size="sm"
                        className="h-5 text-[10px] px-2"
                        onClick={cancelEditing}
                        disabled={saving}
                      >
                        Cancel
                      </Button>
                      <Button
                        size="sm"
                        className="h-5 text-[10px] px-2"
                        onClick={handleSaveEdit}
                        disabled={!editText.trim() || saving}
                      >
                        {saving ? (
                          <Loader2 className="h-2.5 w-2.5 animate-spin" />
                        ) : (
                          "Save"
                        )}
                      </Button>
                    </div>
                  </div>
                ) : (
                  <p className="text-foreground break-words leading-tight mt-0.5">
                    {remark.remark_text}
                  </p>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Add remark button with popover */}
      {canAddRemark && currentUser && (
        <Popover open={popoverOpen} onOpenChange={setPopoverOpen}>
          <PopoverTrigger asChild>
            <Button
              variant="ghost"
              size="sm"
              className="h-5 w-5 p-0 text-muted-foreground hover:text-foreground"
            >
              <MessageSquarePlus className="h-3.5 w-3.5" />
            </Button>
          </PopoverTrigger>
          <PopoverContent className="w-72 p-3" align="start">
            <div className="space-y-2">
              <Textarea
                value={newRemark}
                onChange={(e) => setNewRemark(e.target.value)}
                placeholder="Add a remark..."
                className="min-h-[60px] text-sm resize-none"
                autoFocus
              />
              <div className="flex justify-end gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    setNewRemark("");
                    setPopoverOpen(false);
                  }}
                  disabled={submitting}
                >
                  Cancel
                </Button>
                <Button
                  size="sm"
                  onClick={handleSubmitRemark}
                  disabled={!newRemark.trim() || submitting}
                >
                  {submitting ? (
                    <Loader2 className="h-3 w-3 animate-spin mr-1" />
                  ) : (
                    <Send className="h-3 w-3 mr-1" />
                  )}
                  Save
                </Button>
              </div>
            </div>
          </PopoverContent>
        </Popover>
      )}

      {/* Delete confirmation dialog */}
      <AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete this comment?</AlertDialogTitle>
            <AlertDialogDescription>
              This will permanently remove your comment from this thread.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={deleting}>Cancel</AlertDialogCancel>
            <AlertDialogAction 
              onClick={handleDeleteRemark}
              disabled={deleting}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {deleting ? (
                <Loader2 className="h-4 w-4 animate-spin mr-1" />
              ) : null}
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
};
