import { useEffect, useState, useRef, useCallback } from 'react';
import { usePannable } from '@/hooks/usePannable';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import * as pdfjsLib from 'pdfjs-dist';
import pdfjsWorker from 'pdfjs-dist/build/pdf.worker.min.mjs?url';
import { ChevronLeft, ChevronRight, ZoomIn, ZoomOut, Loader2 } from 'lucide-react';
import { Input } from '@/components/ui/input';
import { Card } from '@/components/ui/card';

// Configure PDF.js worker using bundled worker
pdfjsLib.GlobalWorkerOptions.workerSrc = pdfjsWorker;

interface PDFViewerProps {
  fileUrl: string;
  fileName?: string;
  answerLocations?: AnswerLocation[];
  onAnswerLocationUpdate?: (locationId: string, updates: Partial<AnswerLocation>) => void;
  enableEditing?: boolean;
  preloadedPdf?: any;
  prerenderedFirstPage?: HTMLCanvasElement | null;
  focusPage?: number;
  focusQuery?: string;
}

export interface AnswerLocation {
  question: string;
  category: string;
  answer: string;
  page: number;
  reference: string;
  x?: number;
  y?: number;
  width?: number;
  height?: number;
}

export interface PDFReference {
  page: number;
  x?: number;
  y?: number;
  width?: number;
  height?: number;
}

export const PDFViewer = ({ 
  fileUrl, 
  fileName, 
  answerLocations = [],
  focusPage, 
  focusQuery 
}: PDFViewerProps) => {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pdfDoc, setPdfDoc] = useState<pdfjsLib.PDFDocumentProxy | null>(null);
  const [numPages, setNumPages] = useState(0);
  const [currentPage, setCurrentPage] = useState(focusPage || 1);
  const [scale, setScale] = useState(1.2);
  const [pageInput, setPageInput] = useState((focusPage || 1).toString());
  
  const containerRef = useRef<HTMLDivElement>(null);
  const canvasContainerRef = useRef<HTMLDivElement>(null);
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  
  // Pan functionality
  const { isPanning, handleMouseDown, handleMouseMove, handleMouseUp, handleMouseLeave } = usePannable(scrollContainerRef);

  // Log PDF URL for debugging
  useEffect(() => {
    console.log('PDFViewer rendering with URL:', fileUrl);
    console.log('File name:', fileName);
    console.log('Focus page:', focusPage);
  }, [fileUrl, fileName, focusPage]);

  // Load PDF document using pdf.js
  useEffect(() => {
    let isMounted = true;
    
    const loadPdf = async () => {
      try {
        setLoading(true);
        setError(null);
        
        console.log('Loading PDF with pdf.js from:', fileUrl);
        const loadingTask = pdfjsLib.getDocument(fileUrl);
        const pdf = await loadingTask.promise;
        
        if (isMounted) {
          console.log('PDF loaded successfully, pages:', pdf.numPages);
          setPdfDoc(pdf);
          setNumPages(pdf.numPages);
          if (focusPage && focusPage >= 1 && focusPage <= pdf.numPages) {
            setCurrentPage(focusPage);
            setPageInput(focusPage.toString());
          }
          setLoading(false);
        }
      } catch (err) {
        console.error('Error loading PDF:', err);
        if (isMounted) {
          setError('Failed to load PDF. The file may not be accessible.');
          setLoading(false);
        }
      }
    };
    
    loadPdf();
    
    return () => {
      isMounted = false;
    };
  }, [fileUrl, focusPage]);

  // Render current page
  const renderPage = useCallback(async () => {
    if (!pdfDoc || !canvasContainerRef.current) return;
    
    try {
      const page = await pdfDoc.getPage(currentPage);
      const rotation = page.rotate || 0;
      const viewport = page.getViewport({ scale, rotation });
      
      // Clear container
      canvasContainerRef.current.innerHTML = '';
      
      // Create canvas
      const canvas = document.createElement('canvas');
      const context = canvas.getContext('2d');
      if (!context) return;
      
      canvas.height = viewport.height;
      canvas.width = viewport.width;
      
      // Create wrapper
      const pageWrapper = document.createElement('div');
      pageWrapper.style.position = 'relative';
      pageWrapper.style.display = 'flex';
      pageWrapper.style.justifyContent = 'center';
      
      const canvasWrapper = document.createElement('div');
      canvasWrapper.style.position = 'relative';
      canvasWrapper.style.display = 'inline-block';
      canvasWrapper.style.boxShadow = '0 2px 8px rgba(0,0,0,0.15)';
      canvasWrapper.style.backgroundColor = 'white';
      
      canvasWrapper.appendChild(canvas);
      pageWrapper.appendChild(canvasWrapper);
      canvasContainerRef.current.appendChild(pageWrapper);
      
      // Render PDF page
      await page.render({
        canvasContext: context,
        viewport: viewport,
        intent: 'display'
      } as any).promise;
      
    } catch (err) {
      console.error(`Error rendering page ${currentPage}:`, err);
    }
  }, [pdfDoc, currentPage, scale]);

  // Re-render when page or scale changes
  useEffect(() => {
    renderPage();
  }, [renderPage]);

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
    const container = scrollContainerRef.current;
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
      <div className="w-full h-full flex items-center justify-center min-h-[600px] bg-muted/20 rounded-lg">
        <div className="text-center space-y-4">
          <Loader2 className="h-12 w-12 animate-spin text-primary mx-auto" />
          <p className="text-muted-foreground">Loading PDF...</p>
          <Button
            variant="outline"
            size="sm"
            onClick={() => window.open(fileUrl, '_blank')}
          >
            Open in New Tab
          </Button>
        </div>
      </div>
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
            Open PDF Directly
          </Button>
        </AlertDescription>
      </Alert>
    );
  }
  
  return (
    <div ref={containerRef} className="w-full h-full flex flex-col min-h-[600px]">
      {/* Toolbar */}
      <Card className="p-3 flex items-center justify-between gap-4 mb-2 flex-shrink-0">
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
              className="w-16 text-center h-8"
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
          <span className="text-sm text-muted-foreground min-w-[50px] text-center">{Math.round(scale * 100)}%</span>
          <Button variant="outline" size="sm" onClick={handleZoomIn}>
            <ZoomIn className="h-4 w-4" />
          </Button>
        </div>
        
        {fileName && (
          <div className="text-sm text-muted-foreground truncate max-w-[200px]" title={fileName}>
            {fileName}
          </div>
        )}
      </Card>
      
      {/* PDF Canvas Container - outer wrapper for rounded corner clipping */}
      <div className="flex-1 overflow-hidden rounded-lg border border-border/30">
        <div
          ref={scrollContainerRef}
          className="h-full w-full overflow-auto bg-muted/20 p-4"
          style={{ 
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
