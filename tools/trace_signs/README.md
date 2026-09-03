# trace_signs — floor data from wayfinding-sign photos

Pipeline used to generate `src/data/gateway/level{1,2,3}.ts`. It runs on the photos in
`/workspace/.prompt/initial` (the originals are not committed); the perspective-corrected
results are committed as `floorplans/*.jpg`. Requires `numpy`, `opencv-python-headless`,
`scipy`. Scripts expect to run from a working directory containing a `rect/` folder.

1. `rectify.py` — find the four corners of each sign panel (seeded by hand, refined by
   fitting the panel edges) and estimate the panel aspect ratio; then warp each photo to
   a rectangle (`cv2.warpPerspective`) → `rect/IMG_xxxx.png`.
2. `footprint.py`, `outline2.py`, `outline3.py` — extract the building footprint from the
   whole-floor signs, fit straight walls / arcs, and write the shared outline
   (`outline.json` → `src/data/gateway/outline.ts`).
3. `seg.py`, `flat.py`, `rooms.py` — flat-field each detail sign, classify pixels
   (room / open / corridor / white) and split rooms on the dark divider lines →
   `rect/IMG_xxxx_rooms.json` (+ `_comp.png` with component indices for labelling).
4. `register2.py`, `register5.py` — fit the wing's straight walls, intersect them for the
   corners, walk the contour for the curve junctions and build the warp (affine +
   thin-plate spline along the shared walls) from sign pixels to the floor frame.
5. `labels.py` — hand-written map from component index to room number / special room,
   with merge / split / manual-polygon directives for components the segmentation missed.
6. `gen.py` — warp, clean, snap to walls, weld shared vertices; `emit_ts.py` writes the
   TypeScript modules. `wholefloor_items.json` holds entrances, stairs and the atrium
   ellipse read off the whole-floor signs.
