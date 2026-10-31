# Vector tracer: room shapes from a wall-only drawing

Status: implemented on branch `cycomachead/vector-tracer/1` (PR #18), 2026-10-29. Replaces the raster
tracing in `tools/trace_cad/rooms.py`. The *Findings* section records what the implementation
changed against the plan.

## Problem

The CAD sheets are flattened plots: no layers, one stroke width, one colour, walls as double
lines with an opening at every door, furniture and hatching indistinguishable from walls. The
raster tracer compensates with ~1,900 lines of heuristics (closing kernels, growing kernels,
label-to-door matching, watershed splits), each of which costs a regression somewhere else,
and it needs OpenCV, scipy and scikit-image, which the usual machine does not have.

A spike (2026-10-29, floor 3, 4 and 1) showed that a *wall-only vector drawing* polygonizes
into rooms that match the hand-corrected level files for 95 % of enclosed rooms, from about
250 lines. Two facts made the difference: structural columns (circles of tiny strokes the
extractor files as furniture) seal every partition-to-corridor junction, and every door swing
is closed with both chords from its hinge.

## Goals

1. Enclosed rooms traced deterministically from vectors, with parity to the current level
   files measured, not eyeballed.
2. Every correction is data a person can see and edit: a line added to a per-floor patch
   file, read off the simplified drawing. No new heuristics for one-off cases.
3. Runs locally in a venv in a few minutes per floor.
4. The emitter, the per-floor hand data (`floors.py`) and the level-file format stay.

Non-goals: open-plan areas are not traced from furniture clusters any more; they come from
patch polygons (about 20 per floor, drawn once). The old tracer stays until parity is shown.

## Pipeline

```
extract.py   sheet.pdf ───────────► <pdf>_geom.json      (unchanged, cached)
walls.py     geom ────────────────► <pdf>_walls.json + <pdf>_walls.pdf   (the simplified drawing)
patches/     floor-N.json         (hand lines and area polygons, in the repo)
faces.py     walls + patches ─────► <pdf>_rooms.json     (same schema the emitter reads today)
emit_ts.py   rooms.json ──────────► src/data/gateway/level*.ts   (unchanged)
compare.py   rooms.json vs level*.ts ► IoU report        (the regression gate)
```

### walls.py

- Wall candidates: black, unfilled, non-furniture strokes of at least 0.5 pt inside the plan
  border. Furniture-flagged strokes are never walls (desks against a wall cut rooms in half).
- Columns: closed polylines on a circle of radius 2.5–9 pt whose rim touches a wall stroke
  of at least 4 pt, kept as discs.
- Doors: polylines or béziers on a circle of radius 7–24 pt sweeping 60–120°. Both chords
  from the hinge to the arc ends are added as closures (the leaf-side chord only costs a thin
  notch, and choosing a side by heuristics failed on a tenth of the doors).
- Output: `walls.json` (walls, columns, closures, door centres) and `walls.pdf`, the
  simplified drawing: walls black, columns blue, closures red, patch lines green, labels in
  grey. This is the page a person checks and reads coordinates from.

### patches/floor-N.json

```json
{ "lines": [[x0, y0, x1, y1, "3353: door without swing"]],
  "areas": { "3150": [[x, y], [x, y], ...] } }
```

Sheet coordinates (PDF points of that sheet; the Lower Level in its own sheet frame, as the
existing hand data is). `lines` are extra walls. `areas` are open-plan rooms whose label
sits in the corridor network: the polygon is clipped to the free space and the room is
emitted as `kind: open`. Rooms already drawn by hand in `floors.py` (`hand`, `manual`) stay
there.

### faces.py

- Wall mass = union of the strokes, closures and patch lines buffered by 1.5 pt, plus the
  column discs. Free space = plan border minus mass; each connected piece is a face, holes
  filled (furniture never cuts a room). Everything below 300 pt² is dropped.
- Labels: the room numbers and name lines, with the same size and regex rules as today
  (`label_sizes`, `number_re`, `skip` in `floors.py`).
- A label whose face is at most 150,000 pt² names that face (`kind: room`). A label in a
  bigger face is an open area: taken from `patches.areas`, otherwise reported on stdout.
- Faces without a label and above the floor's minimum become `unlabelled` regions, which
  `floors.py`'s `named` list already turns into cores, restrooms and stairs by seed point.
- The outline is the boundary of the plan border minus the face that touches the border
  (floor 1's plaza is marked exterior in `floors.py` as today); islands follow.
- Shapes: each face is grown back by the buffer (mitred, so corners stay corners), then
  simplified at 0.5 pt, collinear runs merged, a four-corner fit kept when it covers the face
  at IoU ≥ 0.9 (the `quad` and `box` lists in `floors.py` still force it), and curved runs
  turned into arcs with the existing `arcify`.
- Exits: door centres within a wall thickness of the outline.
- Desks: the extractor's furniture quads, as today.

### compare.py

For one floor: every numbered room in the committed level file against the face that holds
its label. Prints counts at IoU 0.95/0.9/0.8, the leaked and merged rooms, and the per-category
medians. This is the acceptance test for every change to the tracer: a change may not lower
the counts on any floor.

## Milestones

1. `walls.py` and the simplified PDF, from the spike. `requirements.txt` and a venv note.
2. `faces.py`, `compare.py`, `gen2.py` driver. Parity on floors 1–5 and LL at or above the
   spike (floor 3: 124 of 131 enclosed rooms at IoU ≥ 0.8).
3. Straightening and arcs; emit the level files; diff against the committed ones; fix what
   the diff shows, by patch line where it is a drawing gap.
4. Patch files for the open areas and the swing-less doors on every floor. README switch,
   `rooms.py` and `gen.py` retired.

## Risks

- The Lower Level sheet is at another scale: radii and lengths scale by the label-size
  ratio, as the old tracer does.
- Labs with benches drawn as walls split; the `box` override covers them.
- Tiered lecture halls stay hand polygons.
- The emitter still imports OpenCV for a few helpers; the venv includes it until those are
  moved to shapely.

## Findings from the implementation

- **Facades hide as furniture.** The curved facades and glass fronts are chains of short
  pieces a few hundred points long; the extractor's furniture rule (a multi-piece path of
  furniture size) dropped them, so every curved-wall room leaked. `extract.py` now exports
  every chained polyline and `walls.py` keeps the gently turning open ones (`CHAIN_TURN`).
- **Columns matter more than doors.** Painting the column circles as discs took floor 3 from
  48 to 116 enclosed rooms; closing both chords of every door swing added another 8.
- **The level files are inset.** Growing faces back to the stroke centres lowered parity:
  the committed polygons sit at the face boundary (`GROW = 0`).
- **Hatched cores come in cells.** Elevator shafts, stairs and restrooms are chopped by their
  hatching into faces below room size; cells under four times the floor's minimum room are
  merged across one stroke into regions, which the `named` seeds then find.
- **Shapes: rectangle first.** A minimum rectangle is the exact answer for most rooms. It is
  kept when it covers the face but for slivers and fills nothing bigger than a notch
  (`SLIVER_MAX`, `NOTCH_MAX`); otherwise four lines fitted through the outermost boundary
  points of each side; otherwise the opened, simplified face. Fitting four lines everywhere
  was *worse* than the rectangle on a third of the rooms (a point or two of bias per wall).
  Rooms in the floor's `quad` list get fitted walls with an arc where the boundary bows away
  on a circle (the social kitchen).
- **Arcs are checked.** `arcify` can read a run of notch edges as a curve; an arced polygon
  is only kept when it still traces the face (IoU ≥ 0.985, within 2 pt).
- **Patches are seeded, not written.** `bootstrap_patches.py` takes the open-plan areas,
  piazzas, porches and booths from the committed level files, and seals the edges of rooms
  that leaked or shared a face. Sealing every room that merely differed added false walls
  (door-swing areas), so it is limited to those two cases.
- **Known differences from the level files** (the trace is right or the question is open):
  3346's committed polygon is an axis-aligned square the sheet does not show; 3112's label
  stands in the small room beside the one the level file calls 3112; 2111 is split by a thin
  desk panel drawn from wall to door; 4382's seating strip and 4384's missing third.

## Findings from the first review (2026-10-29)

- **Slits and bites.** A single stroke poking into a room (a wall line overshooting its
  corner, a leader) left a slit in the polygon, a column standing in the wall a round bite.
  A mitred closing of a stroke's width fills the slits (`CLOSE`); the bites are filled only
  within the column's disc (`BITE`), so a doorway recess of the same width stays.
- **Pockets hold furniture.** Pocket absorption had never fired: the hole-filled exterior
  face touches everything, so every pocket "touched the outside". With that fixed, the
  casework strip behind 3346 and 3348 joined its rooms and the rear wall of the row fell
  into line, but empty cavities (a wedge behind 3111's partition) joined too. A pocket now
  has to hold furniture (a quad or a furniture-flagged stroke).
- **Rows share lines.** Every rectangle was fitted on its own, so a row of offices came out
  a few tenths of a point and of a degree apart. Walls of different rooms that face the same
  way, run within 1° and lie within 1.5 pt of one line are put on their common line
  (`align_walls`); the emitter's parallel-walls pass then has less to do.
- **The outline is the facade, not the drafting on it.** Door chords, mullion boxes (13 pt
  wide, 2.5 pt deep) and overshooting lines made the facades zigzag and the arcs fail their
  check. A mitred closing and opening at 8 pt drop them, but only the jogs: pieces nowhere
  wider than 16 pt, no longer than 60 pt, touching one piece of the building and closing no
  court (a thin channel along the Hearst canopy would otherwise be filled and the canopy
  joined to the building). Column bumps go within their discs. The outline is then
  simplified at 1.5 pt and its curves fitted with arcs checked at 6 pt (not 2: the building
  is 3,000 pt across). Floor 3: 120 vertices with 9 arcs instead of 473 without any.
- **Desks only in the open.** The old tracer drew desks where they stood on an open area;
  the first vector version drew every desk-sized quad, including the ones in offices.
- **Cores square to their walls.** The region of an elevator bank is chopped by the X marks
  and a restroom's by its stalls, so a rectangle fitted to the region (or seeded from the
  old trace) could sit 10° off the walls. The tracer now records the length-weighted
  direction of the wall strokes around every unlabelled region (`axis`, modulo 90°; the
  diagonals cancel) and the emitter boxes the cores along it, turns a hand-drawn core box
  onto it when within 15°, and splits an elevator bank along it. On floor 3 both banks come
  out within 0.3° of their facades, which is what the drawing shows.

## Findings from the second review (2026-10-30)

- **Shafts have X marks.** The traced region of an elevator bank is the free space inside
  the shafts, which the biggest shaft (drawn deeper, without a plain X) stretches, so equal
  squares cut from it reached behind the small shafts into the restroom. Each shaft's X is
  two strokes of one length crossing at their midpoints; the bank is now drawn from them
  (`shaft_boxes`, `bank_cells`): one cell per seed, a pitch wide, as deep as the marks, side
  by side along the bank, a seed without a mark getting the cell at that pitch beyond its
  neighbours. The Lower Level's shafts, whose seeds had fallen into the squares below them,
  come out on the shafts and next to each other.
- **A stair and its bank share a back wall.** The X marks the cab; the hoistway's back wall
  is the stair's. Where a stair edge parallel to the bank lies within 30 pt of the bank's
  edge, the shorter is brought out to the longer (`align_cores`).
- **Rooms do not overlap.** Fitted one by one, two rooms could cross by a hairline along a
  shared partition, a box by a wedge of its neighbour. A last pass (`resolve_overlaps`) cuts
  every overlap above half a point from the polygon with the lower standing (traced room
  over open area over named region over unnumbered room; between equals the bigger gives
  way; a polygon with arcs only when nothing else can). Six to thirteen cuts per floor, all
  slivers; the piazza 2004 and the atrium still meet by 7 pt² because both are arcs.
- **Doors are data; markers on mention.** Every door between corridors and open areas is in
  the level file (`doors`: the doorway from hinge to strike, or hinge to hinge for a pair, and
  the open leaf's end), for directions later. Nothing is drawn for them unless the patch
  file names the door, which puts a small circle on the doorway holding the door's own swing
  in miniature, so the arc shows which way it opens.
- **Open areas carry the drafting too.** A piazza clipped to the free space took every door
  chord and column bite along its glass front as a notch; the outline's tidy (jogs filled or
  cut, column bumps removed) now runs on open areas, and their curves get arcs: 2002 went
  from 262 vertices to 35.
- **Hatching merges rooms.** The floor pattern of floor 1's Southwest-block restrooms crosses
  their walls, so the block traced as one region; its three rooms are drawn by hand
  (`manual`), the single-user room in the corner and the two multi-stall halves, which of
  them is the men's being a guess.
- **Data, not code, for the rest.** The copy room beside X403 has no number on the plans
  (a `named` seed on floors 2–4), the Lower Level's north-east corner is one recording
  studio (two seeds, one room), the pits and closets left off the map are `blank` points, a
  room without a number takes its wing from `wings`, and the stair icon and the accessible
  marker are a tag and a POI.
- **The roof deck is its pavers.** The terrace had been a hand polygon of the whole roof with
  the rooms as holes, so the blocks' corridors and the space beyond the roof edge were
  terrace too. The pavers' hatching chops the deck into cells; joined across their strokes
  they are the deck, holes and all (the blocks with their corridors, the skylight, whose panes
  are cells as well and is cut out as the configured ellipse), and the terrace stops at the
  blocks' walls. The patch area only bounds it. Floor 5 also gained its event space, social
  kitchen and west stair as named regions, 5113 as four walls and 5370 off its neighbour.
- **Piazzas are a few curves.** The informal-collab piazzas around the atrium are crescents
  between the walkway's arc and the glass, and every door chord and column along them had
  become a vertex. A round closing and opening at 12 pt, then arcs fitted loosely, leave a
  dozen vertices each; they are study spaces (green) now. Open offices in a floor's `box`
  set are their minimum rectangle.
- **Four walls stay four.** Cutting an overlap out of a rectangle left a notch of a few
  points (5320 against 5310). The wall the overlap lies along now moves in just past it and
  the corners are rebuilt (`shrink_wall`).
- **The deck is fenced where the drawing is not.** The paving behind the north block and the
  north-east offices runs into the central deck without a wall on the sheet, but it is walled
  off in the building; patch lines across the junctions (the west end of the north block,
  the strip east of it, the west end of the band, the south parapet band of the arm, the
  paving west of the central deck) keep the cells apart, and the seeds in those bands are
  gone. What is left is the deck around the skylight and the walkway to the offices.
- **Rooms by hand where the sheet misleads.** 3405's front wall on 3403's line, 3310 out to
  3329's wall, 4112 across the casework to 4114, 1420 as six walls (the entry nook and the
  strip behind room-9 left out), the floor 1 restrooms with the single-user room between the
  two multi-stall ones; copy rooms have a category of their own; occupants are corrected by
  hand in `occupant_fixes.ts` (4115 vacant, two names off 4128).

