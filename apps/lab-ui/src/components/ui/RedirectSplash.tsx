import { PageSkeleton } from "@/components/ui/States";

type RedirectSplashProps = {
  message: string;
};

/** Shown while client redirects preserve old bookmarks. */
export function RedirectSplash({ message }: RedirectSplashProps) {
  return (
    <div className="space-y-4" aria-busy="true" aria-live="polite">
      <p className="text-sm text-muted">{message}</p>
      <PageSkeleton tiles={2} />
    </div>
  );
}
