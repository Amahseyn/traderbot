"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

export default function ActionsRedirectPage() {
  const router = useRouter();
  useEffect(() => {
    router.replace("/experiments");
  }, [router]);
  return <p className="text-sm text-muted">Opening Lab…</p>;
}
