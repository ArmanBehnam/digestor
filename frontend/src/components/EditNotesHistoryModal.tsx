import { useState, useEffect } from "react";
import apiClient from "@/lib/apiClient";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Loader2, MessageSquare } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

interface EditNote {
  id: string;
  note_text: string;
  old_value: string | null;
  new_value: string | null;
  edited_by_full_name: string;
  edited_at: string;
  column_name: string;
}

interface EditNotesHistoryModalProps {
  open: boolean;
  onClose: () => void;
  projectHash: string;
  rowId: string;
  questionText?: string;
}

export function EditNotesHistoryModal({
  open,
  onClose,
  projectHash,
  rowId,
  questionText,
}: EditNotesHistoryModalProps) {
  const [notes, setNotes] = useState<EditNote[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (open) {
      fetchNotes();
    }
  }, [open, projectHash, rowId]);

  const fetchNotes = async () => {
    setLoading(true);
    try {
      const data = await apiClient.getEditNotes(projectHash, rowId);
      setNotes(data || []);
    } catch (error) {
      console.error("Error fetching edit notes:", error);
      setNotes([]);
    } finally {
      setLoading(false);
    }
  };

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleString(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  };

  return (
    <Dialog open={open} onOpenChange={(isOpen) => !isOpen && onClose()}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <MessageSquare className="h-5 w-5" />
            Edit Notes History
          </DialogTitle>
          {questionText && (
            <p className="text-sm text-muted-foreground mt-1">{questionText}</p>
          )}
        </DialogHeader>

        <ScrollArea className="max-h-[400px] pr-4">
          {loading ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="h-6 w-6 animate-spin text-primary" />
            </div>
          ) : notes.length === 0 ? (
            <div className="text-center py-8 text-muted-foreground">
              <MessageSquare className="h-10 w-10 mx-auto mb-2 opacity-50" />
              <p>No notes have been added for this answer.</p>
            </div>
          ) : (
            <div className="space-y-4">
              {notes.map((note) => (
                <div
                  key={note.id}
                  className="border rounded-lg p-4 space-y-2 bg-muted/30"
                >
                  <div className="flex items-start justify-between gap-2">
                    <span className="font-medium text-sm">
                      {note.edited_by_full_name}
                    </span>
                    <span className="text-xs text-muted-foreground whitespace-nowrap">
                      {formatDate(note.edited_at)}
                    </span>
                  </div>
                  
                  <div className="text-xs text-muted-foreground bg-background/50 p-2 rounded">
                    <span className="font-medium">{note.column_name}:</span>{" "}
                    <span className="text-destructive line-through">
                      {note.old_value || "—"}
                    </span>
                    {" → "}
                    <span className="text-primary font-medium">
                      {note.new_value || "—"}
                    </span>
                  </div>
                  
                  <p className="text-sm whitespace-pre-wrap">{note.note_text}</p>
                </div>
              ))}
            </div>
          )}
        </ScrollArea>

        <div className="flex justify-end pt-2">
          <Button variant="outline" onClick={onClose}>
            Close
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
