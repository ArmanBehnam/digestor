import { useRef, useState, useCallback, RefObject } from 'react';

interface UsePannableResult {
  isPanning: boolean;
  handleMouseDown: (e: React.MouseEvent) => void;
  handleMouseMove: (e: React.MouseEvent) => void;
  handleMouseUp: () => void;
  handleMouseLeave: () => void;
}

export const usePannable = (containerRef: RefObject<HTMLDivElement | null>): UsePannableResult => {
  const [isPanning, setIsPanning] = useState(false);
  const startPos = useRef({ x: 0, y: 0, scrollLeft: 0, scrollTop: 0 });

  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    // Only pan on left click
    if (e.button !== 0) return;
    
    // Don't pan if clicking on toolbar buttons, inputs, or other interactive elements
    const target = e.target as HTMLElement;
    if (target.closest('button, input, .toolbar, [role="button"]')) return;
    
    // Check if user is trying to select text (shift key held)
    if (e.shiftKey) return;
    
    if (!containerRef.current) return;
    
    setIsPanning(true);
    startPos.current = {
      x: e.pageX,
      y: e.pageY,
      scrollLeft: containerRef.current.scrollLeft,
      scrollTop: containerRef.current.scrollTop
    };
    
    e.preventDefault(); // Prevent text selection while panning
  }, [containerRef]);

  const handleMouseMove = useCallback((e: React.MouseEvent) => {
    if (!isPanning || !containerRef.current) return;
    
    const deltaX = e.pageX - startPos.current.x;
    const deltaY = e.pageY - startPos.current.y;
    
    containerRef.current.scrollLeft = startPos.current.scrollLeft - deltaX;
    containerRef.current.scrollTop = startPos.current.scrollTop - deltaY;
  }, [isPanning, containerRef]);

  const handleMouseUp = useCallback(() => {
    setIsPanning(false);
  }, []);

  const handleMouseLeave = useCallback(() => {
    setIsPanning(false);
  }, []);

  return {
    isPanning,
    handleMouseDown,
    handleMouseMove,
    handleMouseUp,
    handleMouseLeave
  };
};
