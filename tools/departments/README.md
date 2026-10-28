# departments — which department each room belongs to

`import_departments.py` reads the colour space-assignment sheets
(`floorplans/architect-pdfs/floorplans/space-assignments_floor-{lower-level,1..5}_2026-06-21.pdf`,
split from One Workplace's "Gateway Space Assignments w/Furniture 6/21/26") and writes
`src/data/gateway/departments.ts`: space id → department, the legend colours, and the rooms
the Level 1 sheet marks as reservable meeting rooms. The site shows the department in a room's
details, under its name in the floor list and in search results, and finds rooms by it.

```sh
npm run departments                                    # rewrite departments.ts
python3 tools/departments/import_departments.py <pdf dir> <out.ts>
```

Then review `git diff src/data/gateway/departments.ts` and commit. Requires `pymupdf`,
`numpy` and `Pillow`.

## How it reads the sheets

Each sheet is a furniture plan with every department's rooms shaded in a colour at 25%
opacity, and a legend of coloured dots beside department names (48 pt text; stacked lines
such as "CDSS Dean's" / "Office" are one name). The dots are matched to the name at the
same height, and each shaded polygon to the nearest legend colour (the shades drift a little
between sheets; a colour named on no sheet is reported and ignored). The Lower Level sheet
has no legend: its blue is taken as CDSS, like the Level 1 sheet's, which its "CDSS AV Team"
annotation confirms; its red (shipping & receiving) is unnamed and ignored.

The sheets are the same size as the plans the map is traced from and every room label sits
on the same point, so the map's rooms (read back from `src/data/gateway/level*.ts` by
`levels.py`, mapped into sheet points with the frame origin from `frame.ts` and, for the Lower
Level, the tracer's registration transform) are laid straight over the shading. A room is
tagged with the department whose shading covers at least half of it; rooms covered 20–50%, or
substantially by two colours (an open office shared by two groups), are listed on stdout for
review. Unnumbered rooms and circulation are skipped. The sheets' line work is identical to the
traced plans, so they add nothing to the wall geometry.
