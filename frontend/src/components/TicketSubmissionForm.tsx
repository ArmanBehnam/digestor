import { useState } from "react";
import { useAuth } from "@/hooks/useAuth";
import apiClient from "@/lib/apiClient";
import { useToast } from "@/hooks/use-toast";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Bug, Lightbulb, Sparkles, HelpCircle, Send, Loader2, Upload, X, Image } from "lucide-react";

interface TicketSubmissionFormProps {
  trigger?: React.ReactNode;
  onSuccess?: () => void;
}

type TicketType = "bug" | "feature_request" | "feature_removal" | "other";
type TicketPriority = "low" | "medium" | "high";

export const TicketSubmissionForm = ({ trigger, onSuccess }: TicketSubmissionFormProps) => {
  const [open, setOpen] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [type, setType] = useState<TicketType>("bug");
  const [priority, setPriority] = useState<TicketPriority>("medium");
  const [screenshotFile, setScreenshotFile] = useState<File | null>(null);
  const [screenshotPreview, setScreenshotPreview] = useState<string | null>(null);
  const [projectReference, setProjectReference] = useState("");
  const { toast } = useToast();
  const { user } = useAuth();

  const resetForm = () => {
    setTitle("");
    setDescription("");
    setType("bug");
    setPriority("medium");
    setScreenshotFile(null);
    setScreenshotPreview(null);
    setProjectReference("");
  };

  const handleScreenshotSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      if (!file.type.startsWith('image/')) {
        toast({
          title: "Invalid file",
          description: "Please select an image file.",
          variant: "destructive",
        });
        return;
      }
      if (file.size > 5 * 1024 * 1024) {
        toast({
          title: "File too large",
          description: "Maximum file size is 5MB.",
          variant: "destructive",
        });
        return;
      }
      setScreenshotFile(file);
      setScreenshotPreview(URL.createObjectURL(file));
    }
  };

  const removeScreenshot = () => {
    setScreenshotFile(null);
    if (screenshotPreview) {
      URL.revokeObjectURL(screenshotPreview);
      setScreenshotPreview(null);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!title.trim() || !description.trim()) {
      toast({
        title: "Validation Error",
        description: "Please fill in all required fields.",
        variant: "destructive",
      });
      return;
    }

    if (!user) {
      toast({
        title: "Authentication Required",
        description: "Please sign in to submit a ticket.",
        variant: "destructive",
      });
      return;
    }

    setIsSubmitting(true);

    try {
      await apiClient.createTicket({
        title: title.trim(),
        description: description.trim(),
        type,
        priority,
        project_reference: projectReference.trim() || undefined,
        screenshot: screenshotFile || undefined,
      });

      toast({
        title: "Ticket Submitted",
        description: "Your ticket has been submitted successfully. You'll receive a confirmation email shortly.",
      });

      resetForm();
      setOpen(false);
      onSuccess?.();
    } catch (error: any) {
      console.error("Error submitting ticket:", error);
      toast({
        title: "Submission Failed",
        description: error.message || "Failed to submit ticket. Please try again.",
        variant: "destructive",
      });
    } finally {
      setIsSubmitting(false);
    }
  };

  const getTypeIcon = (ticketType: TicketType) => {
    switch (ticketType) {
      case "bug":
        return <Bug className="h-4 w-4" />;
      case "feature_request":
        return <Lightbulb className="h-4 w-4" />;
      case "feature_removal":
        return <Sparkles className="h-4 w-4" />;
      default:
        return <HelpCircle className="h-4 w-4" />;
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        {trigger || (
          <Button variant="outline" size="sm">
            <Bug className="h-4 w-4 mr-2" />
            Report Issue
          </Button>
        )}
      </DialogTrigger>
      <DialogContent className="sm:max-w-[500px] max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Submit a Ticket</DialogTitle>
          <DialogDescription>
            Report an issue, request a new feature, or suggest a feature improvement.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4 mt-4">
          <div className="space-y-2">
            <Label htmlFor="ticket-type">Type</Label>
            <Select value={type} onValueChange={(v) => setType(v as TicketType)}>
              <SelectTrigger id="ticket-type">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="bug">
                  <div className="flex items-center gap-2">
                    <Bug className="h-4 w-4 text-destructive" />
                    Bug Report
                  </div>
                </SelectItem>
                <SelectItem value="feature_request">
                  <div className="flex items-center gap-2">
                    <Lightbulb className="h-4 w-4 text-amber-500" />
                    Feature Request
                  </div>
                </SelectItem>
                <SelectItem value="feature_removal">
                  <div className="flex items-center gap-2">
                    <Sparkles className="h-4 w-4 text-primary" />
                    Feature Improvement
                  </div>
                </SelectItem>
                <SelectItem value="other">
                  <div className="flex items-center gap-2">
                    <HelpCircle className="h-4 w-4 text-primary" />
                    Other
                  </div>
                </SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <Label htmlFor="ticket-priority">Priority</Label>
            <Select value={priority} onValueChange={(v) => setPriority(v as TicketPriority)}>
              <SelectTrigger id="ticket-priority">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="low">
                  <span className="text-accent">Low</span>
                </SelectItem>
                <SelectItem value="medium">
                  <span className="text-amber-500">Medium</span>
                </SelectItem>
                <SelectItem value="high">
                  <span className="text-destructive">High</span>
                </SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <Label htmlFor="ticket-title">Title *</Label>
            <Input
              id="ticket-title"
              placeholder="Brief summary of the issue or request"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              maxLength={200}
              required
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="ticket-description">Description *</Label>
            <Textarea
              id="ticket-description"
              placeholder="Provide details about the issue or request. Include steps to reproduce for bugs."
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={5}
              maxLength={2000}
              required
            />
            <p className="text-xs text-muted-foreground text-right">
              {description.length}/2000
            </p>
          </div>

          <div className="space-y-2">
            <Label htmlFor="ticket-project-ref">Project Name & ID (Optional)</Label>
            <Input
              id="ticket-project-ref"
              placeholder="e.g., Project Alpha - ABC123"
              value={projectReference}
              onChange={(e) => setProjectReference(e.target.value)}
              maxLength={200}
            />
            <p className="text-xs text-muted-foreground">
              Reference a specific project if this ticket relates to one
            </p>
          </div>

          <div className="space-y-2">
            <Label htmlFor="ticket-screenshot">Screenshot (Optional)</Label>
            <div className="flex items-center gap-3">
              <input
                type="file"
                id="ticket-screenshot"
                accept="image/*"
                onChange={handleScreenshotSelect}
                className="hidden"
              />
              <label
                htmlFor="ticket-screenshot"
                className="flex items-center gap-2 px-4 py-2 border border-input rounded-md cursor-pointer hover:bg-muted transition-colors text-sm"
              >
                <Upload className="h-4 w-4" />
                {screenshotFile ? "Change Screenshot" : "Attach Screenshot"}
              </label>
              {screenshotFile && (
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={removeScreenshot}
                  className="text-muted-foreground hover:text-destructive"
                >
                  <X className="h-4 w-4" />
                </Button>
              )}
            </div>
            {screenshotPreview && (
              <div className="relative mt-2 border rounded-md overflow-hidden max-w-[200px]">
                <img src={screenshotPreview} alt="Screenshot preview" className="w-full h-auto" />
              </div>
            )}
            <p className="text-xs text-muted-foreground">Max 5MB. Supported: PNG, JPG, GIF, WebP</p>
          </div>

          <div className="flex justify-end gap-3 pt-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => setOpen(false)}
              disabled={isSubmitting}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={isSubmitting}>
              {isSubmitting ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  Submitting...
                </>
              ) : (
                <>
                  <Send className="h-4 w-4 mr-2" />
                  Submit Ticket
                </>
              )}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
};
