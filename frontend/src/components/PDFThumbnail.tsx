import { useState, useEffect, useRef } from "react";
import * as pdfjsLib from "pdfjs-dist";
import { Loader2 } from "lucide-react";

// Configure PDF.js worker
pdfjsLib.GlobalWorkerOptions.workerSrc = `//unpkg.com/pdfjs-dist@${pdfjsLib.version}/build/pdf.worker.min.mjs`;

interface PDFThumbnailProps {
  url: string;
  width?: number;
  height?: number;
  className?: string;
}

// Cache for rendered thumbnails
const thumbnailCache = new Map<string, string>();

export const PDFThumbnail = ({
  url,
  width = 200,
  height = 260,
  className = "",
}: PDFThumbnailProps) => {
  const [thumbnailUrl, setThumbnailUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    let isMounted = true;

    const renderThumbnail = async () => {
      // Check cache first
      if (thumbnailCache.has(url)) {
        setThumbnailUrl(thumbnailCache.get(url)!);
        setLoading(false);
        return;
      }

      try {
        setLoading(true);
        setError(false);

        const loadingTask = pdfjsLib.getDocument({
          url,
          disableAutoFetch: false,
          disableStream: true,
        });

        const pdf = await loadingTask.promise;
        const page = await pdf.getPage(1);

        // Calculate scale to fit within bounds
        const viewport = page.getViewport({ scale: 1 });
        const scaleX = width / viewport.width;
        const scaleY = height / viewport.height;
        const scale = Math.min(scaleX, scaleY) * 2; // 2x for better quality

        const scaledViewport = page.getViewport({ scale });

        // Create offscreen canvas
        const canvas = document.createElement("canvas");
        canvas.width = scaledViewport.width;
        canvas.height = scaledViewport.height;

        const context = canvas.getContext("2d");
        if (!context) throw new Error("Failed to get canvas context");

        await page.render({
          canvasContext: context,
          viewport: scaledViewport,
          canvas,
        }).promise;

        // Convert to data URL
        const dataUrl = canvas.toDataURL("image/jpeg", 0.85);

        // Cache the result
        thumbnailCache.set(url, dataUrl);

        if (isMounted) {
          setThumbnailUrl(dataUrl);
          setLoading(false);
        }

        // Cleanup
        await pdf.destroy();
      } catch (err) {
        console.error("Error rendering PDF thumbnail:", err);
        if (isMounted) {
          setError(true);
          setLoading(false);
        }
      }
    };

    renderThumbnail();

    return () => {
      isMounted = false;
    };
  }, [url, width, height]);

  if (loading) {
    return (
      <div
        className={`flex items-center justify-center bg-muted rounded-lg ${className}`}
        style={{ width, height }}
      >
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (error || !thumbnailUrl) {
    return (
      <div
        className={`flex items-center justify-center bg-muted rounded-lg text-xs text-muted-foreground ${className}`}
        style={{ width, height }}
      >
        Preview unavailable
      </div>
    );
  }

  return (
    <img
      src={thumbnailUrl}
      alt="PDF preview"
      className={`rounded-lg shadow-md object-contain bg-white ${className}`}
      style={{ maxWidth: width, maxHeight: height }}
    />
  );
};
