"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useCallback, useMemo, useState } from "react";
import { PageSkeleton } from "@/components/ui/States";
import { DiscoveryJobResults } from "@/components/DiscoveryJobResults";
import { DiscoveryRunsHistory } from "@/components/DiscoveryRunsHistory";
import { DiscoveryWorkflowIntro } from "@/components/DiscoveryReportSections";
import { JobMonitor } from "@/components/JobMonitor";
import { OpportunityDiscoveryPanel } from "@/components/OpportunityDiscoveryPanel";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Page } from "@/components/ui/Page";
import { PageHeader } from "@/components/ui/PageHeader";

function NewJobPageContent() {
  const searchParams = useSearchParams();
  const presetMarketSymbols = useMemo(() => {
    const raw = searchParams.get("markets");
    if (!raw?.trim()) {
      return [];
    }
    return raw.split(",").map((item) => item.trim()).filter(Boolean);
  }, [searchParams]);

  const [jobId, setJobId] = useState<string | null>(null);
  const [historyRunId, setHistoryRunId] = useState<string | null>(null);

  const onDiscoveryJob = useCallback((id: string) => {
    setJobId(id);
    setHistoryRunId(null);
  }, []);

  const onSelectHistory = useCallback((runId: string | null, historyJobId: string | null) => {
    setHistoryRunId(runId);
    if (historyJobId) {
      setJobId(historyJobId);
    }
  }, []);

  const highlightSymbols = useMemo(
    () => presetMarketSymbols.map((symbol) => symbol.toUpperCase()),
    [presetMarketSymbols],
  );

  return (
    <Page>
      <PageHeader
        eyebrow="Discovery"
        title="Market discovery"
        description="CoinBeacon via Lab API: status, screener presets, trend board, full discovery job, stored runs, and links to Custom research."
        actions={
          <Link href="/custom">
            <Button variant="secondary">Full custom pipeline</Button>
          </Link>
        }
      />

      <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_minmax(18rem,22rem)] lg:items-start">
        <div className="space-y-8">
          <section id="discovery" className="scroll-mt-24 space-y-6">
            <DiscoveryWorkflowIntro />
            <OpportunityDiscoveryPanel
              onJob={onDiscoveryJob}
              showInlineResults={false}
              presetMarketSymbols={presetMarketSymbols}
            />
            <DiscoveryJobResults jobId={jobId} highlightSymbols={highlightSymbols} />
            <DiscoveryRunsHistory
              selectedRunId={historyRunId}
              onSelectRun={onSelectHistory}
              highlightSymbols={highlightSymbols}
            />
          </section>

          <section className="grid gap-4 sm:grid-cols-2">
            <Card
              title="Custom research pipeline"
              description="Multi-dataset export, walk-forward compare, optimizer sweeps, and charts."
            >
              <Link href="/custom">
                <Button variant="secondary">Open Custom research</Button>
              </Link>
            </Card>
            <Card
              title="Optimizer"
              description="Optuna sweeps, batch tuning, and Hyperliquid research pipelines."
            >
              <Link href="/optimizer">
                <Button variant="secondary">Open Optimizer</Button>
              </Link>
            </Card>
          </section>
        </div>

        <div className="lg:sticky lg:top-24 lg:max-h-[calc(100vh-7rem)] lg:overflow-y-auto">
          <JobMonitor
            activeJobId={jobId}
            onSelectJob={setJobId}
            jobTypeFilter={["opportunity-discovery", "custom-research", "strategy-compare", "strategy-sweep", "strategy-test"]}
            recentJobsTitle="Recent jobs"
            recentJobsDescription="Discovery and research jobs from this session."
            logMode="full"
            alwaysShowLogPanel
          />
        </div>
      </div>
    </Page>
  );
}

export default function NewJobPage() {
  return (
    <Suspense fallback={<PageSkeleton />}>
      <NewJobPageContent />
    </Suspense>
  );
}
