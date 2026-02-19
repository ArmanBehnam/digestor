import { useCallback, useState } from "react";
import { Upload, FileText, X } from "lucide-react";
import { useToast } from "@/hooks/use-toast";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";

interface FileUploadProps {
  onFileSelect: (files: File[]) => void;
  isProcessing: boolean;
}

export const FileUpload = ({ onFileSelect, isProcessing }: FileUploadProps) => {
  const [dragActive, setDragActive] = useState(false);
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const { toast } = useToast();

  const handleDrag = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") {
      setDragActive(true);
    } else if (e.type === "dragleave") {
      setDragActive(false);
    }
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);

    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      handleFiles(Array.from(e.dataTransfer.files));
    }
  }, []);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    e.preventDefault();
    if (e.target.files && e.target.files.length > 0) {
      handleFiles(Array.from(e.target.files));
    }
  };

  const handleFiles = (files: File[]) => {
    const validTypes = [
      "application/pdf",
      "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
      "application/msword",
      "text/plain"
    ];

    const validFiles: File[] = [];
    
    for (const file of files) {
      if (!validTypes.includes(file.type)) {
        toast({
          title: "Invalid file type",
          description: `${file.name} is not a valid file type. Please upload PDF, DOCX, DOC, or TXT files.`,
          variant: "destructive",
        });
        continue;
      }

      if (file.size > 400 * 1024 * 1024) {
        toast({
          title: "File too large",
          description: `${file.name} exceeds 400MB limit.`,
          variant: "destructive",
        });
        continue;
      }

      validFiles.push(file);
    }

    if (validFiles.length > 0) {
      setSelectedFiles(validFiles);
      onFileSelect(validFiles);
    }
  };

  const removeFile = (index: number) => {
    const newFiles = selectedFiles.filter((_, i) => i !== index);
    setSelectedFiles(newFiles);
  };

  const clearAllFiles = () => {
    setSelectedFiles([]);
  };

  return (
    <Card className="bg-gradient-card border-border shadow-card transition-shadow hover:shadow-elevated">
      <div className="p-6">
        <div
          className={`relative border-2 border-dashed rounded-lg transition-all ${
            dragActive
              ? "border-primary bg-primary/5"
              : "border-border hover:border-primary/50"
          } ${isProcessing ? "opacity-50 pointer-events-none" : ""}`}
          onDragEnter={handleDrag}
          onDragLeave={handleDrag}
          onDragOver={handleDrag}
          onDrop={handleDrop}
        >
          <input
            type="file"
            id="file-upload"
            className="hidden"
            onChange={handleChange}
            accept=".pdf,.docx,.doc,.txt"
            disabled={isProcessing}
            multiple
          />
          
          {selectedFiles.length > 0 ? (
            <div className="p-6">
              <div className="flex items-center justify-between mb-4">
                <p className="text-sm font-medium text-foreground">
                  {selectedFiles.length} file{selectedFiles.length > 1 ? 's' : ''} selected
                </p>
                {!isProcessing && (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={clearAllFiles}
                    className="hover:bg-destructive/10 hover:text-destructive"
                  >
                    Clear All
                  </Button>
                )}
              </div>
              <div className="space-y-2 max-h-[300px] overflow-y-auto">
                {selectedFiles.map((file, index) => (
                  <div key={index} className="flex items-center justify-between p-3 bg-background/50 rounded-lg border border-border">
                    <div className="flex items-center gap-3 flex-1 min-w-0">
                      <FileText className="h-6 w-6 text-primary flex-shrink-0" />
                      <div className="min-w-0 flex-1">
                        <p className="font-medium text-foreground truncate">{file.name}</p>
                        <p className="text-xs text-muted-foreground">
                          {(file.size / 1024 / 1024).toFixed(2)} MB
                        </p>
                      </div>
                    </div>
                    {!isProcessing && (
                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={() => removeFile(index)}
                        className="hover:bg-destructive/10 hover:text-destructive flex-shrink-0 ml-2"
                      >
                        <X className="h-4 w-4" />
                      </Button>
                    )}
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <label
              htmlFor="file-upload"
              className="flex flex-col items-center justify-center p-12 cursor-pointer"
            >
              <Upload className="h-12 w-12 text-muted-foreground mb-4" />
              <p className="text-lg font-medium text-foreground mb-2">
                Drop your contracts here or click to browse
              </p>
              <p className="text-sm text-muted-foreground">
                Supports multiple PDF, DOCX, DOC, TXT files (max 400MB each)
              </p>
            </label>
          )}
        </div>
      </div>
    </Card>
  );
};
