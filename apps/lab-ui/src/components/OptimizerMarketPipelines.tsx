"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { PipelineRunCard } from "@/components/PipelineRunCard";
import { ErrorState } from "@/components/ui/States";
import { api, type PipelineSpecRow } from "@/lib/api";
import { catalogPipelines } from "@/lib/pipelines";

export function OptimizerMarketPipelines({ onJob }: { onJob: (jobId: string) => void }) {
  const queryClient = useQueryClient();
  const pipelinesQuery = useQuery({ queryKey: ["pipelines"], queryFn: () => api.pipelines() });
  const pipelines = catalogPipelines(pipelinesQuery.data).filter((row) =>
    row.id === "single-market-research" || row.id === "full-universe-research",
  );

  const pipelineRunMutation = useMutation({
    mutationFn: (body: Record<string, unknown>) => api.postJob("pipeline-run", body),
    onSuccess: (data) => {
      onJob(data.id);
      void queryClient.invalidateQueries({ queryKey: ["jobs"] });
    },
  });

  return (
    <div className="space-y-4">
      {pipelinesQuery.isError && (
        <ErrorState title="Could not load pipelines" error={pipelinesQuery.error} hintAuth={false} />
      )}
      {pipelinesQuery.isLoading && !pipelinesQuery.data && (
        <p className="text-sm text-muted">Loading pipeline catalog…</p>
      )}
      {pipelines.map((pipeline: PipelineSpecRow) => (
        <PipelineRunCard
          key={pipeline.id}
          pipeline={pipeline}
          running={
            pipelineRunMutation.isPending &&
            pipelineRunMutation.variables?.pipeline_id === pipeline.id
          }
          error={
            pipelineRunMutation.isError &&
            pipelineRunMutation.variables?.pipeline_id === pipeline.id
              ? pipelineRunMutation.error instanceof Error
                ? pipelineRunMutation.error.message
                : String(pipelineRunMutation.error)
              : null
          }
          onRun={(body) => pipelineRunMutation.mutate(body)}
        />
      ))}
    </div>
  );
}
