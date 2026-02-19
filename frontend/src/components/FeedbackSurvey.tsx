import { useState, useEffect } from "react";
import { useAuth } from "@/hooks/useAuth";
import apiClient from "@/lib/apiClient";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { useToast } from "@/hooks/use-toast";
import { Loader2, Save, Send } from "lucide-react";
import { Progress } from "@/components/ui/progress";

interface FeedbackSurveyProps {
  trigger: React.ReactNode;
}

interface FeedbackData {
  id?: string;
  role_position: string;
  painful_part: string;
  what_surprised: string;
  expected_not_do: string;
  confusing_part: string;
  overall_satisfaction: number | null;
  specific_project_issue: string;
  other_comments: string;
  contact_for_followup: string;
  status: "draft" | "submitted";
}

const initialFormData: FeedbackData = {
  role_position: "",
  painful_part: "",
  what_surprised: "",
  expected_not_do: "",
  confusing_part: "",
  overall_satisfaction: null,
  specific_project_issue: "",
  other_comments: "",
  contact_for_followup: "",
  status: "draft",
};

const satisfactionLabels = [
  { value: 1, label: "Very poor" },
  { value: 2, label: "Poor" },
  { value: 3, label: "Fair" },
  { value: 4, label: "Good" },
  { value: 5, label: "Excellent" },
];

