"""Diff emitted level modules against the committed ones, room by room.

Usage: python3 difflevels.py <emitted dir> [floor id ...]

For each floor: rooms only in one file, category or name changes, and the overlap (IoU, in
frame coordinates) of every room present in both, with the ones below 0.8 listed. Both sets
of files must share a frame (emit into a directory holding a copy of the committed frame.ts).
"""
import json
import os
import sys

from shapely.geometry import Polygon

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'departments'))
import levels  # noqa: E402
from floors import FLOORS  # noqa: E402


def rooms_of(path):
    src = open(path).read()
    body = src.split('export const rooms: RoomSpec[] = [', 1)[1].split('\n];', 1)[0]
    out = {}
    for line in body.strip().splitlines():
        if line.strip().startswith('['):
            wing, rid, cat, poly, *extra = json.loads(levels._ts_to_json(line))
            ex = extra[0] if extra else {}
            out[rid] = (cat, ex.get('name'), poly, ex.get('holes', []))
    return out


def shape(entry):
    cat, name, poly, holes = entry
    return Polygon(levels.flatten(poly), [levels.flatten(h) for h in holes]).buffer(0)


def diff(emitted_dir, fid):
    old_path = os.path.join(levels.GATEWAY, f'level{fid}.ts')
    new_path = os.path.join(emitted_dir, f'level{fid}.ts')
    if not os.path.exists(new_path):
        print(f'floor {fid}: not emitted')
        return
    old, new = rooms_of(old_path), rooms_of(new_path)
    # unnumbered rooms are named by size order, so they are matched by overlap, not by id
    old_un = {k: shape(v) for k, v in old.items() if k.startswith('room-')}
    renamed = {}
    for k in [k for k in new if k.startswith('room-')]:
        g = shape(new[k])
        best = max(old_un.items(), key=lambda kv: g.intersection(kv[1]).area / (g.union(kv[1]).area or 1), default=None)
        if best is not None and g.intersection(best[1]).area > 0:
            renamed[k] = best[0]
            del old_un[best[0]]
    new = {renamed.get(k, k): v for k, v in new.items()}
    print(f'floor {fid}: {len(old)} rooms committed, {len(new)} emitted')
    gone, added = sorted(set(old) - set(new)), sorted(set(new) - set(old))
    if gone:
        print(f'  only committed: {", ".join(gone)}')
    if added:
        print(f'  only emitted:   {", ".join(added)}')
    for k in sorted(set(old) & set(new)):
        if old[k][0] != new[k][0] or old[k][1] != new[k][1]:
            print(f'  {k}: {old[k][0]} {old[k][1]!r} -> {new[k][0]} {new[k][1]!r}')
    ious = []
    for k in sorted(set(old) & set(new)):
        a, b = shape(old[k]), shape(new[k])
        if a.is_empty or b.is_empty:
            continue
        u = a.union(b).area
        ious.append((a.intersection(b).area / u if u else 0.0, k))
    ious.sort()
    print(f'  IoU >= 0.95: {sum(i >= 0.95 for i, _ in ious)}, >= 0.9: {sum(i >= 0.9 for i, _ in ious)}, >= 0.8: {sum(i >= 0.8 for i, _ in ious)} of {len(ious)}')
    for i, k in ious:
        if i < 0.8:
            print(f'    {k:16} {i:.3f}')


if __name__ == '__main__':
    for fid in sys.argv[2:] or FLOORS:
        diff(sys.argv[1], fid)
