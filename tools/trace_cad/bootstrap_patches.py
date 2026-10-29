"""Seed a floor's patch file from the committed level file.

Usage: python3 bootstrap_patches.py <workdir> <floor id> [--write]

The level files hold the hand-corrected map. For every numbered room the tracer has no
polygon for (see compare.py), this proposes a patch:

- a room whose label sits in the corridor network (an open office, a piazza, a porch) gets
  its level polygon as an `areas` entry;
- an enclosed room that leaked gets `lines` for the parts of its level polygon's edges that
  cross free space (the doorway drawn without a swing, the gap at a glass front).

Without --write the proposal is printed; with it, entries are merged into
patches/floor-<label>.json (existing entries are kept). Review the simplified drawing after
a run: a seeded line is only as good as the level polygon it came from.
"""
import json
import os
import sys

from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import unary_union

from compare import frame_to_sheet, report
from faces import BUF, labels
from floors import FLOORS, category
from patches import load_patches, path_for
from walls import BORDER

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'departments'))
from levels import flatten, read_rooms  # noqa: E402

OPEN_CATEGORIES = {'open', 'piazza', 'informal', 'porch', 'lounge', 'study', 'amenity'}
MIN_SEAL = 2.0  # pt; shorter uncovered pieces are corners, not gaps
GOOD = 0.9      # a room matching the level file this well needs no patch


def wall_mass(w, patches):
    scale = w['scale']
    lines = [LineString([(a, b), (c, d)]) for a, b, c, d in w['walls'] + w['closures']]
    lines += [LineString([(a, b), (c, d)]) for a, b, c, d, *_ in patches['lines']]
    return unary_union([ln.buffer(BUF * scale, cap_style='flat') for ln in lines if ln.length > 0]
                       + [Point(cx, cy).buffer(r + 0.5) for cx, cy, r in w['columns']])


def propose(workdir, fid):
    cfg = FLOORS[fid]
    w = json.load(open(os.path.join(workdir, f"{cfg['pdf']}_walls.json")))
    geom = json.load(open(os.path.join(workdir, f"{cfg['pdf']}_geom.json")))
    label_at = {l['id']: Point(l['x'], l['y']) for l in labels(geom, cfg)}
    patches = load_patches(fid)
    rows = {r[0]: r for r in report(workdir, fid)}
    to_sheet = frame_to_sheet(fid)
    mass = wall_mass(w, patches).buffer(1.0)
    areas, lines = {}, []
    for r in read_rooms(fid):
        rid = r['id'].upper()
        row = rows.get(rid)
        if not row or row[2] == 'hand' or (row[3] is not None and row[3] >= GOOD):
            continue
        poly = Polygon([to_sheet(x, y) for x, y in flatten(r['polygon'])]).buffer(0)
        if poly.is_empty:
            continue
        # open-plan areas, pods (a booth's walls are furniture-thick and its front open) and
        # rooms whose label stands outside them are drawn by their level polygon
        label_outside = rid in label_at and not poly.buffer(2).contains(label_at[rid])
        name = (r['extra'].get('name') or '').upper()
        if r['category'] in OPEN_CATEGORIES or 'BOOTH' in name or (r['extra'].get('tags') and 'open plan' in r['extra']['tags']) or label_outside:
            if rid not in patches['areas']:
                areas[rid] = [[round(x, 1), round(y, 1)] for x, y in poly.exterior.coords[:-1]]
            continue
        if row[2] != 'missing':
            continue  # traced but off: not a gap to seal; see the report
        # enclosed room that leaked: the edges of its polygon that run through free space
        n = len(poly.exterior.coords) - 1
        pts = list(poly.exterior.coords[:-1])
        for i in range(n):
            edge = LineString([pts[i], pts[(i + 1) % n]])
            gap = edge.difference(mass)
            for piece in (gap.geoms if hasattr(gap, 'geoms') else [gap]):
                if piece.length >= MIN_SEAL and piece.length < 0.6 * edge.length + 10:
                    (x0, y0), (x1, y1) = piece.coords[0], piece.coords[-1]
                    # reach 3 pt into the walls at both ends so the painted line meets them
                    ux, uy = (x1 - x0) / piece.length, (y1 - y0) / piece.length
                    x0, y0, x1, y1 = x0 - 3 * ux, y0 - 3 * uy, x1 + 3 * ux, y1 + 3 * uy
                    lines.append([round(x0, 1), round(y0, 1), round(x1, 1), round(y1, 1), f'{rid}: sealed from level{fid}.ts'])
    return areas, lines


def main(workdir, fid, write):
    areas, lines = propose(workdir, fid)
    print(f'floor {fid}: {len(areas)} area(s), {len(lines)} seal line(s) proposed')
    for rid in areas:
        print(f'  area {rid}')
    for ln in lines:
        print(f'  line {ln}')
    if not write:
        return
    path = path_for(fid)
    data = json.load(open(path)) if os.path.exists(path) else {'lines': [], 'areas': {}}
    data.setdefault('lines', []).extend(lines)
    data.setdefault('areas', {}).update(areas)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    json.dump(data, open(path, 'w'), indent=1)
    print('wrote', path)


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2], '--write' in sys.argv)
