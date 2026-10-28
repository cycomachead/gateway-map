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
npm run occupants  # re-import faculty office assignments from the EECS directory
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

## Floor and room URLs

- Each floor has a path: `/floor-1` through `/floor-5`, plus `/floor-0` for the
  Lower Level. Opening the site root selects `/floor-1`.
- Selecting a room adds its space ID as a query parameter, for example
  `/floor-4?room=4-4161`. Shared links and reloads restore the room selection;
  browser Back and Forward restore previous floor and room selections.
- Unknown rooms or rooms on a different floor are cleared from the URL. When
  served by an SPA host, unknown floor paths fall back to Floor 1; static hosts
  serve their usual 404 for paths that were not generated.
- URLs respect the deployment base path: on GitHub Pages the example becomes
  `/gateway-map/floor-4?room=4-4161`. The build emits an `index.html` for each floor
  so these links also work when opened directly on a static host.

## Keyboard shortcuts

Press `?` (or the **?** button in the header) for the full list. In short: `Ctrl`+`/` or
`Ctrl`+`F` (`⌘` on a Mac) jumps to the search box, `+` and `−` zoom, `1`–`5` and `B` switch
floors (`B` is the Lower Level), the arrow keys move keyboard focus to the next room in that
direction and pan to keep it in view, `Enter` opens the focused room, and `Esc` goes back to
the floor. The shortcuts dialog has a *Require Shift for single-letter shortcuts* preference
(saved in `localStorage`) for people whose screen reader uses single letters to move around
the page; with it on, `B` alone does nothing and `Shift`+`B` goes to the Lower Level. Every
shortcut either moves focus to the control it acted on (floor button, search box, room) or
reports what happened through the polite live region `#announcer`. The **About** button
credits the author and the language models that helped build the site.

## Editing the map

- Floors, spaces, and points of interest are assembled in `src/data/building.ts`; the
  per-floor data lives in `src/data/gateway/level{0..5}.ts` (`0` is the Lower Level).
- **Every level is generated** from the CAD plan-view PDFs (`floorplan_floor-*_2025-10-02.pdf`
  in `floorplans/architect-pdfs/floorplans/`, the One Workplace furniture plans) by `tools/trace_cad/`: the vector line work
  is rasterised, each room is flood-filled from its label on the plan (seeded through the
  door swing when the label sits in the corridor), open areas are partitioned between their
  labels, desks in the open areas are exported as plain rectangles, and the outline is the
  exterior wall. Doorways count as part of their room, walls are straightened, curves are
  circular arcs (a third value on a vertex is the edge's bulge), and spaces are reconciled so
  they touch without overlapping. All floors are drawn in one coordinate frame
  (the PDF point grid of the upper-floor sheets; the Lower Level sheet is registered onto it
  via the elevator shafts), so walls and cores line up exactly when switching floors.
- Rooms the plan does not number (stairs, elevators, restrooms, the atrium, the lecture
  hall) are named in `tools/trace_cad/floors.py`, which also maps the plan's room names to
  categories and display names. To change a generated room, edit that file and rerun
  `python3 gen.py <pdf dir> <workdir> && python3 emit_ts.py <workdir> ../../src/data/gateway`
  (see `tools/trace_cad/README.md`), or edit the `.ts` file directly if you don't need to
  regenerate. A single floor can be regenerated on its own: `gen.py <pdf dir> <workdir> 4` then
  `emit_ts.py` keeps the shared frame from `frame.ts`.
- [`floorplans/README.md`](./floorplans/README.md) inventories all source PDFs, website images
  and wayfinding-sign photos, with extracted lower-level room numbers from the teaching PDF.
  Photos live in `floorplans/builsding-signs/`. The tracer
  registers a floor's sign onto the CAD outline and takes the piazzas' shape from it (the
  white band around the atrium on the sign), so those sweeping curves match the signs; the
  photos are also a handy cross-check for room names.
- **Who sits where** lives in `src/data/gateway/occupants.ts`: plan room number → names. A
  room with occupants shows their names under its number on the map, in the floor list, in the
  tooltip and in the room details, and the search box finds the room by any part of a name.
  `npm run occupants` regenerates the file from the EECS faculty directory
  (<https://www2.eecs.berkeley.edu/Faculty/Lists/faculty.html>), keeping only faculty with a
  Gateway office; the *Refresh faculty occupants* workflow does the same monthly or on demand
  and opens a pull request. See [`tools/faculty/README.md`](./tools/faculty/README.md). Rooms
  that match no space are logged to the console on start.
- Hearst Avenue, north of the building, is hand-placed in `src/data/gateway/streets.ts` and
  drawn on every floor for orientation.
- Run the app; data problems (duplicate ids, unknown floors) are logged to the console.
