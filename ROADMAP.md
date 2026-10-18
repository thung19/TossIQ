# TossIQ Dashboard Roadmap

Scoped-down, hackathon-realistic plan derived from the full product spec the
captain provided. The full spec described a multi-week SaaS product
(multi-tenant orgs, device fleets, auth/permissions, PDF reporting, etc.);
this roadmap keeps what's achievable and genuinely demo-able in the time
available, consistent with this project's own stated principle in
`CLAUDE.md`: "avoid overengineering."

Executed one stage at a time. Each stage is a real, merged increment on the
`OCIGenAI` branch -- not a mockup.

## Already done (reused, not rebuilt)
- Core detection pipeline: YOLOE fast path + Cohere Command A Vision advanced
  analysis, async, offline-resilient edge client
- Event persistence + image storage in OCI (Autonomous DB + Object Storage)
- Dashboard with real charts (donut, trend, bar) on a validated design system
- Catalog (PRODUCTS) matching: text-based, plus visual similarity matching
  (Cohere image embeddings + Oracle 23ai/26ai native VECTOR search) landing now
- Hazard flag, visible text, and reusable-condition fields on the advanced
  analysis pipeline landing now
- Rule-based insights/recommendations engine

## Deliberately out of scope for this roadmap
Auth/permissions (nothing to protect yet), maintenance-task assignment (no
user system), PDF export (CSV covers the real need), a fabricated
multi-facility/device hierarchy (no real device fleet exists), bin-fullness
hardware simulation presented as real sensor data.

## Stages

1. **Sidebar navigation shell** -- restructure the single-page dashboard into
   sectioned navigation (Overview / Waste Monitoring / Intelligence / AI Tools
   / Management / Reports), wiring in what already exists as the first pages.
2. **Hazard review workflow** -- acknowledge/resolve states and an incident
   list view, built on the hazard-flag field.
3. **Identify Item page** -- dedicated drag-and-drop/file-picker upload page
   reusing the existing `/classify` pipeline.
4. **Procurement upload + matching** -- CSV upload, vendor/product parsing,
   matching against PRODUCTS (reusing the text + visual matching already
   built), with exact-vs-approximate match labeling.
5. **ASKU chat** -- real OCI Generative AI-backed assistant with access to
   actual stored analytics, not a scripted/fake chat UI.
6. **Reports** -- CSV export of existing analytics.
7. **Locations & Devices / Operations** -- location-level grouping of real
   data; no fabricated device fleet.

## Status
Stages 1 (sidebar navigation) and 2 (hazard review workflow) are merged.
Stage 2's live workflow (trigger a hazard flag, acknowledge it, resolve it)
awaits captain verification against real OCI credentials. Stage 3 is next.
