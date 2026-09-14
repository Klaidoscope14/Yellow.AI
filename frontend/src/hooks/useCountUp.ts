import { useEffect, useState } from "react";

const EASE = (t: number) => 1 - Math.pow(1 - t, 3);

/** Animates a number from 0 to `target` once on mount — a small, quiet
 * delight for KPI tiles, not a data visualization. */
export function useCountUp(target: number, durationMs = 500): number {
  const [value, setValue] = useState(0);

  useEffect(() => {
    if (target === 0) {
      setValue(0);
      return;
    }
    let raf: number;
    const start = performance.now();
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / durationMs);
      setValue(Math.round(target * EASE(t)));
      if (t < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [target]);

  return value;
}
