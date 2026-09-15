import { useEffect, useRef, useState } from "react";

/** Drag-to-resize table columns, Notion-style. Each column keeps its own
 * width in a dict keyed by column id; dragging one handle only affects
 * that column. */
export function useResizableColumns(defaults: Record<string, number>, minWidth = 70) {
  const [widths, setWidths] = useState<Record<string, number>>(defaults);
  const dragKey = useRef<string | null>(null);
  const startX = useRef(0);
  const startWidth = useRef(0);

  useEffect(() => {
    function onMove(e: MouseEvent) {
      if (!dragKey.current) return;
      const dx = e.clientX - startX.current;
      const key = dragKey.current;
      setWidths((w) => ({ ...w, [key]: Math.max(minWidth, startWidth.current + dx) }));
    }
    function onUp() {
      if (!dragKey.current) return;
      dragKey.current = null;
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    }
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    return () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function startResize(e: React.MouseEvent, key: string) {
    e.preventDefault();
    e.stopPropagation();
    dragKey.current = key;
    startX.current = e.clientX;
    startWidth.current = widths[key] ?? 120;
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
  }

  return { widths, startResize };
}
