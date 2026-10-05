"use client";

type JobErrorAlertProps = {
  error: unknown;
};

export function JobErrorAlert({ error }: JobErrorAlertProps) {
  if (!error) {
    return null;
  }
  const message = error instanceof Error ? error.message : String(error);
  return (
    <p className="rounded-lg border border-red-900/50 bg-red-950/30 px-3 py-2 text-sm text-red-300">
      {message}
    </p>
  );
}