export const FeedbackSurvey = ({ trigger }: FeedbackSurveyProps) => {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [formData, setFormData] = useState<FeedbackData>(initialFormData);
  const [existingId, setExistingId] = useState<string | null>(null);
  const [hasSubmitted, setHasSubmitted] = useState(false);
  const { toast } = useToast();
  const { user } = useAuth();

  useEffect(() => {
    if (open) {
      loadExistingFeedback();
    }
  }, [open]);

  const loadExistingFeedback = async () => {
    setLoading(true);
    try {
      const data = await apiClient.getFeedbackSurvey();

      if (data?.status === "draft" && data?.id) {
        setFormData({
          role_position: data.role_position || "",
          painful_part: data.painful_part || "",
          what_surprised: data.what_surprised || "",
          expected_not_do: data.expected_not_do || "",
          confusing_part: data.confusing_part || "",
          overall_satisfaction: data.overall_satisfaction,
          specific_project_issue: data.specific_project_issue || "",
          other_comments: data.other_comments || "",
          contact_for_followup: data.contact_for_followup || "",
          status: "draft",
        });
        setExistingId(data.id);
        setHasSubmitted(false);
      } else if (data?.status === "submitted") {
        setHasSubmitted(true);
      } else {
        setFormData(initialFormData);
        setExistingId(null);
        setHasSubmitted(false);
      }
    } catch (error: any) {
      console.error("Error loading feedback:", error);
    } finally {
      setLoading(false);
    }
  };

  const calculateProgress = () => {
    const requiredFields = [
      formData.role_position,
      formData.painful_part,
      formData.what_surprised,
      formData.expected_not_do,
      formData.confusing_part,
      formData.overall_satisfaction,
    ];
    const filledCount = requiredFields.filter(
      (field) => field !== null && field !== ""
    ).length;
    return Math.round((filledCount / 6) * 100);
  };

  const validateRequired = () => {
    const errors: string[] = [];
    if (!formData.role_position.trim()) errors.push("Your role/position");
    if (!formData.painful_part.trim()) errors.push("Most painful part");
    if (!formData.what_surprised.trim()) errors.push("What surprised you");
    if (!formData.expected_not_do.trim()) errors.push("Expected but not done");
    if (!formData.confusing_part.trim()) errors.push("Confusing part");
    if (!formData.overall_satisfaction) errors.push("Overall satisfaction");
    return errors;
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      await apiClient.saveFeedbackSurvey({
        ...formData,
        status: "draft",
      });

      setOpen(false);
    } catch (error: any) {
      console.error("Error saving feedback:", error);
      toast({
        title: "Error",
        description: error.message || "Failed to save feedback.",
        variant: "destructive",
      });
    } finally {
      setSaving(false);
    }
  };

  const handleSubmit = async () => {
    const errors = validateRequired();
    if (errors.length > 0) {
      toast({
        title: "Required fields missing",
        description: `Please fill in: ${errors.join(", ")}`,
        variant: "destructive",
      });
      return;
    }

    setSubmitting(true);
    try {
      await apiClient.submitFeedbackSurvey({
        ...formData,
        status: "submitted",
      });

      setOpen(false);
      setFormData(initialFormData);
      setExistingId(null);
      setHasSubmitted(true);
    } catch (error: any) {
      console.error("Error submitting feedback:", error);
      toast({
        title: "Error",
        description: error.message || "Failed to submit feedback.",
        variant: "destructive",
      });
    } finally {
      setSubmitting(false);
    }
  };

  const progress = calculateProgress();

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Feedback Survey</DialogTitle>
          {!hasSubmitted && (
            <DialogDescription>
              This survey collects your feedback on Digestor's functionality, usability, and overall experience. Your input will directly help us improve the application and better align it with your needs. Fields marked with * are required.
            </DialogDescription>
          )}
        </DialogHeader>

        {loading ? (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="h-8 w-8 animate-spin text-primary" />
          </div>
        ) : hasSubmitted ? (
          <div className="py-8 text-center">
            <p className="text-lg font-medium text-primary">Thank you!</p>
            <p className="text-muted-foreground mt-2">
              You have already submitted your feedback. We appreciate your input!
            </p>
          </div>
        ) : (
          <div className="space-y-6 py-4">
            {/* Progress indicator */}
            <div className="space-y-2">
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">Progress</span>
                <span className="font-medium">{progress}% complete</span>
              </div>
              <Progress value={progress} className="h-2" />
            </div>

            {/* Question 1 */}
            <div className="space-y-2">
              <Label htmlFor="role_position" className="text-sm font-medium">
                1. Your role / position? *
              </Label>
              <Textarea
                id="role_position"
                placeholder="e.g., Project Manager, Director, Engineer..."
                value={formData.role_position}
                onChange={(e) =>
                  setFormData({ ...formData, role_position: e.target.value })
                }
                className="resize-none"
                rows={2}
              />
            </div>

            {/* Question 2 */}
            <div className="space-y-2">
              <Label htmlFor="painful_part" className="text-sm font-medium">
                2. What is the most painful part of using Digestor right now? *
              </Label>
              <Textarea
                id="painful_part"
                placeholder="Describe any frustrations or difficulties..."
                value={formData.painful_part}
                onChange={(e) =>
                  setFormData({ ...formData, painful_part: e.target.value })
                }
                className="resize-none"
                rows={3}
              />
            </div>

            {/* Question 3 */}
            <div className="space-y-2">
              <Label htmlFor="what_surprised" className="text-sm font-medium">
                3. What surprised you (good or bad) when using Digestor? *
              </Label>
              <Textarea
                id="what_surprised"
                placeholder="Share what you found unexpected..."
                value={formData.what_surprised}
                onChange={(e) =>
                  setFormData({ ...formData, what_surprised: e.target.value })
                }
                className="resize-none"
                rows={3}
              />
            </div>

            {/* Question 4 */}
            <div className="space-y-2">
              <Label htmlFor="expected_not_do" className="text-sm font-medium">
                4. What did you expect Digestor to do, but it does NOT do today? *
              </Label>
              <Textarea
                id="expected_not_do"
                placeholder="Features or behaviors you expected but didn't find..."
                value={formData.expected_not_do}
                onChange={(e) =>
                  setFormData({ ...formData, expected_not_do: e.target.value })
                }
                className="resize-none"
                rows={3}
              />
            </div>

            {/* Question 5 */}
            <div className="space-y-2">
              <Label htmlFor="confusing_part" className="text-sm font-medium">
                5. Did anything confuse you while using the app? If yes, what was
                confusing? *
              </Label>
              <Textarea
                id="confusing_part"
                placeholder="Describe any confusing parts or unclear features..."
                value={formData.confusing_part}
                onChange={(e) =>
                  setFormData({ ...formData, confusing_part: e.target.value })
                }
                className="resize-none"
                rows={3}
              />
            </div>

            {/* Question 6 - Rating */}
            <div className="space-y-3">
              <Label className="text-sm font-medium">
                6. Overall, how satisfied are you with the app? *
              </Label>
              <RadioGroup
                value={formData.overall_satisfaction?.toString() || ""}
                onValueChange={(value) =>
                  setFormData({
                    ...formData,
                    overall_satisfaction: parseInt(value),
                  })
                }
                className="flex flex-wrap gap-4"
              >
                {satisfactionLabels.map((item) => (
                  <div key={item.value} className="flex items-center space-x-2">
                    <RadioGroupItem
                      value={item.value.toString()}
                      id={`satisfaction-${item.value}`}
                    />
                    <Label
                      htmlFor={`satisfaction-${item.value}`}
                      className="font-normal cursor-pointer"
                    >
                      {item.value} - {item.label}
                    </Label>
                  </div>
                ))}
              </RadioGroup>
            </div>

            {/* Question 7 - Optional */}
            <div className="space-y-2">
              <Label htmlFor="specific_project_issue" className="text-sm font-medium">
                7. Any specific issue in any specific project? If so, please provide
                the project ID. (Optional)
              </Label>
              <Textarea
                id="specific_project_issue"
                placeholder="Describe the issue and include the project ID if applicable..."
                value={formData.specific_project_issue}
                onChange={(e) =>
                  setFormData({
                    ...formData,
                    specific_project_issue: e.target.value,
                  })
                }
                className="resize-none"
                rows={2}
              />
            </div>

            {/* Question 8 - Optional */}
            <div className="space-y-2">
              <Label htmlFor="other_comments" className="text-sm font-medium">
                8. Any other comments or suggestions? (Optional)
              </Label>
              <Textarea
                id="other_comments"
                placeholder="Share any additional thoughts..."
                value={formData.other_comments}
                onChange={(e) =>
                  setFormData({ ...formData, other_comments: e.target.value })
                }
                className="resize-none"
                rows={3}
              />
            </div>

            {/* Question 9 - Optional */}
            <div className="space-y-2">
              <Label htmlFor="contact_for_followup" className="text-sm font-medium">
                9. May we contact you for follow-up? (Optional)
              </Label>
              <Textarea
                id="contact_for_followup"
                placeholder="Email, phone, or preferred contact method..."
                value={formData.contact_for_followup}
                onChange={(e) =>
                  setFormData({
                    ...formData,
                    contact_for_followup: e.target.value,
                  })
                }
                className="resize-none"
                rows={2}
              />
            </div>

            {/* Action buttons */}
            <div className="flex justify-between pt-4 border-t">
              <Button
                variant="outline"
                onClick={handleSave}
                disabled={saving || submitting}
              >
                {saving ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <Save className="mr-2 h-4 w-4" />
                )}
                Save & Exit
              </Button>
              <Button onClick={handleSubmit} disabled={saving || submitting}>
                {submitting ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <Send className="mr-2 h-4 w-4" />
                )}
                Submit
              </Button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
};
