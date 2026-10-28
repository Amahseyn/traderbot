"use client";

import { useEffect, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { PageSkeleton } from "@/components/ui/States";

function NewRedirectContent() {
  const router = useRouter();
  const searchParams = useSearchParams();

  useEffect(() => {
    const params = new URLSearchParams(searchParams.toString());
    params.set("tab", "discovery");
    router.replace(`/marketcap?${params.toString()}`);
  }, [router, searchParams]);

  return <PageSkeleton />;
}

export default function NewPage() {
  return (
    <Suspense fallback={<PageSkeleton />}>
      <NewRedirectContent />
    </Suspense>
  );
}
