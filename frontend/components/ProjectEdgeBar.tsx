import { cn } from '@/lib/utils';

interface ProjectEdgeBarProps {
  /** Farbe des gewählten Projekts; ohne Projekt oder ohne Farbe gilt der Doctus-Markenverlauf. */
  color?: string | null;
}

/**
 * Schmale senkrechte Randmarke ganz links neben der Sidebar. Sie zeigt den Projektbezug:
 * im allgemeinen Kontext (oder für ein Projekt ohne Farbe) den Markenverlauf, sonst die
 * Farbe des gewählten Projekts. Ersetzt die frühere waagerechte Farbleiste über den Ansichten.
 */
export function ProjectEdgeBar({ color }: ProjectEdgeBarProps) {
  return (
    <div
      data-testid="project-edge-bar"
      aria-hidden="true"
      className={cn(
        'absolute left-0 top-0 bottom-0 w-1 pointer-events-none z-50 transition-colors duration-300',
        !color && 'doctus-brand-gradient',
      )}
      style={color ? { backgroundColor: color } : undefined}
    />
  );
}
