"""Tag every room with the department shaded on the colour space-assignment sheets.

Usage: python3 tools/departments/import_departments.py [<pdf dir>] [<out.ts>]

The sheets (`space-assignments_floor-{lower-level,1..5}_2026-06-21.pdf`, split from "Gateway
Space Assignments w/Furniture 6/21/26") are the One Workplace furniture plans with each
department's rooms shaded in a colour, and a legend of coloured dots with the department
names. The line work is the same as the plans the map is traced from (the sheets are the
same size and every room label sits on the same point), so the shaded polygons can be laid
straight over the map's rooms: a room is tagged with the department whose shading covers at
least half of it. The Lower Level sheet is drawn at another scale and rotation; it is mapped
with the same similarity the tracer uses (`FLOORS['0']['transform']` in trace_cad/floors.py).

Writes src/data/gateway/departments.ts: space id -> department, the legend colours, and the
rooms the Level 1 sheet marks as reservable meeting rooms. Rooms only partly shaded, shaded in
two colours, or shaded in a colour the sheet's legend does not name are listed on stdout for
review. Requires pymupdf, numpy and Pillow.
"""
import math
import os
import re
import sys

import numpy as np
import pymupdf
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, '..', 'trace_cad'))
from floors import FLOORS  # noqa: E402  (the Lower Level sheet's registration transform)
from levels import GATEWAY, LEVELS, flatten, read_origin, read_rooms  # noqa: E402

PDF_DIR = os.path.normpath(os.path.join(HERE, '..', '..', 'floorplans', 'architect-pdfs', 'floorplans'))
SHEET = 'space-assignments_floor-{}_2026-06-21.pdf'
OUT = os.path.join(GATEWAY, 'departments.ts')

ASSIGN = 0.5   # a room is the department's when its shading covers at least this much of it
NOTE = 0.2     # less than ASSIGN but more than this: listed for review
LEGEND_FONT = 40.0   # the legend names are set in 48 pt; the sheet title in 36 pt
DOT_SIZE = (45, 75)  # the legend dots are ~62 pt circles
COLOR_TOL = 0.55     # RGB distance to the nearest legend colour on the same sheet (the shades drift a little) ...
COLOR_TOL_OTHER = 0.1  # ... or, failing that, to a colour named on another sheet
# The Lower Level sheet has no legend: its blue is the Level 1 sheet's CDSS, and the editing
# room it shades is annotated "CDSS AV Team". Its red (shipping & receiving) is not named anywhere.
PAGE_LEGEND = {'0': {(0.0, 0.0, 1.0): 'CDSS'}}
RESERVABLE = re.compile(r'reservable', re.I)


def rgb(c):
    return tuple(round(float(v), 3) for v in c[:3])


def is_white(c):
    return all(v > 0.97 for v in c)


def is_black(c):
    return all(v < 0.05 for v in c)


def dist(a, b):
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def hexcolor(c):
    return '#%02x%02x%02x' % tuple(round(v * 255) for v in c)