## Findings from the fourth review (2026-10-30)

- **Piazzas keep off the atrium.** Rounded hard, a piazza could still lap the atrium's rail;
  the atrium ellipse grown by 8 pt is cut out of every piazza, so the inner edge is the rail's
  own curve, a step back.
- **Open offices are rectangles.** Desks stand in blocks, and the odd angles of an area
  clipped to the free space are the corridor's; an open office is one rectangle when that
  covers it at IoU 0.9, else the best pair of rectangles at right angles (a cut along either
  axis of the minimum rectangle, each side's box) at 0.85, else the tidied shape.
- **Facades are flat walls.** The Hearst facade is drawn as facets two to five degrees apart;
  `merge_facets` drops the vertices between them unless they belong to a curve (a run of
  three or more turns the same way), which the arc fit then takes.
- **Every room pulled in by a point.** Neighbours no longer touch and every border shows; the
  inset runs last in the emitter, arcs refitted, so the parity gate (which reads the trace)
  is not affected.
- **Corrections from the map.** A Corrections panel in the app collects notes: pick a room or
  mark a point with the pencil, write what should change and whose name is involved, copy
  the list as text (floor, room or map coordinates, note) for an issue or an LLM. The list is
  kept in the browser. The app took the Berkeley B for its mark and the brand palette for the
  categories and highlights.

## Findings from the fifth review (2026-10-30)

- **A suite between rooms.** The recording studio's nine rooms stand around a hall; the hall is
  the suite: a `manual` region drawn as the convex hull of the rooms and the cores, minus the
  rooms (4 pt off their walls) and the cores' boxes (the stair, elevators and restroom as one
  block, the storage room on its own), opened by 8 pt so no sliver is left, simplified to
  straight lines. `suites` names it and lists a point in each member room, since the members
  stand around it rather than in it; they take its name, and the map draws the suite lighter
  and dashed.
