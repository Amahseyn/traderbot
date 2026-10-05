import Link from "next/link";
import { Button } from "@/components/ui/Button";
import { PageHeader } from "@/components/ui/PageHeader";

export default function NotFound() {
  return (
    <div className="space-y-6">
      <PageHeader title="Page not found" description="This Lab UI route does not exist." />
      <Link href="/">
        <Button>Back to dashboard</Button>
      </Link>
    </div>
  );
}
