"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

/** Configurations are folded into run records; keep old bookmarks working. */
export default function ConfigurationsRedirectPage() {
  const router = useRouter();
  useEffect(() => {
    router.replace("/runs");
  }, [router]);
  return <p className="text-sm text-muted">Opening runs…</p>;
}