- **Door markers on an edge.** A patch door may name a room; the marker is moved to the nearest
  point of that room's boundary and turned along it (`snap_doors`, after the rooms are final).
  The studio's two entrances sit on the hall.
- **Open areas drawn as given.** The pair-of-rectangles fit at IoU 0.9 put 3190's west corner
  16 pt off the wall it was drawn on. The fit stays where it works; an area listed in the
  floor's `asis` is drawn exactly as its patch polygon when the free space fills 95 % of it.
- **Guided curves.** `guides` in the patch file gives a room three points along its curved
  wall; the room is clipped to the circle through them (4002's wall side).
- **The social kitchens.** 2350, 3350 and 4350 take parallel sides pulled in 2 pt and
  straightened, with the curved ends (the piazza wall, the atrium lobe) fitted as arcs at the
  piazza tolerances (`kitchen_shape`). The sides follow the neighbouring walls, which are not
  quite parallel to each other.
- **Rooms stop at the outline.** Hand polygons and boxed cores could reach past the facade
  (B1008, B1009, 2345); `clip_entries` cuts every room at the outline after the overlap pass.
- **The roof deck.** Joined across its pavers, bounded by the `terrace` patch, fenced by
  `terrace:` patch lines where the paving runs behind a block, rounded 6 pt, kept 2 pt off the
  walls, the skylight's ellipse cut out. The strip south of (1714, 1009) is walled off and
  fenced.
- **Square points.** A Lower Level room whose trace has a jagged tip or stepped side wall is
  drawn as its minimum rectangle when a `square` point lies in it.
- **Rooms by hand this round.** 2405 and 3405 on the line of 2401 and 2403; 2310 and 3310
  square to the building wall; 3112 and 4112 with their wall moved to 3114; 4382 aligned with
  4384; 5360 and 5370 aligned with each other and the wall; 4130 and 4340 as patch areas
  parallel to the office rows; a storage room on the Lower Level as a `manual` room east of
  the hall partition (the marked point lies in the open hall).
- **Still open.** 2004 and the atrium still meet by 7 pt² (both arcs); the stall rows of the
  women's restrooms on floors 2 and 4 trace as their own regions.

## Findings from the sixth review (2026-10-30)

- **Good enough beats exact.** The bar for the map is to look good and be usable: shapes
  accurate, not every detail. 2004 stays as it is (twelve vertices, two arcs) though fewer
  lines would be nicer.
- **One shape for a repeated core.** The Southwest core's restrooms traced differently on
  each of floors 2–4 (the women's room without its stall row, or with the vestibule beside
  it; the single-user room with the closet above it), so they are `manual` rooms drawn once
  from the walls and shared by the three floors (`SW_CORE_RESTROOMS`). Floor 1 traces the
  full room on its own and confirmed the rectangle.
- **Hidden on floor 5.** Three closets and shafts of the south bar are `blank` points.

## Findings from the seventh review (2026-10-30)

- **The atrium stairs.** Floors 2–4 have stairs winding inside the atrium's rail: one on the
  west (2 → 3), two on floor 3, one on the east (3 → 4). Their treads are the radial strokes
  between the opening and the rail standing in rows of parallel strokes; a tread the handrail
  cuts in two, or drawn with its nosing, is merged along its line. Sorted around the atrium
  the treads fall into flights (a landing is a gap of more than two treads), and strokes a
  long way off are not the stair's. The stair follows the atrium: the band of the ellipse
  between the treads' median inner and outer radii from the first tread to the last (the
  straight end flights are drawn on the curve too), and the arrow runs along the ellipse
  between them. The break lines misled on direction: Michael confirmed both stairs rise from
  their north end to their south end (the west one 2 → 3, the east one 3 → 4). The map draws each as a solid band
  over the atrium with a stairs icon, an arrow and an Up/Down label at the arrow's head; the
  atrium is exempt from the overlap pass under its stairs. Floor 4 traces its atrium from the
  opening, so `stair_frame` gives it floor 3's rail ellipse for the detection.
