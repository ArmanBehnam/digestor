import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { ThumbsUp, ThumbsDown, Download, CheckCircle } from "lucide-react";
import { useState } from "react";
import apiClient from "@/lib/apiClient";
import { toast } from "sonner";

interface SimpleAnalysisResult {
  page: string;
  section: string;
  question: string;
  answer: string;
}

interface SimpleResultsDisplayProps {
  results: SimpleAnalysisResult[];
  projectName?: string;
  filesInfo?: Array<{ name: string; size: number }>;
  projectHash?: string;
  onSubmitSuccess?: () => void; // Callback for post-submit navigation
}

export const SimpleResultsDisplay = ({ results, projectName, filesInfo, projectHash, onSubmitSuccess }: SimpleResultsDisplayProps) => {
  const [feedback, setFeedback] = useState<{ [key: number]: 'like' | 'dislike' }>({});
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isSubmitted, setIsSubmitted] = useState(false);
  const [downloadLinks, setDownloadLinks] = useState<{ csv?: string; json?: string }>({});

  const allFeedbackProvided = results.length > 0 && results.every((_, idx) => feedback[idx]);

  const handleFeedback = (index: number, type: 'like' | 'dislike') => {
    setFeedback(prev => ({ ...prev, [index]: type }));
  };

  const handleSubmit = async () => {
    if (!allFeedbackProvided || !projectHash) return;

    setIsSubmitting(true);
    try {
      const response = await apiClient.submitProjectForApproval({
        projectHash,
        results,
        feedback: results.map((_, idx) => ({
          index: idx,
          feedback: feedback[idx],
        })),
      });

      const { csv_path, json_path } = response;

      // Get signed URLs for download
      const csvUrlData = await apiClient.getPresignedUrl(csv_path);
      const jsonUrlData = await apiClient.getPresignedUrl(json_path);

      setDownloadLinks({
        csv: csvUrlData?.signed_url,
        json: jsonUrlData?.signed_url,
      });

      setIsSubmitted(true);
      toast.success("✅ Results successfully submitted and saved.");
      
      // Navigate back to main Projects UI after successful submission
      onSubmitSuccess?.();
    } catch (error: any) {
      console.error('Submission error:', error);
      toast.error('Failed to submit results');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleDownload = (url: string | undefined, filename: string) => {
    if (!url) return;
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    link.click();
  };

  const exportToJSON = async () => {
    // Fetch remarks if we have a project hash
    let remarksByRow = new Map<string, any[]>();
    if (projectHash) {
      try {
        const data = await apiClient.getProjectRemarks(projectHash);
        // Filter active remarks and sort by created_at ascending
        const activeRemarks = (data || [])
          .filter((r: any) => !r.deleted_at)
          .sort((a: any, b: any) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime());

        activeRemarks.forEach((remark: any) => {
          if (!remarksByRow.has(remark.row_id)) {
            remarksByRow.set(remark.row_id, []);
          }
          remarksByRow.get(remark.row_id)!.push(remark);
        });
      } catch (err) {
        console.error("Error fetching remarks for export:", err);
      }
    }
    
    const resultsWithRemarks = results.map((result, index) => {
      const rowId = `${index}`;
      const rowRemarks = remarksByRow.get(rowId) || [];
      return {
        ...result,
        remarks: rowRemarks.map((r: any) => ({
          author: r.created_by_full_name,
          text: r.remark_text,
          created_at: r.created_at,
        })),
      };
    });

    const dataStr = JSON.stringify(
      {
        project_name: projectName,
        processed_at: new Date().toISOString(),
        files: filesInfo,
        results: resultsWithRemarks,
      },
      null,
      2
    );

    const dataUri = "data:application/json;charset=utf-8," + encodeURIComponent(dataStr);
    const exportName = `${projectName?.replace(/[^a-z0-9]/gi, "_") || "results"}_analysis.json`;

    const linkElement = document.createElement("a");
    linkElement.setAttribute("href", dataUri);
    linkElement.setAttribute("download", exportName);
    linkElement.click();
    console.log("JSON export completed");
  };

  if (!results || results.length === 0) {
    return null;
  }

  return (
    <Card className="p-6 bg-gradient-card border-border shadow-card">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-xl font-bold text-foreground">Extracted Results</h3>
        <div className="flex gap-2">
          {isSubmitted && downloadLinks.csv && downloadLinks.json && (
            <>
              <Button
                onClick={() => handleDownload(downloadLinks.csv, `${projectName}_results.csv`)}
                variant="secondary"
                size="sm"
              >
                <Download className="h-4 w-4 mr-2" />
                Download CSV
              </Button>
              <Button
                onClick={() => handleDownload(downloadLinks.json, `${projectName}_results.json`)}
                variant="secondary"
                size="sm"
              >
                <Download className="h-4 w-4 mr-2" />
                Download JSON
              </Button>
            </>
          )}
          {!isSubmitted && (
            <>
              <Button
                onClick={handleSubmit}
                disabled={!allFeedbackProvided || isSubmitting}
                variant="default"
                size="sm"
                className="font-semibold"
              >
                {isSubmitting ? (
                  <>Submitting...</>
                ) : (
                  <>
                    <CheckCircle className="h-4 w-4 mr-2" />
                    Submit
                  </>
                )}
              </Button>
              <Button onClick={exportToJSON} variant="secondary" size="sm">
                <Download className="h-4 w-4 mr-2" />
                Export JSON
              </Button>
            </>
          )}
        </div>
      </div>
      
      {isSubmitted && (
        <div className="mb-4 p-3 bg-green-500/10 border border-green-500/20 rounded-lg text-green-600 dark:text-green-400 flex items-center gap-2">
          <CheckCircle className="h-5 w-5" />
          <span className="font-medium">✅ Results successfully submitted and saved.</span>
        </div>
      )}

      {!allFeedbackProvided && !isSubmitted && (
        <div className="mb-4 p-3 bg-yellow-500/10 border border-yellow-500/20 rounded-lg text-yellow-600 dark:text-yellow-400">
          ⚠️ Please provide feedback (↑ or ↓) for all rows before submitting.
        </div>
      )}

      <div className="rounded-lg border border-border overflow-hidden">
        <Table>
          <TableHeader>
            <TableRow className="bg-muted/50">
              <TableHead className="text-foreground font-semibold">Page</TableHead>
              <TableHead className="text-foreground font-semibold">Section</TableHead>
              <TableHead className="text-foreground font-semibold">Question</TableHead>
              <TableHead className="text-foreground font-semibold">Answer</TableHead>
              <TableHead className="text-foreground font-semibold text-center">AI Extraction Accuracy</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {results.map((result, index) => (
              <TableRow
                key={index}
                className="border-border hover:bg-accent/5 transition-colors"
              >
                <TableCell className="font-medium text-foreground">
                  {result.page}
                </TableCell>
                <TableCell className="text-foreground">{result.section}</TableCell>
                <TableCell className="text-foreground">{result.question}</TableCell>
                <TableCell className="text-foreground">{result.answer}</TableCell>
                <TableCell className="text-center">
                  <div className="flex gap-2 justify-center">
                    <Button
                      size="sm"
                      variant={feedback[index] === 'like' ? 'default' : 'outline'}
                      onClick={() => handleFeedback(index, 'like')}
                      disabled={isSubmitted}
                      className="h-8 w-8 p-0"
                    >
                      <ThumbsUp className="h-4 w-4" />
                    </Button>
                    <Button
                      size="sm"
                      variant={feedback[index] === 'dislike' ? 'destructive' : 'outline'}
                      onClick={() => handleFeedback(index, 'dislike')}
                      disabled={isSubmitted}
                      className="h-8 w-8 p-0"
                    >
                      <ThumbsDown className="h-4 w-4" />
                    </Button>
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      {filesInfo && filesInfo.length > 0 && (
        <div className="mt-4 text-sm text-muted-foreground">
          <p className="font-medium">Processed files:</p>
          <ul className="list-disc list-inside mt-1">
            {filesInfo.map((file, idx) => (
              <li key={idx}>{file.name} ({(file.size / 1024).toFixed(2)} KB)</li>
            ))}
          </ul>
        </div>
      )}
    </Card>
  );
};
