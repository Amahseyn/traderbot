import Link from "next/link";
import { Button } from "@/components/ui/Button";
import { PageHeader } from "@/components/ui/PageHeader";

export default function NotFound() {
  return (
    <div className="space-y-6">
      <PageHeader title="Page not found" eyebrow="404" description="This Lab UI route does not exist. It may have moved — use the navigation above or jump back below." />
      <div className="flex flex-wrap gap-2">
        <Link href="/">
          <Button>Back to overview</Button>
        </Link>
        <Link href="/runs">
          <Button variant="secondary">Browse runs</Button>
        </Link>
      </div>
    </div>
  );
}
