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
import { Button } from "@/components/ui/button";
import { Save, Trash2, X, Loader2 } from "lucide-react";

interface UnsavedChangesDialogProps {
  open: boolean;
  onSaveAndContinue: () => Promise<void>;
  onDiscard: () => void;
  onCancel: () => void;
  isSaving: boolean;
}

export function UnsavedChangesDialog({
  open,
  onSaveAndContinue,
  onDiscard,
  onCancel,
  isSaving,
}: UnsavedChangesDialogProps) {
  return (
    <AlertDialog open={open} onOpenChange={(isOpen) => !isOpen && onCancel()}>
      <AlertDialogContent className="max-w-md">
        <AlertDialogHeader>
          <AlertDialogTitle className="text-xl font-semibold">
            Unsaved Review Changes
          </AlertDialogTitle>
          <AlertDialogDescription className="text-base">
            You have unsaved review changes. Would you like to save your progress before leaving?
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter className="flex flex-col gap-2 sm:flex-col">
          <Button
            variant="outline"
            onClick={onSaveAndContinue}
            disabled={isSaving}
            className="w-full justify-center"
          >
            {isSaving ? (
              <>
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                Saving...
              </>
            ) : (
              <>
                <Save className="h-4 w-4 mr-2" />
                Save & Continue Later
              </>
            )}
          </Button>
          <Button
            variant="outline"
            onClick={onDiscard}
            disabled={isSaving}
            className="w-full justify-center"
          >
            <Trash2 className="h-4 w-4 mr-2" />
            Discard Changes
          </Button>
          <Button
            variant="outline"
            onClick={onCancel}
            disabled={isSaving}
            className="w-full justify-center"
          >
            <X className="h-4 w-4 mr-2" />
            Cancel
          </Button>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
