import { FileText, MoreVertical, ExternalLink } from "lucide-react";
import { cn } from "@/lib/utils";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { PdfPopoutButton } from "./PdfPopoutButton";

interface PDFSource {
  name: string;
  url: string;
  pageCount?: number;
  size?: number;
}

interface PDFSourceCarouselProps {
  sources: PDFSource[];
  selectedIndex: number;
  onSelect: (index: number) => void;
  className?: string;
  // Pop-out support
  projectId?: string;
  filesMetadata?: Array<{ name: string; path: string; size?: number; type?: string }>;
  onPopoutStateChange?: (isActive: boolean) => void;
  hidePopout?: boolean;
}

export const PDFSourceCarousel = ({
  sources,
  selectedIndex,
  onSelect,
  className,
  projectId,
  filesMetadata,
  onPopoutStateChange,
  hidePopout = false,
}: PDFSourceCarouselProps) => {
  const handleOpenInNewWindow = (url: string, e: React.MouseEvent) => {
    e.stopPropagation();
    window.open(url, '_blank');
  };

  const showPopoutButton = !hidePopout && projectId && filesMetadata && filesMetadata.length > 0;

  return (
    <div className={cn("flex items-center gap-2 mb-3", className)}>
      {/* PDF Tabs */}
      <div className="flex flex-wrap gap-2 flex-1">
        {sources.map((source, index) => {
          const isSelected = selectedIndex === index;
          
          return (
            <div
              key={index}
              className={cn(
                "flex items-center rounded-lg border transition-colors",
                isSelected
                  ? "border-primary bg-primary/10"
                  : "border-border bg-card hover:border-primary/50 hover:bg-primary/5"
              )}
            >
              <button
                onClick={() => onSelect(index)}
                className={cn(
                  "flex items-center gap-2 px-3 py-2",
                  "text-sm font-medium",
                  isSelected ? "text-primary" : "text-foreground"
                )}
                title={source.name}
              >
                <FileText className="h-4 w-4 flex-shrink-0" />
                <span className="truncate max-w-[150px]">{source.name}</span>
              </button>
              
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <button
                    onClick={(e) => e.stopPropagation()}
                    className={cn(
                      "p-2 rounded-r-lg hover:bg-muted/50 transition-colors",
                      isSelected ? "text-primary" : "text-muted-foreground"
                    )}
                    title="More options"
                  >
                    <MoreVertical className="h-4 w-4" />
                  </button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" className="bg-popover z-50">
                  <DropdownMenuItem 
                    onClick={(e) => handleOpenInNewWindow(source.url, e)}
                    className="cursor-pointer"
                  >
                    <ExternalLink className="h-4 w-4 mr-2" />
                    Open in new window
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </div>
          );
        })}
      </div>

      {/* Pop-out Button */}
      {showPopoutButton && (
        <PdfPopoutButton
          projectId={projectId}
          filesMetadata={filesMetadata}
          selectedIndex={selectedIndex}
          onPopoutStateChange={onPopoutStateChange}
        />
      )}
    </div>
  );
};
