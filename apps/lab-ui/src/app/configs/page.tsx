"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { RedirectSplash } from "@/components/ui/RedirectSplash";

/** Configurations are folded into run records; keep old bookmarks working. */
export default function ConfigurationsRedirectPage() {
  const router = useRouter();
  useEffect(() => {
    router.replace("/runs");
  }, [router]);
  return <RedirectSplash message="Opening runs…" />;
}
