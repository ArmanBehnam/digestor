import { useEffect, useState, useRef, useCallback } from 'react';
import { usePannable } from '@/hooks/usePannable';
import * as pdfjsLib from 'pdfjs-dist';
import pdfjsWorker from 'pdfjs-dist/build/pdf.worker.min.mjs?url';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { ChevronLeft, ChevronRight, ZoomIn, ZoomOut, Loader2 } from 'lucide-react';
import { Input } from '@/components/ui/input';

// Configure PDF.js worker using bundled worker
pdfjsLib.GlobalWorkerOptions.workerSrc = pdfjsWorker;

export interface PDFHighlight {
  page: number;
  x: number;
  y: number;
  width: number;
  height: number;
  fileName?: string;
}

interface PDFViewerWithAnnotationsProps {
  fileUrl: string;
  fileName?: string;
  highlights?: PDFHighlight[];
  onReady?: () => void;
}

interface RenderedPage {
  pageNumber: number;
  canvas: HTMLCanvasElement;
  scale: number;
}

export const PDFViewerWithAnnotations = ({
  fileUrl,
  fileName,
  highlights = [],
  onReady
}: PDFViewerWithAnnotationsProps) => {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pdfDoc, setPdfDoc] = useState<pdfjsLib.PDFDocumentProxy | null>(null);
  const [numPages, setNumPages] = useState(0);
  const [currentPage, setCurrentPage] = useState(1);
  const [scale, setScale] = useState(1.5);
  const [pageInput, setPageInput] = useState('1');
  
  const containerRef = useRef<HTMLDivElement>(null);
  const canvasContainerRef = useRef<HTMLDivElement>(null);
  const renderedPagesRef = useRef<Map<number, RenderedPage>>(new Map());
  const highlightRequestRef = useRef<PDFHighlight | null>(null);
  const fitScaleRequestRef = useRef<boolean>(false);
  
  // Pan functionality
  const { isPanning, handleMouseDown, handleMouseMove, handleMouseUp, handleMouseLeave } = usePannable(containerRef);

  // Load PDF document
  useEffect(() => {
    let isMounted = true;
    
    const loadPdf = async () => {
      try {
        setLoading(true);
        setError(null);
        
        const loadingTask = pdfjsLib.getDocument(fileUrl);
        const pdf = await loadingTask.promise;
        
        if (isMounted) {
          setPdfDoc(pdf);
          setNumPages(pdf.numPages);
          setLoading(false);
          onReady?.();
          
          // Emit ready event for navigation coordination
          window.dispatchEvent(new CustomEvent('pdf-viewer-ready'));
        }
      } catch (err) {
        console.error('Error loading PDF:', err);
        if (isMounted) {
          setError('Failed to load PDF');
          setLoading(false);
        }
      }
    };
    
    loadPdf();
    
    return () => {
      isMounted = false;
    };
  }, [fileUrl, onReady]);

  // Render a specific page
  const renderPage = useCallback(async (pageNum: number, targetScale: number) => {
    if (!pdfDoc || !canvasContainerRef.current) return;
    
    try {
      const page = await pdfDoc.getPage(pageNum);
      
      // Get page rotation (0, 90, 180, 270)
      const rotation = page.rotate || 0;
      
      // Get viewport with target scale and rotation
      const viewport = page.getViewport({ scale: targetScale, rotation });
      
      // Create canvas for PDF content
      const canvas = document.createElement('canvas');
      const context = canvas.getContext('2d');
      if (!context) return;
      
      canvas.height = viewport.height;
      canvas.width = viewport.width;
      canvas.id = `pdf-page-${pageNum}`;
      
      // Render PDF page
      await page.render({
        canvasContext: context,
        viewport: viewport,
        intent: 'display'
      } as any).promise;
      
      // Store rendered page
      renderedPagesRef.current.set(pageNum, {
        pageNumber: pageNum,
        canvas,
        scale: targetScale
      });
      
      return { canvas, viewport };
    } catch (err) {
      console.error(`Error rendering page ${pageNum}:`, err);
      return null;
    }
  }, [pdfDoc]);

  // Calculate fit-to-width scale
  const calculateFitScale = useCallback(async (pageNum: number): Promise<number> => {
    if (!pdfDoc || !containerRef.current) return 1.0;
    
    try {
      const page = await pdfDoc.getPage(pageNum);
      const viewport = page.getViewport({ scale: 1.0 }); // Get intrinsic size
      const containerWidth = containerRef.current.clientWidth - 48; // Account for padding
      
      // Calculate fit-to-width scale, cap at 1.5 max
      return Math.min(containerWidth / viewport.width, 1.5);
    } catch (err) {
      console.error('Error calculating fit scale:', err);
      return 1.0;
    }
  }, [pdfDoc]);

  // Display current page
  useEffect(() => {
    if (!pdfDoc || !canvasContainerRef.current) return;
    
    const displayPage = async () => {
      // Check if we need to apply fit scale
      let targetScale = scale;
      if (fitScaleRequestRef.current) {
        targetScale = await calculateFitScale(currentPage);
        setScale(targetScale);
        fitScaleRequestRef.current = false;
      }
      
      // Clear container
      canvasContainerRef.current!.innerHTML = '';
      
      // Render page
      const result = await renderPage(currentPage, targetScale);
      if (!result) return;
      
      const { canvas, viewport } = result;
      
      // Create wrapper for page
      const pageWrapper = document.createElement('div');
      pageWrapper.id = `page-${currentPage}`;
      pageWrapper.style.position = 'relative';
      pageWrapper.style.marginBottom = '20px';
      pageWrapper.style.display = 'flex';
      pageWrapper.style.justifyContent = 'center';
      pageWrapper.style.alignItems = 'flex-start';
      
      // Create inner wrapper for canvas and overlay
      const canvasWrapper = document.createElement('div');
      canvasWrapper.style.position = 'relative';
      canvasWrapper.style.display = 'inline-block';
      canvasWrapper.style.width = `${viewport.width}px`;
      canvasWrapper.style.height = `${viewport.height}px`;
      
      // Add canvas
      canvasWrapper.appendChild(canvas);
      
      // Create overlay canvas for highlights
      const overlayCanvas = document.createElement('canvas');
      overlayCanvas.width = viewport.width;
      overlayCanvas.height = viewport.height;
      overlayCanvas.style.position = 'absolute';
      overlayCanvas.style.top = '0';
      overlayCanvas.style.left = '0';
      overlayCanvas.style.pointerEvents = 'none';
      overlayCanvas.id = `overlay-${currentPage}`;
      
      canvasWrapper.appendChild(overlayCanvas);
      pageWrapper.appendChild(canvasWrapper);
      canvasContainerRef.current!.appendChild(pageWrapper);
      
      // Draw highlights for this page
      drawHighlightsOnPage(currentPage, overlayCanvas, viewport);
      
      // Check if there's a pending highlight request - scroll to top to show full page
      if (highlightRequestRef.current?.page === currentPage) {
        highlightRequestRef.current = null;
        // Scroll to top to show full page
        containerRef.current?.scrollTo({ top: 0, behavior: 'smooth' });
      }
    };
    
    displayPage();
  }, [pdfDoc, currentPage, scale, renderPage, calculateFitScale]);

  // Draw highlights on a page
  const drawHighlightsOnPage = (pageNum: number, canvas: HTMLCanvasElement, viewport: any) => {
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    
    // Clear previous highlights
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    
    // Filter highlights for this page
    const pageHighlights = highlights.filter(h => h.page === pageNum);
    
    pageHighlights.forEach(highlight => {
      // Convert normalized coordinates to pixel coordinates
      const x = highlight.x * viewport.width;
      const y = highlight.y * viewport.height;
      const width = highlight.width * viewport.width;
      const height = highlight.height * viewport.height;
      
      // Draw green rectangle
      ctx.strokeStyle = '#22c55e';
      ctx.lineWidth = 3;
      ctx.strokeRect(x, y, width, height);
      
      // Add semi-transparent fill
      ctx.fillStyle = 'rgba(34, 197, 94, 0.1)';
      ctx.fillRect(x, y, width, height);
      
      // Add glow effect
      ctx.shadowColor = '#22c55e';
      ctx.shadowBlur = 10;
      ctx.strokeRect(x, y, width, height);
      ctx.shadowBlur = 0;
    });
  };

  // Scroll to highlight
  const scrollToHighlight = (highlight: PDFHighlight, viewport: any) => {
    if (!containerRef.current) return;
    
    const x = highlight.x * viewport.width;
    const y = highlight.y * viewport.height;
    const height = highlight.height * viewport.height;
    
    // Calculate scroll position to center the highlight
    const container = containerRef.current;
    const scrollTop = y - container.clientHeight / 2 + height / 2;
    
    container.scrollTo({
      top: Math.max(0, scrollTop),
      behavior: 'smooth'
    });
  };

  // Jump to location (called from external code)
  const jumpToLocation = useCallback(async (location: PDFHighlight) => {
    // Set flag to apply fit scale on next render
    fitScaleRequestRef.current = true;
    highlightRequestRef.current = location;
    
    if (location.page !== currentPage) {
      // Change page - displayPage effect will handle the rest
      setCurrentPage(location.page);
      setPageInput(location.page.toString());
    } else {
      // Already on the page, recalculate fit scale and re-render
      const fitScale = await calculateFitScale(location.page);
      setScale(fitScale);
      // Scroll to top after scale change
      setTimeout(() => {
        containerRef.current?.scrollTo({ top: 0, behavior: 'smooth' });
      }, 100);
    }
  }, [currentPage, calculateFitScale]);

  // Expose jumpToLocation to window for external access
  useEffect(() => {
    (window as any).jumpToPdfLocation = jumpToLocation;
    return () => {
      delete (window as any).jumpToPdfLocation;
    };
  }, [jumpToLocation]);

  // Redraw highlights when they change
  useEffect(() => {
    const overlayCanvas = document.getElementById(`overlay-${currentPage}`) as HTMLCanvasElement;
    if (overlayCanvas && pdfDoc) {
      pdfDoc.getPage(currentPage).then(page => {
        const viewport = page.getViewport({ scale });
        drawHighlightsOnPage(currentPage, overlayCanvas, viewport);
      });
    }
  }, [highlights, currentPage, pdfDoc, scale]);

  const handlePrevPage = () => {
    if (currentPage > 1) {
      const newPage = currentPage - 1;
      setCurrentPage(newPage);
      setPageInput(newPage.toString());
    }
  };

  const handleNextPage = () => {
    if (currentPage < numPages) {
      const newPage = currentPage + 1;
      setCurrentPage(newPage);
      setPageInput(newPage.toString());
    }
  };

  const handleZoomIn = () => {
    setScale(prev => Math.min(prev + 0.25, 3));
  };

  const handleZoomOut = () => {
    setScale(prev => Math.max(prev - 0.25, 0.5));
  };

  // Ctrl + Mouse Wheel zoom handler
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const handleWheel = (e: WheelEvent) => {
      if (e.ctrlKey) {
        e.preventDefault();
        e.stopPropagation();
        
        // Zoom step of ~10% per wheel tick
        const zoomStep = 0.1;
        const delta = e.deltaY > 0 ? -zoomStep : zoomStep;
        
        setScale(prev => {
          const newScale = prev + delta;
          return Math.min(Math.max(newScale, 0.5), 3);
        });
      }
    };

    container.addEventListener('wheel', handleWheel, { passive: false });
    
    return () => {
      container.removeEventListener('wheel', handleWheel);
    };
  }, []);

  const handlePageInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setPageInput(e.target.value);
  };

  const handlePageInputSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const pageNum = parseInt(pageInput);
    if (pageNum >= 1 && pageNum <= numPages) {
      setCurrentPage(pageNum);
    } else {
      setPageInput(currentPage.toString());
    }
  };

  if (loading) {
    return (
      <Card className="w-full h-full flex items-center justify-center min-h-[600px]">
        <div className="text-center space-y-4">
          <Loader2 className="h-12 w-12 animate-spin text-primary mx-auto" />
          <p className="text-muted-foreground">Loading PDF...</p>
        </div>
      </Card>
    );
  }

  if (error) {
    return (
      <Alert variant="destructive" className="m-4">
        <AlertDescription>
          {error}
          <br />
          <Button
            variant="outline"
            size="sm"
            className="mt-2"
            onClick={() => window.open(fileUrl, '_blank')}
          >
            Open PDF in New Tab
          </Button>
        </AlertDescription>
      </Alert>
    );
  }

  return (
    <div className="w-full h-full flex flex-col">
      {/* Toolbar */}
      <Card className="p-3 flex items-center justify-between gap-4 mb-4">
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={handlePrevPage}
            disabled={currentPage <= 1}
          >
            <ChevronLeft className="h-4 w-4" />
          </Button>
          
          <form onSubmit={handlePageInputSubmit} className="flex items-center gap-2">
            <Input
              type="text"
              value={pageInput}
              onChange={handlePageInputChange}
              className="w-16 text-center"
              size={1}
            />
            <span className="text-sm text-muted-foreground">of {numPages}</span>
          </form>
          
          <Button
            variant="outline"
            size="sm"
            onClick={handleNextPage}
            disabled={currentPage >= numPages}
          >
            <ChevronRight className="h-4 w-4" />
          </Button>
        </div>
        
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={handleZoomOut}>
            <ZoomOut className="h-4 w-4" />
          </Button>
          <span className="text-sm text-muted-foreground">{Math.round(scale * 100)}%</span>
          <Button variant="outline" size="sm" onClick={handleZoomIn}>
            <ZoomIn className="h-4 w-4" />
          </Button>
        </div>
        
        {fileName && (
          <div className="text-sm text-muted-foreground truncate max-w-xs">
            {fileName}
          </div>
        )}
      </Card>
      
      {/* PDF Canvas Container - outer wrapper for rounded corner clipping */}
      <div className="flex-1 overflow-hidden rounded-lg border border-border/30">
        <div
          ref={containerRef}
          className="h-full w-full overflow-auto bg-muted/20 p-4"
          style={{ 
            minHeight: '600px',
            cursor: isPanning ? 'grabbing' : 'grab',
            userSelect: isPanning ? 'none' : 'auto'
          }}
          onMouseDown={handleMouseDown}
          onMouseMove={handleMouseMove}
          onMouseUp={handleMouseUp}
          onMouseLeave={handleMouseLeave}
        >
          <div
            ref={canvasContainerRef}
            style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', minWidth: 'min-content' }}
          />
        </div>
      </div>
    </div>
  );
};
