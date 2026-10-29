# Vector tracer: room shapes from a wall-only drawing

Status: design, 2026-10-29. Replaces the raster tracing in `tools/trace_cad/rooms.py`.

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
