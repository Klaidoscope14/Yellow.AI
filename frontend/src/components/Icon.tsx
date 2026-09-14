import type { ReactNode } from "react";

/** One consistent icon language across the app: fixed stroke, rounded joins,
 * currentColor fill. Pass the inner <path>/<circle> elements as children. */
export function Icon({
  children,
  size = 20,
  strokeWidth = 1.75,
  className,
}: {
  children: ReactNode;
  size?: number;
  strokeWidth?: number;
  className?: string;
}) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden
    >
      {children}
    </svg>
  );
}

export const ChevronRightIcon = ({ size = 16 }: { size?: number }) => (
  <Icon size={size} strokeWidth={2}>
    <path d="m9 18 6-6-6-6" />
  </Icon>
);

export const SearchIcon = ({ size = 15 }: { size?: number }) => (
  <Icon size={size} strokeWidth={2}>
    <circle cx="11" cy="11" r="8" />
    <path d="m21 21-4.35-4.35" />
  </Icon>
);
