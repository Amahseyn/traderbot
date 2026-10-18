"use client";

import { formatApiError, isLabAuthError } from "@/lib/api";
import { LabApiAuthHint } from "@/components/LabApiAuth";

type JobErrorAlertProps = {
  error: unknown;
};

/** Compact inline alert for failed job POSTs and form mutations. */
export function JobErrorAlert({ error }: JobErrorAlertProps) {
  if (!error) {
    return null;
  }
  return (
    <div
      role="alert"
      className="rounded-lg border border-red-500/40 bg-red-500/10 px-3 py-2 text-sm text-red-200/90"
    >
      <p className="break-words">{formatApiError(error)}</p>
      {isLabAuthError(error) ? <LabApiAuthHint /> : null}
    </div>
  );
}
