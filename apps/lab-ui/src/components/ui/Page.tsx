import type { ReactNode } from "react";

type PageProps = {
  children: ReactNode;
  className?: string;
};

/** Consistent vertical rhythm and entrance motion for route content. */
export function Page({ children, className = "" }: PageProps) {
  return <div className={`page-stack animate-page-in ${className}`.trim()}>{children}</div>;
}
