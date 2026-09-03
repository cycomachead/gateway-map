# Gateway Map — Build Plan

An interactive, browser-based map website. The working assumption is that this maps
**the Gateway building** (floor plans, rooms, labs, classrooms, amenities), but the
architecture is data-driven so the same app can render any building, campus, or
network-of-gateways dataset by swapping the data files.

## Goals

- Fast, static site (no backend) that can be hosted on GitHub Pages.
- Data-driven: floors, spaces, and points of interest live in plain JSON/TS files,
  so non-developers can update content without touching rendering code.
- Interactive: pan/zoom, hover and click on spaces, floor switching, search,
  category filters, and shareable deep links.
- Accessible and mobile-friendly.

## Tech choices

| Concern      | Choice                          | Why                                                   |
| ------------ | ------------------------------- | ----------------------------------------------------- |
| Build tool   | Vite + TypeScript               | Zero-config dev server, fast builds, static output.   |
| UI           | Vanilla TS + DOM/SVG            | No framework lock-in; the map is an SVG, not a form.  |
| Map render   | Inline SVG generated from data  | Crisp at any zoom, easily styled, hit-testable.       |
| Styling      | Plain CSS with custom properties| Small surface area, easy theming (light/dark).        |
| Tests        | Vitest (unit) + Playwright (e2e)| Fast unit coverage for data/geometry; e2e for UX.     |
| Hosting      | GitHub Pages via Actions        | Free, matches the static-site constraint.             |

If the UI grows beyond a few panels, migrating to a small framework (Preact/Svelte)
is a contained change because rendering is isolated in `src/map/` and `src/ui/`.

## Milestones

Each step should leave `main` in a working, deployable state.

### 1. Project scaffold  ✅ (prototype)
- Vite + TypeScript app, `.gitignore`, `README` with dev instructions.
- `npm run dev | build | preview | typecheck`.
- Basic page shell: header, map area, side panel.

### 2. Data model  ✅ (prototype)
- `src/data/types.ts`: `Building`, `Floor`, `Space`, `Poi`, `SpaceCategory`.
- `src/data/building.ts`: sample data for a few floors with rooms drawn in a shared
  coordinate system. Outlines are polylines whose edges can be circular arcs
  (DXF-style `bulge` on a vertex), so curved facades and round rooms are first-class.
- Validation helper that checks ids are unique and polygons are well-formed.

### 3. Map rendering  ✅ (prototype)
- `src/map/render.ts`: render a floor as SVG (`<g>` per space, labels, POI markers).
  Shapes are `<path>`s with true arcs; `flatten()` gives a polygon for bbox/centroid math.
- Floor switcher control.
- Category-based colouring via CSS classes.

### 4. Core interaction  ✅ (prototype)
- Hover highlight + tooltip; click selects a space and shows details in the panel.
- Search box with fuzzy-ish matching on names, ids, and tags; results jump to the space.
- Category filter chips that dim non-matching spaces.

### 5. Pan & zoom  ✅ (prototype, basic)
- Wheel / pinch zoom and drag pan on the SVG viewBox.
- "Fit to floor" and "Zoom to selection" helpers.

### 6. Deep links & state
- Encode `floor` and `space` in the URL hash (`#/floor/2/space/210`).
- Restore state on load; update on navigation; support browser back/forward.

### 7. Accessibility & responsive layout
- Keyboard navigation between spaces (tab order, arrow keys), ARIA labels on SVG.
- Reduced-motion support; colour contrast checks.
- Mobile layout: panel becomes a bottom sheet.

### 8. Real content  🔶 (Levels 1–4 done from wayfinding signs)
- Every floor shares one outline (`src/data/gateway/outline.ts`) fitted from the
  perspective-corrected whole-floor signs, so exterior walls coincide across floors.
- Levels 1, 2 and 3 are generated from photos of the detail signs by `tools/trace_signs/`
  (perspective correction from the sign's four corners → colour/divider segmentation →
  warp onto the shared outline → snap perimeter vertices to the walls). The corrected sign
  images are kept in `floorplans/`. Level 4 remains hand-traced in the same frame.
- Known gaps: no Level 1 Southwest detail sign exists, so that block only has its cores and
  two unlabelled rooms; a few small rooms on Levels 2/3 carry no number on the signs and are
  stored as "Unlabelled room"; the Level 2 paper plan was only used as a visual cross-check.
- Fill in room metadata (names, departments, capacity, hours, photos).

### 9. Quality & delivery
- Vitest unit tests for data validation, search, and geometry helpers.
- Playwright smoke test: load page, switch floor, select a room, use search.
- GitHub Actions: typecheck + test on PR; build + deploy to Pages on `main`.

### 10. Nice-to-haves (later)
- Directions between two spaces (graph over doors/corridors, A* pathfinding).
- Embeddable mode (`?embed=1`) for use in other sites.
- Print/export a floor as PNG/PDF.
- Analytics on most-searched spaces.

## Repository layout

```
gateway-map/
  index.html
  package.json
  PLAN.md
  README.md
  public/            static assets (favicon, future floor-plan images)
  src/
    main.ts          app entry; wires data → map → ui
    style.css
    data/            types + building data + validation
    map/             SVG rendering, pan/zoom, geometry helpers
    ui/              side panel, search, filters, floor switcher
    state.ts         tiny store for selected floor/space/filters
```
