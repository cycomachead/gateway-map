"""Seed a floor's patch file from the committed level file.

Usage: python3 bootstrap_patches.py <workdir> <floor id> [--write] [--emitted <dir>]

The level files hold the hand-corrected map. For every numbered room the tracer has no
polygon for (see compare.py), this proposes a patch:

- a room whose label sits in the corridor network (an open office, a piazza, a porch) gets
  its level polygon as an `areas` entry;
- an enclosed room that leaked gets `lines` for the parts of its level polygon's edges that
  cross free space (the doorway drawn without a swing, the gap at a glass front).

With --emitted, the named regions (restrooms, shafts, stairs, the terrace) whose emitted
polygon misses the committed one badly get the committed polygon as an area too.
Without --write the proposal is printed; with it, entries are merged into
patches/floor-<label>.json (existing entries are kept). Review the simplified drawing after
a run: a seeded line is only as good as the level polygon it came from.
"""
import json
import os
import re
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
NAMED_GOOD = 0.6  # a named region (a core) this close keeps its traced shape: the trace is often the better one


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
    traced = json.load(open(os.path.join(workdir, f"{cfg['pdf']}_rooms.json")))
    shared = {r['id'] for r in traced['rooms'] if r.get('shared')}
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
        # the level polygon in sheet points, arcs kept (a bulge survives a similarity)
        drawn = [[round(v, 1) for v in to_sheet(pt[0], pt[1])] + ([round(pt[2], 4)] if len(pt) > 2 and pt[2] else []) for pt in r['polygon']]
        # open-plan areas, pods (a booth's walls are furniture-thick and its front open) and
        # rooms whose label stands outside them are drawn by their level polygon
        label_outside = rid in label_at and not poly.buffer(2).contains(label_at[rid])
        name = (r['extra'].get('name') or '').upper()
        # ... and rooms the floor config lists as `quad` whose walls bow (the social kitchen)
        if r['category'] in OPEN_CATEGORIES or 'BOOTH' in name or (r['extra'].get('tags') and 'open plan' in r['extra']['tags']) or label_outside or rid in cfg['quad']:
            if rid not in patches['areas']:
                areas[rid] = drawn if (rid in cfg['quad'] or 'BOOTH' in name or label_outside) else [[round(x, 1), round(y, 1)] for x, y in poly.exterior.coords[:-1]]
            continue
        # an enclosed room that leaked, or shares its face with a neighbour: the edges of its
        # level polygon that run through free space are the gaps to seal. A room traced on
        # its own but shaped differently is not a gap (its swing area, a notch), so no line.
        if row[2] != 'missing' and rid not in shared:
            continue
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


def propose_named(emitted_dir, fid):
    """Areas for the named regions (restrooms, shafts, stairs, the terrace) whose emitted
    polygon misses the committed one badly: the committed polygon, in sheet points."""
    from difflevels import rooms_of, shape
    cfg = FLOORS[fid]
    number_re = re.compile(cfg['number_re'])
    old_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'src', 'data', 'gateway', f'level{fid}.ts')
    new_path = os.path.join(emitted_dir, f'level{fid}.ts')
    if not os.path.exists(new_path):
        return {}
    old, new = rooms_of(old_path), rooms_of(new_path)
    patches = load_patches(fid)
    to_sheet = frame_to_sheet(fid)
    areas = {}
    for rid, entry in old.items():
        if number_re.match(rid.upper()) or rid.startswith('room-') or rid in patches['areas']:
            continue
        a = shape(entry)
        score = 0.0
        if rid in new:
            b = shape(new[rid])
            u = a.union(b).area
            score = a.intersection(b).area / u if u else 0.0
        if score >= NAMED_GOOD:
            continue
        areas[rid] = [[round(v, 1) for v in to_sheet(pt[0], pt[1])] + ([round(pt[2], 4)] if len(pt) > 2 and pt[2] else []) for pt in entry[2]]
    return areas


def main(workdir, fid, write, emitted_dir=None):
    areas, lines = propose(workdir, fid)
    if emitted_dir:
        areas.update(propose_named(emitted_dir, fid))
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
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    emitted = sys.argv[sys.argv.index('--emitted') + 1] if '--emitted' in sys.argv else None
    main(args[0], args[1], '--write' in sys.argv, emitted)
