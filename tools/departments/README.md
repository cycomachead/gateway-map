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

## Names in offices (`import_names.py`)

The same sheets carry a layer of annotations in Helvetica (the plan's own labels are Arial):
a person's name written across their office, sometimes with a role ("CS Division Chair"), a
note ("+1", "Proposed new hire", "Search #3113") or several people separated by commas,
slashes or line breaks, and desk numbers in the open offices. `import_names.py` lays every
annotation line over the map's rooms with the same registration, gathers the lines written
over each office into stacked blocks (the text is rotated with the building, so reading order
follows the text's own direction), and splits each block into names: pieces of one to four
capitalised words with no role or note word and no room number. A role on its own line beside
a name ("Stat Chair" under "Steve Evans") drops just that line; a role before a name on one
line ("Initiatives  Adrian Hill") keeps the name. Roles, groups ("PhD/Postdoc", "Masters
Students STAT"), searches and desk numbers are dropped.

```sh
npm run names                                          # rewrite sheet_occupants.ts
python3 tools/departments/import_names.py <pdf dir> <out.ts>
```

It writes `src/data/gateway/sheet_occupants.ts` (plan room number → names, spelled as the
sheets spell them), which `building.ts` merges under the EECS directory's `occupants.ts`: the
directory's names come first and a sheet name is added only when it names nobody already
there (allowing a missing hyphen, a one-letter typo, "Venkat" for "Venkatesan"). Everything
dropped from an office, and every annotation in a room that is not an office (the PI names on
the labs, the hoteling huddle rooms, the Dean's suite's conference room), is printed for
review; surnames written alone ("Tangherlini", "Nielsen / Huelsenbeck") are kept as the
sheet gives them.

Corrections to what the sheets say (a room that is vacant, a name that moved) go in
`src/data/gateway/occupant_fixes.ts`, kept by hand and applied after the two sources are merged;
rerunning the importer does not touch it.
