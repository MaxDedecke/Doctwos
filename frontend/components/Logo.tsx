import React from 'react';
import { cn } from "@/lib/utils";

interface LogoProps extends React.SVGProps<SVGSVGElement> {
  className?: string;
  theme?: string;
}

/**
 * DoctusIcon - Renders just the stylized "C" knowledge network icon.
 */
export const DoctusIcon: React.FC<LogoProps> = ({ className, ...props }) => {
  return (
    <svg
      viewBox="0 0 100 100"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={cn("w-full h-full", className)}
      {...props}
    >
      {/* Outer ring (the "C" shape, open) */}
      <path
        d="M 60 20 A 30 30 0 1 0 60 80"
        stroke="rgb(var(--ds-accent))"
        strokeWidth="10"
        strokeLinecap="round"
        fill="none"
      />
      {/* Center node */}
      <circle cx="50" cy="50" r="9" fill="rgb(var(--ds-accent))" />
      {/* Connecting nodes */}
      <circle cx="60" cy="20" r="6" fill="rgb(var(--ds-accent-base))" />
      <circle cx="60" cy="80" r="6" fill="rgb(var(--ds-accent-base))" />
      <circle cx="32" cy="50" r="6" fill="rgb(var(--ds-accent-base))" />
      {/* Connection lines */}
      <line x1="50" y1="50" x2="60" y2="20" stroke="rgb(var(--ds-accent-base))" strokeWidth="3" />
      <line x1="50" y1="50" x2="60" y2="80" stroke="rgb(var(--ds-accent-base))" strokeWidth="3" />
      <line x1="50" y1="50" x2="32" y2="50" stroke="rgb(var(--ds-accent-base))" strokeWidth="3" />
    </svg>
  );
};

/**
 * DoctusWordmark - Renders only the "doctus" text, adapting the color to light/dark mode.
 */
export const DoctusWordmark: React.FC<LogoProps> = ({ className, theme, ...props }) => {
  const isDark = theme === 'dark';
  return (
    <svg
      viewBox="0 0 160 100"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={cn("w-full h-full", className)}
      {...props}
    >
      <text
        x="5"
        y="65"
        fontFamily="'Space Grotesk', Helvetica, Arial, sans-serif"
        fontSize="40"
        fontWeight="700"
        letterSpacing="2"
        fill={isDark ? "rgb(var(--ds-neutral-100))" : "rgb(var(--ds-neutral-800))"}
        className="transition-colors duration-200"
      >
        doctus
      </text>
    </svg>
  );
};

interface DoctusLogoProps {
  className?: string;
  theme?: string;
  iconClassName?: string;
  wordmarkClassName?: string;
}

/**
 * DoctusLogo - Combined C icon + "doctus" wordmark side-by-side.
 */
export const DoctusLogo: React.FC<DoctusLogoProps> = ({
  className,
  theme,
  iconClassName,
  wordmarkClassName
}) => {
  return (
    <div className={cn("flex items-center gap-2", className)}>
      <DoctusIcon className={cn("h-8 w-8 shrink-0", iconClassName)} />
      <DoctusWordmark className={cn("h-8 w-20 shrink-0", wordmarkClassName)} theme={theme} />
    </div>
  );
};
