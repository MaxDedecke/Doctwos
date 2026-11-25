import React, { useId } from 'react';
import { cn } from "@/lib/utils";

interface LogoProps extends React.SVGProps<SVGSVGElement> {
  className?: string;
}

type Ring = { x: number; y: number; r: number; w: number };
type Gap = { d: string; w: number };

// Blüte (E-21): sechs Blätter, je Nachbarpaar verhakt, und ein kräftiger Kernring, der über allen Blättern liegt.
// app/icon.svg und docs/assets/codena-icon.svg sind aus derselben Geometrie erzeugt.
const PETAL = { count: 6, distance: 26, radius: 14, stroke: 8 };
const CORE: Ring = { x: 50, y: 50, r: 15, w: 11 };

const PETALS: Ring[] = Array.from({ length: PETAL.count }, (_, i) => {
  const angle = ((-90 + (360 / PETAL.count) * i) * Math.PI) / 180;
  return { x: 50 + PETAL.distance * Math.cos(angle), y: 50 + PETAL.distance * Math.sin(angle), r: PETAL.radius, w: PETAL.stroke };
});

function crossings(a: Ring, b: Ring): { x: number; y: number }[] {
  const dx = b.x - a.x, dy = b.y - a.y, d = Math.hypot(dx, dy);
  if (d >= a.r + b.r || d <= Math.abs(a.r - b.r)) return [];
  const l = (d * d + a.r * a.r - b.r * b.r) / (2 * d), h = Math.sqrt(a.r * a.r - l * l);
  const mx = a.x + (dx * l) / d, my = a.y + (dy * l) / d;
  return [{ x: mx + (h * dy) / d, y: my - (h * dx) / d }, { x: mx - (h * dy) / d, y: my + (h * dx) / d }];
}

/** Bogen des oben liegenden Rings um den Kreuzungspunkt; als Maske schneidet er den Spalt in den unteren Ring. */
function gap(over: Ring, p: { x: number; y: number }): Gap {
  const t = Math.atan2(p.y - over.y, p.x - over.x), half = (over.w * 0.9 + 1) / over.r;
  const at = (a: number) => `${(over.x + over.r * Math.cos(a)).toFixed(2)} ${(over.y + over.r * Math.sin(a)).toFixed(2)}`;
  return { d: `M${at(t - half)}A${over.r} ${over.r} 0 0 1 ${at(t + half)}`, w: over.w + 4.5 };
}

const PETAL_GAPS: Gap[][] = (() => {
  const gaps: Gap[][] = PETALS.map(() => []);
  PETALS.forEach((a, i) => {
    const j = (i + 1) % PETALS.length, b = PETALS[j];
    for (const p of crossings(a, b)) {
      // Je Paar liegt an einer Kreuzung das eine, an der anderen das andere Blatt oben: verhakt statt gestapelt.
      if ((b.x - a.x) * (p.y - a.y) - (b.y - a.y) * (p.x - a.x) > 0) gaps[j].push(gap(a, p));
      else gaps[i].push(gap(b, p));
    }
    for (const p of crossings(CORE, a)) gaps[i].push(gap(CORE, p));
  });
  return gaps;
})();

/**
 * CodenaMark – Blüte aus sechs verhakten Ringen um einen Kernring.
 *
 * Die Spalte an den Kreuzungen sind Masken statt Flächen in Hintergrundfarbe,
 * damit die Marke auf jeder Fläche (Karten, getönte Badges) stimmt.
 */
export const CodenaMark: React.FC<LogoProps> = ({ className, ...props }) => {
  const id = `codena-mark-${useId().replace(/:/g, '')}`;
  return (
    <svg
      viewBox="0 0 100 100"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={cn("w-full h-full", className)}
      aria-hidden="true"
      {...props}
    >
      <defs>
        {PETAL_GAPS.map((gaps, i) => (
          <mask key={i} id={`${id}-${i}`} maskUnits="userSpaceOnUse" x="0" y="0" width="100" height="100">
            <rect width="100" height="100" fill="#fff" />
            {gaps.map((g, k) => <path key={k} d={g.d} stroke="#000" strokeWidth={g.w} />)}
          </mask>
        ))}
      </defs>
      {PETALS.map((p, i) => (
        <circle
          key={i}
          cx={p.x.toFixed(2)}
          cy={p.y.toFixed(2)}
          r={p.r}
          stroke="rgb(var(--ds-foreground))"
          strokeWidth={p.w}
          mask={`url(#${id}-${i})`}
        />
      ))}
      <circle cx={CORE.x} cy={CORE.y} r={CORE.r} stroke="rgb(var(--ds-accent))" strokeWidth={CORE.w} />
    </svg>
  );
};

interface CodenaLogoProps {
  className?: string;
}

/**
 * CodenaLogo – Marke + Schriftzug „Codena“. Die Größe kommt aus der Schriftgröße
 * (z. B. `text-5xl`), Marke und Abstand skalieren mit.
 */
export const CodenaLogo: React.FC<CodenaLogoProps> = ({ className }) => (
  <span
    className={cn("inline-flex items-center gap-[0.22em] leading-none whitespace-nowrap text-foreground", className)}
    role="img"
    aria-label="Codena"
  >
    <CodenaMark className="h-[1.45em] w-[1.45em] shrink-0" />
    <span
      aria-hidden="true"
      className="font-extrabold tracking-[-0.035em]"
      style={{ fontFamily: "var(--font-manrope), system-ui, sans-serif" }}
    >
      Codena
    </span>
  </span>
);
