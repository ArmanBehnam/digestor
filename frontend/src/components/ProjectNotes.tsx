import { useState, useEffect, useCallback } from "react";
import apiClient from "@/lib/apiClient";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { toast } from "sonner";
import { MessageSquare, Edit2, Trash2, Check, X } from "lucide-react";
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

interface Note {
  id: string;
  author_id: string;
  author_name: string;
  text: string;
  created_at: string;
  updated_at: string;
}

interface ProjectNotesProps {
  projectId: string;
  currentUserId: string;
  currentUserFullName: string;
  isSupervisor: boolean;
  approvalStatus?: string;
}

export function ProjectNotes({
  projectId,
  currentUserId,
  currentUserFullName,
  isSupervisor,
  approvalStatus,
}: ProjectNotesProps) {
  const [notes, setNotes] = useState<Note[]>([]);
  const [newNoteText, setNewNoteText] = useState("");
  const [loading, setLoading] = useState(false);
  const [editingNoteId, setEditingNoteId] = useState<string | null>(null);
  const [editingText, setEditingText] = useState("");
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [noteToDelete, setNoteToDelete] = useState<string | null>(null);

  const loadNotes = useCallback(async () => {
    try {
      const data = await apiClient.getProjectNotes(projectId);
      const notesArray = Array.isArray(data?.notes) ? data.notes : [];

      // Sort notes by created_at descending (newest first)
      const sortedNotes = notesArray.sort((a: Note, b: Note) => {
        const dateA = new Date(a.created_at).getTime();
        const dateB = new Date(b.created_at).getTime();
        return dateB - dateA;
      });

      setNotes(sortedNotes);
    } catch (error) {
      console.error("Error loading notes:", error);
      toast.error("Failed to load notes");
    }
  }, [projectId]);

  useEffect(() => {
    loadNotes();

    // Poll for updates every 30 seconds (replaces Supabase realtime)
    const interval = setInterval(loadNotes, 30000);
    return () => clearInterval(interval);
  }, [loadNotes]);

  const addNote = async () => {
    if (!newNoteText.trim()) {
      toast.error("Please enter a note");
      return;
    }

    setLoading(true);
    const noteTextToAdd = newNoteText.trim();
    const noteId = crypto.randomUUID();

    try {
      const newNote: Note = {
        id: noteId,
        author_id: currentUserId,
        author_name: currentUserFullName,
        text: noteTextToAdd,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      };

      // Clear input and optimistically update UI
      const previousNotes = [...notes];
      setNewNoteText("");
      setNotes([newNote, ...notes]);

      await apiClient.addProjectNote(projectId, noteTextToAdd);

      toast.success("Note added successfully");
    } catch (error) {
      console.error("Error adding note:", error);
      // Revert optimistic update
      setNewNoteText(noteTextToAdd);
      await loadNotes();
      toast.error("Failed to add note. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  const startEditing = (note: Note) => {
    setEditingNoteId(note.id);
    setEditingText(note.text);
  };

  const cancelEditing = () => {
    setEditingNoteId(null);
    setEditingText("");
  };

  const saveEdit = async (noteId: string) => {
    if (!editingText.trim()) {
      toast.error("Note cannot be empty");
      return;
    }

    setLoading(true);
    const newText = editingText.trim();

    try {
      const previousNotes = [...notes];
      const updatedNotes = notes.map((note) =>
        note.id === noteId
          ? {
              ...note,
              text: newText,
              updated_at: new Date().toISOString(),
            }
          : note
      );

      // Optimistically update UI
      setNotes(updatedNotes);
      setEditingNoteId(null);
      setEditingText("");

      await apiClient.updateProjectNote(projectId, noteId, newText);

      toast.success("Note updated successfully");
    } catch (error) {
      console.error("Error updating note:", error);
      await loadNotes();
      toast.error("Failed to update note. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  const confirmDelete = (noteId: string) => {
    setNoteToDelete(noteId);
    setDeleteDialogOpen(true);
  };

  const deleteNote = async () => {
    if (!noteToDelete) return;

    setLoading(true);
    const noteIdToDelete = noteToDelete;

    try {
      const previousNotes = [...notes];
      const updatedNotes = notes.filter((note) => note.id !== noteIdToDelete);

      // Optimistically update UI
      setNotes(updatedNotes);
      setDeleteDialogOpen(false);
      setNoteToDelete(null);

      await apiClient.deleteProjectNote(projectId, noteIdToDelete);

      toast.success("Note deleted successfully");
    } catch (error) {
      console.error("Error deleting note:", error);
      await loadNotes();
      toast.error("Failed to delete note. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  const canEdit = (note: Note) => {
    if (approvalStatus === 'APPROVED') {
      return false;
    }
    const isWaitingForApproval = approvalStatus === 'PENDING' || approvalStatus === 'CHANGES_REQUESTED';
    return note.author_id === currentUserId || isSupervisor || isWaitingForApproval;
  };

  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    return date.toLocaleString("en-US", {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  };

  return (
    <>
      <Card className="p-6 mt-6">
        <div className="flex items-center gap-2 mb-4">
          <MessageSquare className="h-5 w-5" />
          <h3 className="text-lg font-semibold">Notes</h3>
        </div>

        {/* Add New Note */}
        <div className="space-y-2 mb-6">
          <Textarea
            placeholder="Add a note or comment..."
            value={newNoteText}
            onChange={(e) => setNewNoteText(e.target.value)}
            className="min-h-[100px]"
            disabled={loading}
          />
          <Button onClick={addNote} disabled={loading || !newNoteText.trim()}>
            Add Note
          </Button>
        </div>

        {/* Notes List */}
        <div className="space-y-4">
          {notes.length === 0 ? (
            <p className="text-center text-muted-foreground py-4">
              No notes yet. Add the first note above.
            </p>
          ) : (
            notes.map((note) => (
              <Card key={note.id} className="p-4">
                <div className="flex items-start justify-between gap-2 mb-2">
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <span className="font-semibold text-sm">
                        {note.author_name}
                      </span>
                      <span className="text-xs text-muted-foreground">
                        {formatDate(note.created_at)}
                      </span>
                      {note.updated_at !== note.created_at && (
                        <span className="text-xs text-muted-foreground italic">
                          (edited)
                        </span>
                      )}
                    </div>
                  </div>
                  {canEdit(note) && editingNoteId !== note.id && (
                    <div className="flex gap-1">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => startEditing(note)}
                        disabled={loading}
                      >
                        <Edit2 className="h-4 w-4" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => confirmDelete(note.id)}
                        disabled={loading}
                      >
                        <Trash2 className="h-4 w-4 text-destructive" />
                      </Button>
                    </div>
                  )}
                </div>

                {editingNoteId === note.id ? (
                  <div className="space-y-2">
                    <Textarea
                      value={editingText}
                      onChange={(e) => setEditingText(e.target.value)}
                      className="min-h-[80px]"
                      disabled={loading}
                    />
                    <div className="flex gap-2">
                      <Button
                        size="sm"
                        onClick={() => saveEdit(note.id)}
                        disabled={loading || !editingText.trim()}
                      >
                        <Check className="h-4 w-4 mr-1" />
                        Save
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={cancelEditing}
                        disabled={loading}
                      >
                        <X className="h-4 w-4 mr-1" />
                        Cancel
                      </Button>
                    </div>
                  </div>
                ) : (
                  <p className="text-sm whitespace-pre-wrap">{note.text}</p>
                )}
              </Card>
            ))
          )}
        </div>
      </Card>

      <AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete Note</AlertDialogTitle>
            <AlertDialogDescription>
              Are you sure you want to delete this note? This action cannot be
              undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={deleteNote}>Delete</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
