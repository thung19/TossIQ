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

## Frontend architecture

Stages 1-2 were built as a single static HTML/CSS/vanilla-JS file served
directly by FastAPI's `StaticFiles` mount -- no build step, no Node
dependency. After stage 2, the captain decided to switch to React for the
remaining stages (better suited to ASKU's chat interface and procurement
upload's multi-step flow). Stage 2.5 migrates the existing vanilla-JS
dashboard/sidebar/hazard-workflow work into React as a foundation; stages
3+ are built as React from there. FastAPI continues serving the built
static output (`frontend/dist`) via the same `StaticFiles` mount -- the
backend's role doesn't change, only how the frontend is authored and built.

The build step is a prerequisite for serving the dashboard:

    cd frontend && npm install && npm run build   # then run the API as before

For frontend development, `npm run dev` serves the app with hot reload and
proxies API requests to a FastAPI server on `http://localhost:8000`.

## Stages

1. **Sidebar navigation shell** -- restructure the single-page dashboard into
   sectioned navigation (Overview / Waste Monitoring / Intelligence / AI Tools
   / Management / Reports), wiring in what already exists as the first pages.
2. **Hazard review workflow** -- acknowledge/resolve states and an incident
   list view, built on the hazard-flag field.
2.5. **React migration** -- set up a Vite + React build, port the existing
   sidebar/Dashboard/Hazard Detection views and all working functionality
   (charts, polling, forms) into React components with zero behavior loss,
   wire FastAPI to serve the built output. Foundational for every stage below.
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
Stages 1 (sidebar navigation), 2 (hazard review workflow), 2.5 (React
migration), and 3 (Identify Item page) are merged. Stage 2's live workflow
(trigger a hazard flag, acknowledge it, resolve it) and stage 2.5's migrated
dashboard await captain verification against real OCI credentials. Stage 4 is
next.
