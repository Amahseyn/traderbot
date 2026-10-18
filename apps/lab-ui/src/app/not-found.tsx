import Link from "next/link";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Page } from "@/components/ui/Page";
import { PageHeader } from "@/components/ui/PageHeader";

export default function NotFound() {
  return (
    <Page>
      <PageHeader
        eyebrow="404"
        title="Page not found"
        description="This route is not part of Traderbot Lab. Use the navigation bar or pick a common destination below."
      />
      <Card title="Where to go next">
        <div className="flex flex-wrap gap-2">
          <Link href="/">
            <Button>Overview</Button>
          </Link>
          <Link href="/data">
            <Button variant="secondary">Market data</Button>
          </Link>
          <Link href="/custom">
            <Button variant="secondary">Research</Button>
          </Link>
          <Link href="/runs">
            <Button variant="ghost">Runs</Button>
          </Link>
        </div>
      </Card>
    </Page>
  );
}
