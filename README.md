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
  per-floor data lives in `src/data/gateway/`.
- All floors share one coordinate frame and one set of outline vertices
  (`src/data/gateway/outline.ts`), so exterior walls line up exactly when switching floors.
  The vertices were fitted from the perspective-corrected whole-floor signs of Levels 2 and 3:
  straight walls are least-squares lines, corners are their intersections, curved walls are
  circular arcs (`bulge` on a vertex, `bulge = tan(θ/4)`, 1 = semicircle, sign picks the side).
  Level 2 has its own outline (deep entrance notch); Level 1 has its own outline plus a
  detached Southwest block (`islands` on the floor).
- **Levels 1–3 are generated** (`level1.ts`, `level2.ts`, `level3.ts`) by
  `tools/trace_signs/` from the sign photos: each photo is perspective-corrected using the
  four corners of the sign panel (`floorplans/*.jpg` are the corrected images), rooms are
  segmented from the detail signs by colour and divider lines, the wing is warped onto the
  shared outline (affine + thin-plate spline fitted along the walls), and perimeter vertices
  are snapped onto the outline walls. Room numbers and special rooms are assigned in
  `tools/trace_signs/labels.py`. To change a generated room, edit the label tables and rerun
  `python3 gen.py && python3 emit_ts.py` (needs `numpy`, `opencv-python-headless`, `scipy`),
  or edit the `.ts` file directly if you don't need to regenerate.
- **Level 4 is hand-traced** (`level4.ts`): perimeter rooms are defined as a span along a
  named wall (`t0..t1` fractions) plus a depth, via `rowOffWall`, `offWall` and `cornerRoom`
  in `src/data/helpers.ts`, so their outer edge is exactly the outline; interior rooms are
  traced in the detail signs' pixel coordinates and mapped with an affine fitted on the wing
  corners.
- Run the app; data problems (duplicate ids, unknown floors) are logged to the console.
