"""Parity of a traced floor against the committed level file.

Usage: python3 compare.py <workdir> <floor id> [--all]

Every numbered room of src/data/gateway/level<id>.ts is matched by id with the room in
<workdir>/<pdf>_rooms.json and their overlap (IoU) reported, in the sheet's coordinates.
Hand-drawn rooms (floors.py `hand`) are listed but not scored. This is the acceptance test
for every change to the tracer: a change may not lower the counts on any floor.
"""
import json
import math
import os
import re
import sys

from shapely.geometry import Polygon

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'departments'))
from floors import FLOORS  # noqa: E402
from levels import flatten, read_origin, read_rooms  # noqa: E402

THRESHOLDS = (0.95, 0.9, 0.8)


def frame_to_sheet(fid):
    """Frame coordinates back to the sheet's PDF points (the Lower Level through the inverse
    of its registration transform)."""
    ox, oy = read_origin()
    t = FLOORS[fid]['transform']
    if not t:
        return lambda x, y: (x + ox, y + oy)
    s, deg, dx, dy = t
    c, si = math.cos(math.radians(deg)), math.sin(math.radians(deg))

    def inv(x, y):
        X, Y = x + ox - dx, y + oy - dy
        return ((c * X + si * Y) / s, (-si * X + c * Y) / s)
    return inv


def report(workdir, fid, show_all=False):
    cfg = FLOORS[fid]
    traced = json.load(open(os.path.join(workdir, f"{cfg['pdf']}_rooms.json")))
    by_id = {r['id']: r for r in traced['rooms']}
    number_re = re.compile(cfg['number_re'])
    to_sheet = frame_to_sheet(fid)
    rows = []
    for r in read_rooms(fid):
        rid = r['id'].upper()
        if not number_re.match(rid) or rid in cfg['skip']:
            continue
        ref = Polygon([to_sheet(x, y) for x, y in flatten(r['polygon'])]).buffer(0)
        if rid in cfg['hand']:
            rows.append((rid, r['category'], 'hand', None))
            continue
        t = by_id.get(rid)
        if t is None:
            rows.append((rid, r['category'], 'missing', None))
            continue
        g = Polygon(t['polygon'], [h for h in t.get('holes', [])]).buffer(0)
        u = g.union(ref).area
        rows.append((rid, r['category'], t['kind'], g.intersection(ref).area / u if u else 0.0))
    scored = [x for x in rows if x[3] is not None]
    enclosed = [x for x in scored if x[1] != 'open']
    print(f"floor {fid}: {len(rows)} numbered rooms in level{fid}.ts: {len(scored)} traced, "
          f"{sum(x[2] == 'missing' for x in rows)} missing, {sum(x[2] == 'hand' for x in rows)} hand-drawn")
    for thr in THRESHOLDS:
        print(f"  IoU >= {thr}: {sum(x[3] >= thr for x in enclosed)} of {len(enclosed)} enclosed, {sum(x[3] >= thr for x in scored)} of {len(scored)} all")
    cats = {}
    for x in scored:
        cats.setdefault(x[1], []).append(x[3])
    for cat, v in sorted(cats.items()):
        v.sort()
        print(f"  {cat}: n={len(v)} median {v[len(v) // 2]:.2f} below 0.8: {sum(i < 0.8 for i in v)}")
    worst = sorted((x for x in rows if x[3] is None and x[2] == 'missing' or (x[3] is not None and x[3] < 0.8)), key=lambda x: (x[3] is not None, x[3] or 0))
    for x in (rows if show_all else worst):
        print(f"    {x[0]:7} {x[1]:10} {x[2]:8} {'' if x[3] is None else f'{x[3]:.3f}'}")
    return rows


if __name__ == '__main__':
    report(sys.argv[1], sys.argv[2], '--all' in sys.argv)
