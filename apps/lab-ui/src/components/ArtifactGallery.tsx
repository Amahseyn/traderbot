"use client";

import { apiUrl, type ArtifactRef } from "@/lib/api";

type ArtifactGalleryProps = {
  artifacts: ArtifactRef[];
  title?: string;
};

export function ArtifactGallery({ artifacts, title = "Visualizations" }: ArtifactGalleryProps) {
  if (artifacts.length === 0) {
    return null;
  }

  return (
    <section className="space-y-3">
      <h3 className="text-sm font-medium text-white">{title}</h3>
      <div className="grid gap-4 md:grid-cols-2">
        {artifacts.map((artifact) => (
          <figure key={artifact.url} className="overflow-hidden rounded-xl border border-border bg-panel">
            <img
              src={apiUrl(artifact.url)}
              alt={artifact.name}
              className="w-full bg-surface object-contain"
              loading="lazy"
            />
            <figcaption className="truncate px-3 py-2 text-xs text-muted">{artifact.name}</figcaption>
          </figure>
        ))}
      </div>
    </section>
  );
}
