# RC1 Validation Failure Log

Date: 2026-06-30

This document records the latest RC1 validation state for tomorrow's
stabilization pass. It is docs-only and does not change runtime or desktop
behavior.

## Latest Validation Results

- Desktop app launched successfully at `localhost:5173`.
- Operator Console UI is rendering and looks good.
- Backend was unreachable from desktop during screenshot/manual check.
- Full backend validation result: `23 failed, 1327 passed, 2 skipped, 1 warning`.

## Failure Clusters

- Evaluation accountability projection validation.
- Projection registry, drift, and query catalog expected counts.
- Provider execution cancellation and metadata contract drift.
- Runtime dashboard expected counts.
- Transformation session lifecycle status.

## Tomorrow's Stabilization Plan

1. Start the FastAPI backend and verify desktop connectivity.
2. Fix projection and query registry expected contracts.
3. Fix provider execution cancellation and metadata regressions.
4. Fix evaluation accountability projection schema.
5. Fix transformation session lifecycle expectation.
6. Rerun focused tests by cluster, then the full backend suite.
7. Rerun the desktop build and manual workflow.

## Recommended First Fix Cluster

- Start with the projection registry, drift, and query catalog expected count
  cluster.
- Reason: it spans registry contract expectations and likely gates several of
  the downstream validation mismatches, making it the most efficient first
  stabilization target after backend connectivity is restored.
