import { useEffect, useRef, useState } from 'react';
import { Canvas as FabricCanvas, Rect, Text as FabricText, FabricObject } from 'fabric';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { toast } from 'sonner';

export interface AnswerBoxData {
  id: string;
  page: number;
  question: string;
  category: string;
  answer: string;
  x: number;
  y: number;
  width: number;
  height: number;
}

interface EditableAnswerBoxProps {
  pageNumber: number;
  canvasWidth: number;
  canvasHeight: number;
  renderScale: number;
  answerBoxes: AnswerBoxData[];
  onAnswerBoxUpdate: (id: string, updates: Partial<AnswerBoxData>) => void;
  enabled: boolean;
}

export const EditableAnswerBox = ({
  pageNumber,
  canvasWidth,
  canvasHeight,
  renderScale,
  answerBoxes,
  onAnswerBoxUpdate,
  enabled,
}: EditableAnswerBoxProps) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const fabricCanvasRef = useRef<FabricCanvas | null>(null);
  const [selectedBox, setSelectedBox] = useState<AnswerBoxData | null>(null);
  const [editDialogOpen, setEditDialogOpen] = useState(false);
  const [editedAnswer, setEditedAnswer] = useState('');

  // Initialize Fabric canvas
  useEffect(() => {
    if (!canvasRef.current || fabricCanvasRef.current) return;

    const canvas = new FabricCanvas(canvasRef.current, {
      width: canvasWidth,
      height: canvasHeight,
      selection: enabled,
      backgroundColor: 'transparent',
    });

    canvas.isDrawingMode = false;

    fabricCanvasRef.current = canvas;

    // Handle object modification
    canvas.on('object:modified', (e) => {
      const obj = e.target as FabricObject;
      if (!obj) return;

      const boxData = (obj as any).answerBoxData as AnswerBoxData;
      if (!boxData) return;

      // Convert canvas coordinates back to PDF coordinates
      const pdfX = (obj.left || 0) / renderScale;
      const pdfY = (canvasHeight - (obj.top || 0) - (obj.height || 0) * (obj.scaleY || 1)) / renderScale;
      const pdfWidth = ((obj.width || 0) * (obj.scaleX || 1)) / renderScale;
      const pdfHeight = ((obj.height || 0) * (obj.scaleY || 1)) / renderScale;

      onAnswerBoxUpdate(boxData.id, {
        x: pdfX,
        y: pdfY,
        width: pdfWidth,
        height: pdfHeight,
      });

      toast.success('Bounding box position updated');
    });

    // Handle double-click to edit text
    canvas.on('mouse:dblclick', (e) => {
      const obj = e.target as FabricObject;
      if (!obj) return;

      const boxData = (obj as any).answerBoxData as AnswerBoxData;
      if (!boxData) return;

      setSelectedBox(boxData);
      setEditedAnswer(boxData.answer);
      setEditDialogOpen(true);
    });

    return () => {
      canvas.dispose();
      fabricCanvasRef.current = null;
    };
  }, [canvasWidth, canvasHeight]);

  // Update canvas dimensions
  useEffect(() => {
    if (!fabricCanvasRef.current) return;
    
    fabricCanvasRef.current.setDimensions({
      width: canvasWidth,
      height: canvasHeight,
    });
  }, [canvasWidth, canvasHeight]);

  // Update selection mode
  useEffect(() => {
    if (!fabricCanvasRef.current) return;
    
    fabricCanvasRef.current.selection = enabled;
    fabricCanvasRef.current.forEachObject((obj) => {
      obj.selectable = enabled;
      obj.evented = enabled;
    });
    fabricCanvasRef.current.requestRenderAll();
  }, [enabled]);

  // Render answer boxes for this page
  useEffect(() => {
    if (!fabricCanvasRef.current) return;

    const canvas = fabricCanvasRef.current;
    canvas.clear();

    const pageBoxes = answerBoxes.filter(box => box.page === pageNumber);

    pageBoxes.forEach((boxData) => {
      // Convert PDF coordinates to canvas display coordinates
      // The canvasWidth/Height are now the displayed dimensions
      // renderScale is already applied in PDF rendering, so we just scale to display size
      const canvasX = boxData.x * renderScale * (canvasWidth / (canvasWidth));
      const canvasY = canvasHeight - ((boxData.y + boxData.height) * renderScale);
      const boxCanvasWidth = boxData.width * renderScale;
      const boxCanvasHeight = boxData.height * renderScale;

      // Create rectangle
      const rect = new Rect({
        left: canvasX,
        top: canvasY,
        width: boxCanvasWidth,
        height: boxCanvasHeight,
        fill: 'rgba(255, 255, 0, 0.25)',
        stroke: 'rgba(255, 210, 0, 0.95)',
        strokeWidth: 2,
        selectable: enabled,
        evented: enabled,
        hasControls: true,
        hasBorders: true,
        lockRotation: true,
      });

      // Attach data to the object
      (rect as any).answerBoxData = boxData;

      // Add tooltip
      rect.set('hoverCursor', enabled ? 'move' : 'default');

      canvas.add(rect);

      // Add label text above the box
      const label = new FabricText(boxData.question.substring(0, 30), {
        left: canvasX,
        top: canvasY - 20,
        fontSize: 12,
        fill: '#333',
        backgroundColor: 'rgba(255, 255, 255, 0.9)',
        selectable: false,
        evented: false,
      });

      canvas.add(label);
    });

    canvas.requestRenderAll();
  }, [answerBoxes, pageNumber, canvasWidth, canvasHeight, renderScale, enabled]);

  const handleSaveEdit = () => {
    if (!selectedBox) return;

    onAnswerBoxUpdate(selectedBox.id, {
      answer: editedAnswer,
    });

    toast.success('Answer text updated');
    setEditDialogOpen(false);
    setSelectedBox(null);
  };

  return (
    <>
      <canvas
        ref={canvasRef}
        style={{
          position: 'absolute',
          top: 0,
          left: 0,
          pointerEvents: enabled ? 'auto' : 'none',
          zIndex: 20,
        }}
      />

      <Dialog open={editDialogOpen} onOpenChange={setEditDialogOpen}>
        <DialogContent aria-describedby="edit-answer-description">
          <DialogHeader>
            <DialogTitle>Edit Answer</DialogTitle>
          </DialogHeader>
          <p id="edit-answer-description" className="sr-only">
            Edit the answer text for the selected bounding box
          </p>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label>Question</Label>
              <p className="text-sm text-muted-foreground">{selectedBox?.question}</p>
            </div>
            <div className="space-y-2">
              <Label>Category</Label>
              <p className="text-sm text-muted-foreground">{selectedBox?.category}</p>
            </div>
            <div className="space-y-2">
              <Label htmlFor="answer">Answer Text</Label>
              <Textarea
                id="answer"
                value={editedAnswer}
                onChange={(e) => setEditedAnswer(e.target.value)}
                rows={4}
                placeholder="Enter answer text..."
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditDialogOpen(false)}>
              Cancel
            </Button>
            <Button onClick={handleSaveEdit}>
              Save Changes
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
};
