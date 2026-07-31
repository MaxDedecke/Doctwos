import React from 'react';
import { cn } from "@/lib/utils";

interface LogoProps extends React.SVGProps<SVGSVGElement> {
  className?: string;
  theme?: string;
}

/**
 * DoctusIcon - A structural D assembled from a frame and a forward trace.
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
      <path d="M18 14H48C72 14 86 28 86 50C86 72 72 86 48 86H18V14Z" fill="rgb(var(--ds-accent))" />
      <path d="M35 30H48C61 30 69 37 69 50C69 63 61 70 48 70H35V30Z" fill="rgb(var(--ds-background))" />
      <path d="M8 50H50" stroke="rgb(var(--ds-on-accent))" strokeWidth="8" />
      <path d="M43 40L55 50L43 60" stroke="rgb(var(--ds-on-accent))" strokeWidth="6" strokeLinecap="square" strokeLinejoin="miter" />
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
      viewBox="0 0 220 100"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={cn("w-full h-full", className)}
      {...props}
    >
      <text
        x="5"
        y="65"
        fontFamily="'Space Grotesk', Helvetica, Arial, sans-serif"
        fontSize="42"
        fontWeight="600"
        letterSpacing="-1"
        fill={isDark ? "rgb(var(--ds-neutral-100))" : "rgb(var(--ds-neutral-800))"}
        className="transition-colors duration-200"
      >
        doctwos
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
      <DoctusWordmark className={cn("h-8 w-24 shrink-0", wordmarkClassName)} theme={theme} />
    </div>
  );
};
