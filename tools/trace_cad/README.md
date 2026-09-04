# trace_cad — floor data from the CAD plan-view PDFs

Generates `src/data/gateway/level{0..5}.ts` and `frame.ts` from the One Workplace furniture
plans (`Gateway_Plan_View_10_2_2025-Floor_{Lower_Level,1,2,3,4,5}.pdf`, one 48"×36" vector sheet
each; not committed because of their size). Requires `pymupdf`, `numpy`, `opencv-python-headless`,
`scipy`, `scikit-image`.

```sh
python3 gen.py <dir with the PDFs> <workdir>          # extract + segment every floor (~10 min)
python3 gen.py <dir with the PDFs> <workdir> 3        # just floor 3
python3 emit_ts.py <workdir> ../../src/data/gateway   # write the TypeScript modules
```

`<workdir>` gets, per sheet, `<pdf>_geom.json` (cached vector extraction), `<pdf>_rooms.json`
(the result) and `<pdf>_debug.png` (overlay: filled rooms, outlined open areas, red unlabelled
regions with their index, magenta outline, grey exterior). Extracting a sheet needs ~1.5 GB of
RAM, so floors are processed one at a time.

## How it works

1. `extract.py` — pulls every stroke, small chained polyline and text line out of the PDF
   with PyMuPDF. The sheets have no layers: walls, furniture and hatching are all plain black
   strokes.
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
   - Labels whose fill still escapes into the corridor network are open areas: the unenclosed
     free space is partitioned between them by geodesic distance.
   - The exterior is the fill from the sheet corner; the outline is the outer contour of the
     non-exterior components that hold labels (Floor 1 has two: the covered plaza between the
     Southwest block and the main building is marked exterior in `floors.py`).
   - Everything enclosed but unlabelled (stairs, elevators, restrooms, mechanical rooms) is
     listed for hand naming. Hatched floors, stair treads and elevator X marks chop those rooms
     into tiny cells; adjacent cells are merged back into one region.
   - Door arcs lying on the outline are exterior doors and become entrance POIs.
3. `floors.py` — per-floor configuration: label style, hand seeds, gap-sealing strokes, named
   regions (identified by a point inside them), hand polygons, and the similarity transform
   that registers the Lower Level sheet (drawn at 1/8" = 1' and rotated) onto the upper-floor
   sheets; it was fitted on the six elevator shafts and has a residual below 0.1 pt. Also maps
   the plan's room names to categories and display names.
4. `emit_ts.py` — writes the modules. Coordinates are PDF points of the upper-floor sheets,
   shifted so the building starts near the origin (`frame.ts`).
