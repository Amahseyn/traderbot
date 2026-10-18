"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { RedirectSplash } from "@/components/ui/RedirectSplash";

export default function ActionsRedirectPage() {
  const router = useRouter();
  useEffect(() => {
    router.replace("/custom");
  }, [router]);
  return <RedirectSplash message="Opening Custom research…" />;
}
