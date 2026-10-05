"use client";

import { useState } from "react";
import { Button } from "@/components/ui/Button";

type JsonBlockProps = {
  value: unknown;
  className?: string;
  /** Start hidden behind a toggle (useful for large run payloads). */
  collapsed?: boolean;
};

export function JsonBlock({ value, className = "", collapsed = false }: JsonBlockProps) {
  const [open, setOpen] = useState(!collapsed);

  if (collapsed && !open) {
    return (
      <Button type="button" variant="ghost" className="text-sm" onClick={() => setOpen(true)}>
        Show JSON
      </Button>
    );
  }

  return (
    <div className="space-y-2">
      {collapsed && (
        <Button type="button" variant="ghost" className="text-sm" onClick={() => setOpen(false)}>
          Hide JSON
        </Button>
      )}
      <pre
        className={`text-xs overflow-auto max-h-96 rounded-lg border border-border bg-surface p-3 whitespace-pre-wrap ${className}`}
      >
        {JSON.stringify(value, null, 2)}
      </pre>
    </div>
  );
}
