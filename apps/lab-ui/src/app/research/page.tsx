"use client";

import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { PairResearchCharts } from "@/components/PairResearchCharts";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Field, TextInput } from "@/components/ui/Field";
import { PageHeader } from "@/components/ui/PageHeader";
import { api, type PairBacktestResponse } from "@/lib/api";

export default function ResearchPage() {
  const [primaryCsv, setPrimaryCsv] = useState("data/crypto/eth_rls_60.csv");
  const [hedgeCsv, setHedgeCsv] = useState("data/crypto/btc_rls_60.csv");
  const [entryZ, setEntryZ] = useState("2");
  const [exitZ, setExitZ] = useState("0.5");
  const [result, setResult] = useState<PairBacktestResponse | null>(null);

  const mutation = useMutation({
    mutationFn: () =>
      api.pairBacktest({
        primary_csv: primaryCsv,
        hedge_csv: hedgeCsv,
        entry_z: Number(entryZ),
        exit_z: Number(exitZ),
        fee: 0.002,
      }),
    onSuccess: (payload) => setResult(payload),
  });

  const summary = result?.summary;

  return (
    <div className="mx-auto max-w-5xl space-y-6 p-6">
      <PageHeader
        title="Strategy research"
        description="Pair-trading spread dashboard (Martha Stewart–style charts). Uses aligned Nobitex-style CSV paths on the Lab API host — no live orders."
      />
      <Card>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Primary CSV path">
            <TextInput value={primaryCsv} onChange={(event) => setPrimaryCsv(event.target.value)} />
          </Field>
          <Field label="Hedge CSV path">
            <TextInput value={hedgeCsv} onChange={(event) => setHedgeCsv(event.target.value)} />
          </Field>
          <Field label="Entry z (long when spread below −entry)">
            <TextInput value={entryZ} onChange={(event) => setEntryZ(event.target.value)} />
          </Field>
          <Field label="Exit z">
            <TextInput value={exitZ} onChange={(event) => setExitZ(event.target.value)} />
          </Field>
        </div>
        <div className="mt-4 flex flex-wrap items-center gap-3">
          <Button disabled={mutation.isPending} onClick={() => mutation.mutate()}>
            {mutation.isPending ? "Running backtest…" : "Run pair backtest"}
          </Button>
          {mutation.isError && (
            <p className="text-sm text-red-400">{mutation.error instanceof Error ? mutation.error.message : "Failed"}</p>
          )}
        </div>
      </Card>
      {summary && result && (
        <Card>
          <p className="text-sm text-muted">
            Return {summary.return_pct?.toFixed?.(2) ?? summary.return_pct}% · Trades {summary.trades} · Final equity{" "}
            {summary.final_equity}
          </p>
          <div className="mt-4">
            <PairResearchCharts series={result.series} equityCurve={result.equity_curve} trades={result.trades} />
          </div>
        </Card>
      )}
    </div>
  );
}
