"use client";

import { Button } from "@/components/ui/Button";

type TablePaginationProps = {
  page: number;
  pageCount: number;
  pageSize: number;
  totalCount: number;
  itemLabel: string;
  onPageChange: (page: number) => void;
};

export function TablePagination({
  page,
  pageCount,
  pageSize,
  totalCount,
  itemLabel,
  onPageChange,
}: TablePaginationProps) {
  if (totalCount === 0) {
    return null;
  }
  const pageClamped = Math.min(Math.max(page, 1), pageCount);
  const rangeStart = (pageClamped - 1) * pageSize + 1;
  const rangeEnd = Math.min(pageClamped * pageSize, totalCount);

  return (
    <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted">
      <span>
        {rangeStart}–{rangeEnd} of {totalCount} {itemLabel}
      </span>
      <div className="flex items-center gap-2">
        <Button
          type="button"
          variant="secondary"
          className="text-xs"
          disabled={pageClamped <= 1}
          onClick={() => onPageChange(Math.max(1, pageClamped - 1))}
        >
          Previous
        </Button>
        <span className="tabular-nums text-slate-300">
          Page {pageClamped} / {pageCount}
        </span>
        <Button
          type="button"
          variant="secondary"
          className="text-xs"
          disabled={pageClamped >= pageCount}
          onClick={() => onPageChange(Math.min(pageCount, pageClamped + 1))}
        >
          Next
        </Button>
      </div>
    </div>
  );
}
