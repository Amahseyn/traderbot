"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { RedirectSplash } from "@/components/ui/RedirectSplash";

/** Former Lab page — quick jobs and pipelines live under Custom research. */
export default function ExperimentsRedirectPage() {
  const router = useRouter();
  useEffect(() => {
    router.replace("/custom#quick-jobs");
  }, [router]);
  return <RedirectSplash message="Opening Custom research…" />;
}
