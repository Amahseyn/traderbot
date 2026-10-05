"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

export default function ActionsRedirectPage() {
  const router = useRouter();
  useEffect(() => {
    router.replace("/custom");
  }, [router]);
  return <p className="text-sm text-muted">Opening Custom research…</p>;
}
