# trace_cad — floor data from the CAD plan-view PDFs

Generates `src/data/gateway/level{0..5}.ts` and `frame.ts` from the One Workplace furniture
plans (`floorplan_floor-{lower-level,1,2,3,4,5}_2025-10-02.pdf`, one 48"×36" vector sheet
each, committed in `floorplans/architect-pdfs/floorplans/`). Requires `pymupdf`, `numpy`, `opencv-python-headless`,
`scipy`, `scikit-image`, `shapely`.

Run from `tools/trace_cad/` with a temporary workdir outside the repository.

```sh
python3 gen.py ../../floorplans/architect-pdfs/floorplans <workdir>          # extract + segment every floor (~10 min)
python3 gen.py ../../floorplans/architect-pdfs/floorplans <workdir> 3        # just floor 3
python3 emit_ts.py <workdir> ../../src/data/gateway   # write the TypeScript modules
```

A workdir holding only some floors is fine: `emit_ts.py` then keeps the shared frame recorded in
`frame.ts` (`FRAME` and `ORIGIN`) instead of recomputing it, so one level can be regenerated
without moving the others.

`<workdir>` gets, per sheet, `<pdf>_geom.json` (cached vector extraction), `<pdf>_rooms.json`
(the result) and `<pdf>_debug.png` (overlay: filled rooms, outlined open areas, red unlabelled
regions with their index, orange desks, magenta outline, grey exterior). Extracting a sheet needs ~1.5 GB of
RAM, so floors are processed one at a time.

## How it works

1. `extract.py` — pulls every stroke, small chained polyline, furniture quad and text line out
   of the PDF with PyMuPDF. The sheets have no layers: walls, furniture and hatching are all
   plain black strokes. Multi-segment paths of furniture size and single closed quads with a
   real short side (desks are one bold quad each) are flagged as furniture; the room polygons
   and the open areas are traced on a raster without them.