- **The second Northeast stair.** East of the Northeast elevators, south of the men's
  restroom (floor 1) and of 2133 (floor 2), a stair traces only as slivers; it is a `manual`
  room drawn from its walls on both floors (`NE_STAIR_EAST`).
- **Open offices around their desks.** `desk_box`: the rectangle around the worksurfaces
  standing in the patch area (not another area's), in the desks' own frame, 8 pt out for
  the chairs (3360, 3340, 4340). 3340 no longer cuts into 3330.
- **Facade jogs.** The south facade of floor 4 is drawn in panels with 2 pt steps at the
  joints; `drop_jogs` removes an edge shorter than 4 pt between two stretches of one wall.
- **Captions.** A numbered room of 10 000 pt² or more whose name is not generic shows the
  name under its number (4310 Masters Student Work Space, the labs, meeting rooms,
  classrooms). 3397 is renamed ERSO IT Help Desk (`rename`, with ERSO as an acronym).
- **Copy rooms** carry a printer icon, drawn when the room is big enough for it.
- **3350** is drawn from its patch area with its right side 10 pt further left and its south
  tip 30 pt shorter, bulges kept.
- **About.** The dialog names the Barbara and Gerson Bakar Gateway and CDSS, states the
  WCAG 2.2 AA target with a contact, and has an Info button that swaps in the Info dialog.

## Findings from the ninth review (2026-10-30)

- **A desk block's cut-out.** 3160 is the rectangle around its desks; 3151 and the closet
  beside it stand in it and are cut out as one box in the desks' frame (boxes that meet join),
  so the notch has right angles and the shape stays simple.
- **The same room on every floor.** 3310 takes 2310's hand polygon (a right angle at its
  lower left); the west stair along the Southwest facade, which floor 5 traces as one region,
  is drawn on floors 2–4 as that region squared off (`WEST_STAIR_UPPER`), the same size and
  place on each.
- **Icons by room.** `icons` in the floor config gives a room a pictogram; 3397 shows a
  computer. Every copy room shows the printer whatever the plan calls it (1456).
