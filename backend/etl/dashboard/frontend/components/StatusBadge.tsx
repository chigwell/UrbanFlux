type StatusBadgeProps = {
  status: number;
};

export function StatusBadge({ status }: StatusBadgeProps) {
  if (status === 1) return <span className="status success">Success</span>;
  if (status === -1) return <span className="status error">Error</span>;
  return <span className="status pending">Pending</span>;
}
