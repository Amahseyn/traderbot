"use client";

import Link from "next/link";
import { WORKFLOW_STEPS } from "@/lib/workflow";

const CARD_STEPS = WORKFLOW_STEPS.filter((step) => step.id !== "overview");

export function WorkflowCards() {
  return (
    <section className="grid gap-3 sm:grid-cols-3" aria-label="Get started">
      {CARD_STEPS.map((step) => (
        <Link key={step.id} href={step.href} className="workflow-card group">
          <div className="text-xs font-medium uppercase tracking-wide text-accent/90">{step.short}</div>
          <div className="mt-1 text-base font-semibold text-white group-hover:text-accent transition">
            {step.label}
          </div>
          <p className="mt-2 text-sm text-muted leading-relaxed">{step.description}</p>
        </Link>
      ))}
    </section>
  );
}