def read_sheet(path):
    """(legend {colour: name}, fills [(colour, polygon)]) of one sheet."""
    page = pymupdf.open(path)[0]
    # legend names: the big text lines, stacked lines joined ("CDSS Dean's" + "Office")
    lines = []
    for block in page.get_text('dict')['blocks']:
        if block['type'] != 0:
            continue
        for line in block['lines']:
            text = ' '.join(s['text'] for s in line['spans']).strip()
            size = max(s['size'] for s in line['spans'])
            if text and size >= LEGEND_FONT:
                lines.append([list(line['bbox']), text])
    lines.sort(key=lambda l: (l[0][1], l[0][0]))
    labels = []
    for bbox, text in lines:
        if labels and abs(labels[-1][0][0] - bbox[0]) < 8 and bbox[1] - labels[-1][0][3] < 2:
            labels[-1][0][3] = bbox[3]
            labels[-1][1] += ' ' + text
        else:
            labels.append([bbox, text])
    dots, fills = [], []
    for d in page.get_drawings():
        fill = d.get('fill')
        if fill is None or is_white(fill) or is_black(fill):
            continue
        kinds = {it[0] for it in d['items']}
        r = d['rect']
        if kinds == {'c'} and DOT_SIZE[0] <= r.width <= DOT_SIZE[1] and abs(r.width - r.height) < 8:
            dots.append((rgb(fill), r))
        elif kinds <= {'l', 'qu'} and min(r.width, r.height) >= 15:
            pts = []
            for it in d['items']:
                if it[0] == 'l':
                    if not pts:
                        pts.append((it[1].x, it[1].y))
                    pts.append((it[2].x, it[2].y))
                else:
                    q = it[1]
                    pts += [(p.x, p.y) for p in (q.ul, q.ur, q.lr, q.ll)]
            fills.append((rgb(fill), pts))
    # pair each dot with the name beside it (same height), leftovers by order
    legend = {}
    free = list(labels)
    unpaired = []
    for colour, r in sorted(dots, key=lambda t: t[1].y0):
        cy = (r.y0 + r.y1) / 2
        hit = min(free, key=lambda l: abs((l[0][1] + l[0][3]) / 2 - cy), default=None)
        if hit and abs((hit[0][1] + hit[0][3]) / 2 - cy) < 30:
            legend[colour] = hit[1]
            free.remove(hit)
        else:
            unpaired.append(colour)
    for colour, (bbox, text) in zip(unpaired, sorted(free, key=lambda l: l[0][1])):
        legend[colour] = text
    return legend, fills


def name_for(colour, legend, everywhere):
    """The legend name of a shading colour: the nearest on the same sheet, else an exact
    match on another sheet (sheets reuse a palette loosely)."""
    best = min(legend, key=lambda c: dist(c, colour), default=None)
    if best is not None and dist(best, colour) <= COLOR_TOL:
        return legend[best]
    best = min(everywhere, key=lambda c: dist(c, colour), default=None)
    if best is not None and dist(best, colour) <= COLOR_TOL_OTHER:
        return everywhere[best]
    return None


def sheet_mapper(level, origin):
    """Frame coordinates -> this level's sheet points."""
    ox, oy = origin
    t = FLOORS[level]['transform']
    if not t:
        return lambda x, y: (x + ox, y + oy)
    s, deg, dx, dy = t
    c, si = math.cos(math.radians(deg)) * s, math.sin(math.radians(deg)) * s
    det = c * c + si * si

    def inv(x, y):
        X, Y = x + ox - dx, y + oy - dy
        return ((c * X + si * Y) / det, (-si * X + c * Y) / det)
    return inv


def coverage(room, fills_by_name):
    """{name: fraction of the room's area under that name's shading}."""
    xs, ys = [p[0] for p in room], [p[1] for p in room]
    x0, y0 = int(math.floor(min(xs))) - 1, int(math.floor(min(ys))) - 1
    w, h = int(math.ceil(max(xs))) - x0 + 2, int(math.ceil(max(ys))) - y0 + 2
    if w < 2 or h < 2:
        return {}
    mask = Image.new('1', (w, h), 0)
    ImageDraw.Draw(mask).polygon([(x - x0, y - y0) for x, y in room], fill=1)
    room_px = np.array(mask, bool)
    area = room_px.sum()
    if not area:
        return {}
    out = {}
    for name, polys in fills_by_name.items():
        m = Image.new('1', (w, h), 0)
        draw = ImageDraw.Draw(m)
        for poly in polys:
            px, py = [p[0] for p in poly], [p[1] for p in poly]
            if max(px) < x0 or min(px) > x0 + w or max(py) < y0 or min(py) > y0 + h:
                continue
            draw.polygon([(x - x0, y - y0) for x, y in poly], fill=1)
        frac = (np.array(m, bool) & room_px).sum() / area
        if frac > 0:
            out[name] = float(frac)
    return out


