"use client";

import Link from "next/link";
import { useState } from "react";
import { JobMonitor } from "@/components/JobMonitor";
import {
  DEFAULT_PIPELINE_DATA_STATE,
  PipelineDataSection,
  type PipelineDataSectionState,
} from "@/components/PipelineDataSection";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Page } from "@/components/ui/Page";
import { PageHeader } from "@/components/ui/PageHeader";

export default function DataPage() {
  const [dataState, setDataState] = useState<PipelineDataSectionState>(DEFAULT_PIPELINE_DATA_STATE);
  const [exportJobId, setExportJobId] = useState<string | null>(null);

  function patchDataState(patch: Partial<PipelineDataSectionState>) {
    setDataState((current) => ({ ...current, ...patch }));
  }

  return (
    <Page>
      <PageHeader
        eyebrow="Market Data"
        title="Market data"
        description="Sync exchange catalogs, export OHLC batches, and browse registered datasets. Use selected files in Custom research or download CSVs directly."
        actions={
          <Link href="/custom">
            <Button variant="secondary">Continue to research</Button>
          </Link>
        }
      />

      <Card
        title="Catalog & export"
        description="Filter existing files or queue new exports from Hyperliquid / Nobitex catalogs."
      >
        <PipelineDataSection
          state={dataState}
          onChange={patchDataState}
          onExportJobStarted={setExportJobId}
        />
      </Card>

      <JobMonitor
        activeJobId={exportJobId}
        onSelectJob={setExportJobId}
        jobTypeFilter={["export"]}
        recentJobsTitle="Export jobs"
        recentJobsDescription="OHLC download tasks. New datasets appear in the catalog when each job completes."
      />
    </Page>
  );
}
