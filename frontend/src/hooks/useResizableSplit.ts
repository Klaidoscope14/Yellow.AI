import { useCallback, useEffect, useRef, useState } from "react";

const STORAGE_KEY = "nexus-split-left-width";
const MIN_PANE = 340;

/** Draggable divider between two panes. Width is persisted per-browser so a
 * reload keeps the operator's chosen layout. */
export function useResizableSplit() {
  const containerRef = useRef<HTMLDivElement>(null);
  const [leftWidth, setLeftWidth] = useState<number | null>(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      return saved ? Number(saved) : null;
    } catch {
      return null;
    }
  });
  const dragging = useRef(false);

  useEffect(() => {
    function onMove(e: MouseEvent) {
      if (!dragging.current || !containerRef.current) return;
      const rect = containerRef.current.getBoundingClientRect();
      const w = Math.max(MIN_PANE, Math.min(e.clientX - rect.left, rect.width - MIN_PANE));
      setLeftWidth(w);
    }
    function onUp() {
      if (!dragging.current) return;
      dragging.current = false;
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
      setLeftWidth((w) => {
        if (w != null) {
          try {
            localStorage.setItem(STORAGE_KEY, String(w));
          } catch {
            /* ignore */
          }
        }
        return w;
      });
    }
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    return () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
  }, []);

  const startDrag = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    dragging.current = true;
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
  }, []);

  const resetSplit = useCallback(() => {
    setLeftWidth(null);
    try {
      localStorage.removeItem(STORAGE_KEY);
    } catch {
      /* ignore */
    }
  }, []);

  return { containerRef, leftWidth, startDrag, resetSplit };
}
