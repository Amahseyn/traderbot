type JsonBlockProps = {
  value: unknown;
  className?: string;
};

export function JsonBlock({ value, className = "" }: JsonBlockProps) {
  return (
    <pre
      className={`text-xs overflow-auto rounded-lg border border-border bg-surface p-3 whitespace-pre-wrap ${className}`}
    >
      {JSON.stringify(value, null, 2)}
    </pre>
  );
}