2. `rooms.py` — rasterises the black strokes at 1 px per PDF point and flood-fills rooms:
   - Walls are drawn as short pieces, so nearly all strokes are kept (`MIN_LINE`); a 3×3
     morphological closing seals 1–2 px drafting gaps.
   - Room labels are the 4-digit numbers (plus the name lines next to them). They usually sit
     in the corridor just outside the door, so each label is matched one-to-one with the
     nearest door swing (arcs found by fitting circles to the small polylines) and the fill is
     seeded just beyond the arc. Labels without a door are filled from the label itself or
     from a ring of points around it.
   - Two rooms whose shared partition has a gap fill as one region; when a second door seed
     lands in a region another label already owns, the region is split between the two seeds
     by geodesic distance (watershed).
   - A small room whose door is drawn without a swing (focus rooms) leaks through the
     opening; the raster around its label is closed with a growing kernel until the fill is a
     room-sized enclosed region. Phone-booth pods stand with an open front, so they are boxed
     from the medium-length strokes drawn around their label instead.
   - Structural columns are circles of 1 pt strokes (below `MIN_LINE`), so they never reached
     the raster and every wall junction at a column was a gap: rooms leaked into neighbours
     or merged in pairs. Circles of column size whose rim meets a long wall stroke are painted
     as solid discs in both rasters (round chairs and tables are larger and stand clear).
   - Every polygon is then straightened. A room becomes the simplest polygon (4, 5, 6 or 8
     corners) whose edges are least-squares lines through the traced wall pixels and whose
     corners are the intersections of neighbouring walls, accepted when it still covers the
     fill (IoU) and most of the traced wall lies on it (so a curved wall is never faceted).
     Irregular rooms, open areas and the outline get line-fitted straight runs with the
     curved runs traced finely (`straight_runs`), after a round close-then-open (`SMOOTH`)
     that drops the jogs where the fill crept between the two lines of a wall. Rooms in the
     floor's `quad` set are forced to four corners. Polygons are fitted only after every
     room's fill is known, so the furniture-free re-fill never crosses into a neighbour.
   - Rooms may touch but not overlap: the fitted polygons are reconciled with shapely.
     Enclosed rooms keep their shape, then the cores, then the open areas, which also snap to
     their neighbours to close hairline gaps. A room standing inside an open area becomes a
     hole in it (`holes`, drawn with an even-odd fill). Named cores that resolve to one
     region (the three elevator shafts of a bank) are split between their points, and
     restrooms, elevators and stairs are emitted as boxes aligned with their longest wall.
   - The piazzas take their shape from the wayfinding sign photo named in the floor's `sign`
     (`sign.py`): the sign's simplified map is registered onto the CAD outline with a
     homography fitted by iterative closest point (median residual under 3 px), its white
     band between the wings is the piazza, split between the piazza labels by a Voronoi
     diagram and cut away from the rooms and cores the CAD knows precisely. The atrium is
     the ellipse fitted to its traced outline. Porches (and any label in the floor's `smooth`
     set) are drawn as sweeping shapes instead: their cell is closed and opened with a 25 px
     disc so door notches and office corners vanish, and inset 4 px from the rooms.
   - Curves become circular arcs: a run of gently turning edges that lies within 1 px of a
     circle (radius at least 40 px, sweep at most 100°) collapses to one edge carrying a
     DXF-style bulge, which the map draws as a true arc; longer curves split into a few arcs.
     A wall that bows consistently away from its chord and lies on a circle (the curved
     facades, the south wall of the social kitchen 4350) is traced as a curve rather than
     straightened; a stepped or zigzag partition does not count. A long such wall refuses the
     corner fit, and a room in the floor's `quad` set keeps the corner fit but gets an arc for
     that wall (a box with a curved wall). Chains of nearly collinear edges on the outline
     and the open areas collapse to one straight edge, so a facade traced as a zigzag of
     mullion ticks is one line with the curved bay as one arc between two straight walls;
     an arc is only collapsed when it bows less than 3 px, so the long facades keep their
     subtle curves. The outline is arc-fitted before the rooms, and a room whose exterior
     wall runs along a curved facade adopts the facade's circle for that wall, so the
     exterior offices follow the curve. The other way round for a bay: where a room has a
     clearly curved exterior wall (the social kitchen 4350), the outline takes that wall's
     circle at the exterior face (`WALL`, 10 px out) between the room's corners, since the
     interior trace measures the bay better than the exterior one. No room may cross the
     outline; the tracer reports any that does.
     Later polygons adopt the arcs of earlier neighbours along a shared curve, and edges next
     to an enclosed room stay straight.
   - The door swing arcs are rasterised as walls so that rooms close, which would leave a
     quarter-circle notch at every door; each swing that opens into a room is added back to
     that room's polygon, so the map treats the doorway as part of the room. Rooms listed in
     the floor's `box` (research labs whose internal lines are benches, not walls) are reduced
     to their minimum-area bounding rectangle.
   - Labels whose fill still escapes into the corridor network are open areas: the unenclosed
     free space (on the furniture-free raster) is partitioned between them by geodesic
     distance. The desks standing in them (bold quads of worksurface size) are exported as
     `desks`, which the map draws as plain rectangles under the open areas.
   - The exterior is the fill from the sheet corner; the outline is the outer contour of the
     non-exterior components that hold labels (Floor 1 has two: the covered plaza between the
     Southwest block and the main building is marked exterior in `floors.py`).
   - Everything enclosed but unlabelled (stairs, elevators, restrooms, mechanical rooms) is
     listed for hand naming. Hatched floors, stair treads and elevator X marks chop those rooms
     into tiny cells; adjacent cells are merged back into one region.
   - Door arcs lying on the outline are exterior doors and become entrance POIs.
   - Most rooms have four walls: when the simplest line-fitted polygon keeps a notch (a
     pilaster, a closet, a door recess), a looser four-corner fit that still covers the room
     (IoU ≥ `QUAD_IOU`) replaces it.
   - Exterior doors swing out, so their swings used to bump the outline and the doorways
     notched it. Swings lying against the exterior are cut out and the opening sealed (only
     there, so planters close to a facade stay outside); the facade runs straight past the
     door and the door becomes an entrance marker at its doorway.
   - No room may cross the outline: after the arcs are fitted, anything that still sticks out
     (a fill that crept into a facade's wall cavity) is cut along the outline.
   - Floors 1–3 have stairs winding down inside the atrium's rail, so the opening never closes
     as one region; the floor's `atrium` ellipse replaces the stair pieces inside it.
   - Floor 5's indoor blocks stand on a paved roof terrace (`terrace` seeds on its pavers and
     walkways). The deck is one open area with the blocks as its holes.
   - Plans that number only the furnished rooms (Lower Level, 1, 5) set `unnamed`: every
     other enclosed region of room size is emitted as an unnumbered room (a rectangle when it
     nearly fills one), leaving out strips along the facades, corridors and pockets inside a
     room.
   - Rooms whose fill cannot be traced (a label in the corridor, benches drawn as walls, a
     side open to the neighbouring workspace, the tiered lecture halls) are drawn by hand in
     the floor's `hand`, from wall coordinates read off the sheet.