def ts_str(s):
    return "'" + s.replace('\\', '\\\\').replace("'", "\\'") + "'"


def main(pdf_dir=PDF_DIR, out=OUT):
    origin = read_origin()
    sheets = {}
    for level in LEVELS:
        name = 'lower-level' if level == '0' else level
        path = os.path.join(pdf_dir, SHEET.format(name))
        if not os.path.exists(path):
            raise SystemExit(f'missing {path}')
        legend, fills = read_sheet(path)
        legend = {**legend, **PAGE_LEGEND.get(level, {})}
        sheets[level] = (legend, fills)
        print(f'level {level}: legend {", ".join(f"{n} {hexcolor(c)}" for c, n in legend.items()) or "(none)"}; {len(fills)} shaded areas')
    everywhere = {}
    for legend, _ in sheets.values():
        for c, n in legend.items():
            everywhere.setdefault(c, n)
    colours = {}      # name -> colour
    departments = {}  # space id -> name
    reservable = []
    for level in LEVELS:
        legend, fills = sheets[level]
        by_name = {}
        unnamed = set()
        for colour, poly in fills:
            name = name_for(colour, legend, everywhere)
            if name is None:
                unnamed.add(colour)
                continue
            by_name.setdefault(name, []).append(poly)
            colours.setdefault(name, colour)
        for c in sorted(unnamed):
            print(f'  level {level}: shading {hexcolor(c)} is not in any legend; ignored')
        to_sheet = sheet_mapper(level, origin)
        for room in read_rooms(level):
            if room['category'] == 'circulation' or room['id'].startswith('room-'):
                continue
            poly = [to_sheet(x, y) for x, y in flatten(room['polygon'])]
            cov = sorted(coverage(poly, by_name).items(), key=lambda kv: -kv[1])
            if not cov:
                continue
            (name, frac), rest = cov[0], cov[1:]
            label = room['extra'].get('name', room['id'])
            if frac >= ASSIGN:
                if RESERVABLE.search(name):
                    reservable.append(room['space_id'])
                else:
                    departments[room['space_id']] = name
                if rest and rest[0][1] >= NOTE:
                    print(f'  level {level}: {label} is {name} ({frac:.0%}) but also {rest[0][0]} ({rest[0][1]:.0%})')
            elif frac >= NOTE:
                print(f'  level {level}: {label} is only {frac:.0%} {name}; not tagged')
    lines = [
        '// GENERATED by tools/departments/import_departments.py from the colour space-assignment sheets',
        "// (floorplans/architect-pdfs/floorplans/space-assignments_floor-*_2026-06-21.pdf) — do not edit by hand.",
        '',
        '/** Each department’s shading colour on the sheets (drawn there at 25% opacity). */',
        'export const DEPARTMENT_COLORS: Record<string, string> = {',
        *(f'  {ts_str(n)}: {ts_str(hexcolor(c))},' for n, c in sorted(colours.items()) if not RESERVABLE.search(n)),
        '};',
        '',
        '/** Space id → the department whose shading covers the room on its sheet. */',
        'export const DEPARTMENTS: Record<string, string> = {',
        *(f'  {ts_str(k)}: {ts_str(v)},' for k, v in sorted(departments.items())),
        '};',
        '',
        '/** Spaces the Level 1 sheet marks as reservable meeting rooms. */',
        'export const RESERVABLE: string[] = [' + ', '.join(ts_str(s) for s in sorted(reservable)) + '];',
        '',
    ]
    open(out, 'w').write('\n'.join(lines))
    print(f'{out}: {len(departments)} rooms in {len(colours) - sum(1 for n in colours if RESERVABLE.search(n))} departments, {len(reservable)} reservable')


if __name__ == '__main__':
    main(*sys.argv[1:3])
