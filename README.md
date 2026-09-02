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
  GitHub Pages at `https://cycomachead.github.io/gateway-map/`. It sets `BASE_PATH` so
  asset URLs work under the repository sub-path.
- One-time setup: in the repository settings, under **Pages**, set **Source** to
  **GitHub Actions**.

## Editing the map

- Floors, spaces, and points of interest live in `src/data/building.ts`.
- Level 4 is traced from the wayfinding signs. The outline uses the whole-floor sign's
  pixel coordinates (2000×1057). Rooms are written in the pixel coordinates of the
  Northeast / Southwest detail signs and mapped onto the floor with an affine transform
  fitted on matching corners, so you can refine a wing by re-reading only its sign.
- The outline is built from named wall segments. Rooms on the perimeter are defined as a
  span along a wall (`t0..t1` fractions) plus a depth, via `rowOffWall`, `offWall` and
  `cornerRoom` in `src/data/helpers.ts`, so their outer edge is exactly the outline and
  neighbours share dividing edges. Interior rooms are traced polygons.
- Outline edges are straight by default; add `bulge` to a vertex to make the edge to the
  next vertex a circular arc (`bulge = tan(θ/4)`, 1 = semicircle, sign picks the side).
  Two vertices with `bulge: 1` make a circle. See helpers in `src/data/building.ts`.
- Run the app; data problems (duplicate ids, unknown floors) are logged to the console.