3. `floors.py` — per-floor configuration: label style, hand seeds, gap-sealing strokes, named
   regions (identified by a point inside them), hand polygons, boxed rooms, and the similarity transform
   that registers the Lower Level sheet (drawn at 1/8" = 1' and rotated) onto the upper-floor
   sheets; it was fitted on the six elevator shafts and has a residual below 0.1 pt. Also maps
   the plan's room names to categories and display names.
4. `emit_ts.py` — writes the modules. A final pass guarantees rooms never overlap: arcs fitted
   after the reconciliation, boxed cores, ellipses and hand shapes can still bite a neighbour,
   so each polygon gives up what a higher-priority one covers (enclosed rooms, then cores and
   named regions, then open areas, then unnumbered rooms). Coordinates are PDF points of the upper-floor sheets,
   shifted so the building starts near the origin (`frame.ts`).

## Source inventory and lower-level corrections

See [the reference inventory](../../floorplans/README.md) for every source file and the
room-number/seat-count key extracted from teaching PDF pages 3, 4 and 10.
`LL_TEACHING` in `floors.py` supplies the nine classroom numbers and group-study room B1013
that the CAD furniture plan omits. Its wall polygons omit door swings and furniture notches
while retaining the curved walls. The sign paths include the actual `builsding-signs/`
directory. The lower-level sign mentioned in the ticket is absent from this checkout.

The storage closets wedged between neighbouring classrooms (and the
one between B1008 and B1009, via the floor's `blank` points) are left off the map, so the
classrooms meet. B1040 is a five-walled room whose doors face B1026 on a straight corner wall.
The two rounded open-study areas are numbered B1030 (west curve) and B1010 (inside the main
stair) and drawn as ellipses fitted to their curved walls; the main stair is the band between
B1010 and the stair's outer wall (`_ellipse` and `_band` in `floors.py`).

The East Stair (Floors 1–4) is a `manual` four-sided shape around its flight and the opening
beside it: the traced region ran out along the corridor by the facade.

On Floor 1 the lecture halls 1210 and 1220 are the red outlines on pages 21 and 18 of the
Teaching Spaces PDF, registered onto the CAD sheet with a similarity fitted on the structural
columns along the halls (residual under 2 pt); 1220 gives way to 1210 where the outlines cross,
and the drone lab 1230 is drawn from its walls below 1220. The storage rooms behind the halls
are not shown: the East Hallway (`F1_EAST_HALLWAY`, a generous `manual` shape clipped to the
outline and trimmed by the rooms) runs along the backs of all three to the southeast corner.
