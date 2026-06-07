import { ChevronLeft, ChevronRight } from "lucide-react";

type PaginationProps = {
  page: number;
  pageSize: number;
  total?: number | null;
  hasMore?: boolean;
  onPageChange: (page: number) => void;
};

export function Pagination({
  page,
  pageSize,
  total,
  hasMore,
  onPageChange,
}: PaginationProps) {
  const knownTotal = typeof total === "number";
  const totalPages = knownTotal ? Math.max(1, Math.ceil(total / pageSize)) : null;
  const canGoNext = totalPages === null ? Boolean(hasMore) : page < totalPages;

  return (
    <div className="pagination">
      <button
        className="icon-button"
        type="button"
        title="Previous page"
        disabled={page <= 1}
        onClick={() => onPageChange(page - 1)}
      >
        <ChevronLeft size={18} />
      </button>
      <span className="muted">
        Page {page}
        {totalPages ? ` of ${totalPages}` : ""}
      </span>
      <button
        className="icon-button"
        type="button"
        title="Next page"
        disabled={!canGoNext}
        onClick={() => onPageChange(page + 1)}
      >
        <ChevronRight size={18} />
      </button>
    </div>
  );
}
