# gateway-map

An interactive, data-driven map website for the Gateway building. Static site built with
Vite + TypeScript; the floor plan is rendered as inline SVG from plain data files.

See [PLAN.md](./PLAN.md) for the roadmap and current status.

## Develop

```sh
npm install
npm run dev        # http://localhost:5173
npm run typecheck
npm run build      # outputs to dist/
npm run preview    # serve the production build
npm test           # Playwright end-to-end + axe accessibility tests (builds first)
npm run test:a11y  # just the axe accessibility scans
```

## CI and deployment

- `.github/workflows/ci.yml` runs on every push and pull request: typecheck, build, then
  Playwright end-to-end tests including axe-core accessibility scans (WCAG 2.1 AA + best
  practices). Any axe violation fails the build; the report is uploaded as an artifact.
- `.github/workflows/deploy.yml` builds on pushes to `main` and publishes `dist/` to
  GitHub Pages at `https://mball.co/gateway-map/`. The user site carries the custom
  domain and project sites inherit it, so the build still sets `BASE_PATH` to
  `/gateway-map/` for asset URLs. No `CNAME` file is needed in this repo.
- One-time setup: in the repository settings, under **Pages**, set **Source** to
  **GitHub Actions**.

## Editing the map

- Floors, spaces, and points of interest are assembled in `src/data/building.ts`; the
  per-floor data lives in `src/data/gateway/level{0..5}.ts` (`0` is the Lower Level).
- **Every level is generated** from the CAD plan-view PDFs (`Gateway_Plan_View_10_2_2025-
  Floor_*.pdf`, the One Workplace furniture plans) by `tools/trace_cad/`: the vector line work
  is rasterised, each room is flood-filled from its label on the plan (seeded through the
  door swing when the label sits in the corridor), open areas are partitioned between their
  labels, and the outline is the exterior wall. All floors are drawn in one coordinate frame
  (the PDF point grid of the upper-floor sheets; the Lower Level sheet is registered onto it
  via the elevator shafts), so walls and cores line up exactly when switching floors.
- Rooms the plan does not number (stairs, elevators, restrooms, the atrium, the lecture
  hall) are named in `tools/trace_cad/floors.py`, which also maps the plan's room names to
  categories and display names. To change a generated room, edit that file and rerun
  `python3 gen.py <pdf dir> <workdir> && python3 emit_ts.py <workdir> ../../src/data/gateway`
  (see `tools/trace_cad/README.md`), or edit the `.ts` file directly if you don't need to
  regenerate.
- `floorplans/` keeps the perspective-corrected photos of the wayfinding signs that the first
  version of the map was traced from; they are a handy cross-check for room names.
- Run the app; data problems (duplicate ids, unknown floors) are logged to the console.
