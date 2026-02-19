import { useEffect, useState, useRef } from 'react';
import { createPortal } from 'react-dom';
import { EditableAnswerBox, AnswerBoxData } from './EditableAnswerBox';

interface EditableAnswerBoxPortalProps {
  pageNumber: number;
  canvasWidth: number;
  canvasHeight: number;
  renderScale: number;
  answerBoxes: AnswerBoxData[];
  onAnswerBoxUpdate: (id: string, updates: Partial<AnswerBoxData>) => void;
  enabled: boolean;
}

export const EditableAnswerBoxPortal = (props: EditableAnswerBoxPortalProps) => {
  const [portalTarget, setPortalTarget] = useState<HTMLElement | null>(null);
  const isMountedRef = useRef(true);
  const portalTargetRef = useRef<HTMLElement | null>(null);
  const observerRef = useRef<MutationObserver | null>(null);

  useEffect(() => {
    isMountedRef.current = true;

    const findTarget = () => {
      if (!isMountedRef.current) return;
      
      const wrapper = document.getElementById(`canvas-wrapper-${props.pageNumber}`);
      if (wrapper && wrapper.isConnected && document.body.contains(wrapper)) {
        portalTargetRef.current = wrapper;
        setPortalTarget(wrapper);

        // Watch for the target being removed from DOM
        if (observerRef.current) {
          observerRef.current.disconnect();
        }
        
        observerRef.current = new MutationObserver((mutations) => {
          for (const mutation of mutations) {
            if (mutation.type === 'childList' && mutation.removedNodes.length > 0) {
              const wasRemoved = Array.from(mutation.removedNodes).some(
                node => node === wrapper || (node as HTMLElement).contains?.(wrapper)
              );
              if (wasRemoved && isMountedRef.current) {
                portalTargetRef.current = null;
                setPortalTarget(null);
                observerRef.current?.disconnect();
              }
            }
          }
        });

        // Observe the parent for removal of our target
        if (wrapper.parentElement) {
          observerRef.current.observe(wrapper.parentElement, {
            childList: true,
            subtree: false
          });
        }
      } else if (portalTargetRef.current && !portalTargetRef.current.isConnected) {
        portalTargetRef.current = null;
        setPortalTarget(null);
      }
    };

    findTarget();
    const retryTimer = setTimeout(findTarget, 50);

    return () => {
      isMountedRef.current = false;
      clearTimeout(retryTimer);
      observerRef.current?.disconnect();
      observerRef.current = null;
      
      // Force clear portal state immediately to prevent unmount errors
      setPortalTarget(null);
      portalTargetRef.current = null;
    };
  }, [props.pageNumber]);

  // Validate target exists and is still in the document
  const isValidTarget = portalTarget && 
                        portalTarget.isConnected && 
                        document.body.contains(portalTarget) &&
                        portalTarget === portalTargetRef.current;

  if (!isValidTarget || !isMountedRef.current) {
    return null;
  }

  return createPortal(
    <EditableAnswerBox {...props} />,
    portalTarget
  );
};
