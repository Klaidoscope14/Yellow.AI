import { useMemo } from "react";

// Faint drifting flecks (the CSS-starfield box-shadow trick, muted into
// this app's violet/magenta/pink palette) -- ambient texture over the light
// mesh gradient in body::before, not meant to be individually noticed.
const FIELD_HEIGHT = 2000;
const FIELD_WIDTH = 2000;

interface DotLayer {
  count: number;
  blur: number;
  color: string;
  duration: number;
}

// Muted violet/magenta/pink hues, blended toward neutral gray.
const DOT_LAYERS: DotLayer[] = [
  { count: 90, blur: 0, color: "rgba(45, 19, 151, 0.35)", duration: 90 },
  { count: 30, blur: 1, color: "rgba(190, 73, 154, .30)", duration: 130 },
  { count: 12, blur: 2, color: "rgba(196, 130, 181, .40)", duration: 170 },
];

function randomDots(count: number, blur: number, color: string): string {
  const dots: string[] = [];
  for (let i = 0; i < count; i++) {
    const x = Math.floor(Math.random() * FIELD_WIDTH);
    const y = Math.floor(Math.random() * FIELD_HEIGHT);
    dots.push(`${x}px ${y}px ${blur}px ${color}`);
  }
  return dots.join(", ");
}

export function AmbientParticles() {
  // Randomize once per mount, not per render.
  const layers = useMemo(
    () => DOT_LAYERS.map((l) => ({ ...l, shadow: randomDots(l.count, l.blur, l.color) })),
    [],
  );

  return (
    <div className="ambient-particles" aria-hidden="true">
      {layers.map((l, i) => (
        <div
          key={i}
          className="ambient-particles-layer"
          style={{ animationDuration: `${l.duration}s` }}
        >
          <span className="ambient-dot-field" style={{ boxShadow: l.shadow }} />
          {/* duplicate field one screen-height below, so the upward drift
              loops seamlessly instead of jumping */}
          <span
            className="ambient-dot-field"
            style={{ boxShadow: l.shadow, top: FIELD_HEIGHT }}
          />
        </div>
      ))}
    </div>
  );
}
