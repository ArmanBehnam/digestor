import { useState, useEffect } from "react";
import { MessageSquare } from "lucide-react";
import apiClient from "@/lib/apiClient";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { EditNotesHistoryModal } from "./EditNotesHistoryModal";

interface EditNoteIndicatorProps {
  projectHash: string;
  rowId: string;
  questionText?: string;
}

interface NotePreview {
  note_text: string;
  edited_by_full_name: string;
  edited_at: string;
}

export function EditNoteIndicator({
  projectHash,
  rowId,
  questionText,
}: EditNoteIndicatorProps) {
  const [latestNote, setLatestNote] = useState<NotePreview | null>(null);
  const [noteCount, setNoteCount] = useState(0);
  const [showHistory, setShowHistory] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchLatestNote();
  }, [projectHash, rowId]);

  const fetchLatestNote = async () => {
    try {
      // Get latest note and count via API
      const data = await apiClient.getEditNotesPreview(projectHash, rowId);

      if (data && data.length > 0) {
        setLatestNote(data[0]);
        setNoteCount(data.length);
      } else {
        setLatestNote(null);
        setNoteCount(0);
      }
    } catch (error) {
      console.error("Error fetching note preview:", error);
      setLatestNote(null);
      setNoteCount(0);
    } finally {
      setLoading(false);
    }
  };

  // Don't render anything if no notes exist
  if (loading || !latestNote) {
    return null;
  }

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  };

  return (
    <>
      <TooltipProvider>
        <Tooltip delayDuration={200}>
          <TooltipTrigger asChild>
            <button
              type="button"
              className="inline-flex items-center text-primary/70 hover:text-primary transition-colors ml-1"
              onClick={() => setShowHistory(true)}
            >
              <MessageSquare className="h-3.5 w-3.5" />
              {noteCount > 1 && (
                <span className="text-[10px] ml-0.5 font-medium">{noteCount}</span>
              )}
            </button>
          </TooltipTrigger>
          <TooltipContent side="top" className="max-w-xs">
            <div className="space-y-1">
              <p className="text-sm">{latestNote.note_text}</p>
              <p className="text-xs text-muted-foreground">
                — {latestNote.edited_by_full_name}, {formatDate(latestNote.edited_at)}
              </p>
              {noteCount > 1 && (
                <p className="text-xs text-primary cursor-pointer">
                  View all {noteCount} notes →
                </p>
              )}
            </div>
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>

      <EditNotesHistoryModal
        open={showHistory}
        onClose={() => setShowHistory(false)}
        projectHash={projectHash}
        rowId={rowId}
        questionText={questionText}
      />
    </>
  );
}
