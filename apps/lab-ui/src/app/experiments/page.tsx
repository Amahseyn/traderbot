"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

/** Former Lab page — quick jobs and pipelines live under Custom research. */
export default function ExperimentsRedirectPage() {
  const router = useRouter();
  useEffect(() => {
    router.replace("/custom#quick-jobs");
  }, [router]);
  return <p className="text-sm text-muted">Opening Custom research…</p>;
}
