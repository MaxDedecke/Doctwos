import React, { useId } from 'react';
import { cn } from "@/lib/utils";

interface LogoProps extends React.SVGProps<SVGSVGElement> {
  className?: string;
}

/**
 * CodenaMark – zwei ineinandergreifende Kettenglieder.
 *
 * Wo das linke Glied oben über dem rechten liegt, schneidet eine Maske einen
 * Spalt in das rechte Glied. Der Spalt ist durchsichtig statt in Hintergrundfarbe
 * gemalt, damit die Marke auf jeder Fläche (Karten, getönte Badges) stimmt.
 */
export const CodenaMark: React.FC<LogoProps> = ({ className, ...props }) => {
  const maskId = `codena-gap-${useId().replace(/:/g, '')}`;
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
        <mask id={maskId} maskUnits="userSpaceOnUse" x="0" y="0" width="100" height="100">
          <rect width="100" height="100" fill="#fff" />
          <path d="M42.6 30.1A21 21 0 0 1 55.8 38" stroke="#000" strokeWidth="15" />
        </mask>
      </defs>
      <circle cx="36" cy="50" r="21" stroke="rgb(var(--ds-foreground))" strokeWidth="9" />
      <circle cx="64" cy="50" r="21" stroke="rgb(var(--ds-accent))" strokeWidth="9" mask={`url(#${maskId})`} />
    </svg>
  );
};

interface CodenaLogoProps {
  className?: string;
}

/**
 * CodenaLogo – Marke + Schriftzug „codena“. Die Größe kommt aus der Schriftgröße
 * (z. B. `text-5xl`), Marke und Abstand skalieren mit.
 */
export const CodenaLogo: React.FC<CodenaLogoProps> = ({ className }) => (
  <span
    className={cn("inline-flex items-center gap-[0.32em] leading-none whitespace-nowrap text-foreground", className)}
    role="img"
    aria-label="Codena"
  >
    <CodenaMark className="h-[1.05em] w-[1.05em] shrink-0" />
    <span
      aria-hidden="true"
      className="font-extrabold tracking-[-0.035em]"
      style={{ fontFamily: "var(--font-manrope), system-ui, sans-serif" }}
    >
      codena
    </span>
  </span>
);
