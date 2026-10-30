"""Write src/data/gateway/level*.ts from the <floor>_rooms.json files.

Usage: python3 emit_ts.py <workdir> <src/data/gateway dir> [--reframe]

Every floor is mapped into one shared frame: the PDF point grid of the upper-floor sheets
(which are all drawn in the same position), shifted so the building starts near the origin.
The Lower Level sheet is drawn at another scale and rotation and is registered with the
similarity transform in floors.py.

The frame origin is recorded in frame.ts (`ORIGIN`) and kept on later runs while the building
still fits in it (`--reframe` recomputes it), so a single floor can be regenerated
(`gen.py ... 4`) into a workdir holding only that floor and still land in the shared frame,
and a full rerun does not shift every coordinate by a rounding point.
"""
import json
import math
import os
import re
import sys

from shapely.geometry import MultiPolygon, Point, Polygon

from floors import FLOORS, category, display_name, wing

PAD = 20.0
FRAME_SLACK = 6.0  # pt; an outline may stick this far into the padding before the frame is recomputed


def similarity(t):
    if not t:
        return lambda x, y: (x, y)
    s, deg, dx, dy = t
    c, si = math.cos(math.radians(deg)) * s, math.sin(math.radians(deg)) * s
    return lambda x, y: (c * x - si * y + dx, si * x + c * y + dy)


def load(workdir):
    data = {}
    for fid, cfg in FLOORS.items():
        path = os.path.join(workdir, f"{cfg['pdf']}_rooms.json")
        if not os.path.exists(path):
            print('missing', path)
            continue
        data[fid] = json.load(open(path))
    return data


def xy(poly):
    """The plain [x, y] vertices of a polygon whose points may carry a bulge."""
    return [[float(p[0]), float(p[1])] for p in poly]


def box_of(poly, axis=None):
    """Bounding rectangle of a polygon aligned with the walls drawn around it (`axis`, in
    degrees, from the tracer) or else with its longest edge (restrooms, elevators and stairs
    are boxes; a traced region full of fixtures may be blobby, but its longest edge is a wall)."""
    import numpy as np
    P = np.array(xy(poly), float)
    if axis is not None:
        ang = math.radians(axis)
    else:
        D = np.roll(P, -1, axis=0) - P
        d = D[np.argmax(np.linalg.norm(D, axis=1))]
        ang = np.arctan2(d[1], d[0])
    R = np.array([[np.cos(-ang), -np.sin(-ang)], [np.sin(-ang), np.cos(-ang)]])
    Q = P @ R.T
    x0, y0 = Q.min(0)
    x1, y1 = Q.max(0)
    box = np.array([[x0, y0], [x1, y0], [x1, y1], [x0, y1]]) @ R
    return [[float(x), float(y)] for x, y in box]


BOXED_TAGS = {'restroom', 'elevator', 'stairs'}
TURN_LIMIT = 15.0  # degrees; a hand-drawn box is turned onto the walls' direction when it is this close to it


def turned_to(poly, axis, limit=TURN_LIMIT):
    """A hand-drawn box turned about its centre so its walls run along `axis` (degrees), when
    it stands within `limit` of that already (a box seeded from a trace a few degrees off
    the walls). Arcs (bulges) are unchanged by a rotation."""
    import numpy as np
    P = np.array(xy(poly), float)
    D = np.roll(P, -1, axis=0) - P
    d = D[np.argmax(np.linalg.norm(D, axis=1))]
    have = math.degrees(math.atan2(d[1], d[0]))
    turn = (axis - have + 45) % 90 - 45
    if abs(turn) > limit or abs(turn) < 0.05:
        return poly
    c = P.mean(0)
    t = math.radians(turn)
    R = np.array([[math.cos(t), -math.sin(t)], [math.sin(t), math.cos(t)]])
    Q = (P - c) @ R.T + c
    return [[round(float(x), 1), round(float(y), 1)] + list(p[2:]) for (x, y), p in zip(Q, poly)]
# the pictogram the map draws above a room's label, by tag (restroom signs)
ICONS = {'men': 'man', 'women': 'woman', 'all gender': 'all-gender', 'stairs': 'stairs'}


def with_icon(extra):
    icon = next((ICONS[t] for t in extra.get('tags', []) if t in ICONS), None)
    return {**extra, 'icon': icon} if icon else extra


def ellipse_of(poly, n=48):
    """The ellipse fitted to a polygon, as arcs (a third value on a vertex is the bulge)."""
    import cv2
    import numpy as np
    from rooms import arcify, flatten_arcs
    (cx, cy), (w, h), ang = cv2.fitEllipse(np.array(flatten_arcs(poly), np.float32))
    t = np.radians(ang)
    a = np.linspace(0, 2 * np.pi, n, endpoint=False)
    u, v = w / 2 * np.cos(a), h / 2 * np.sin(a)
    pts = [[float(cx + x * np.cos(t) - y * np.sin(t)), float(cy + x * np.sin(t) + y * np.cos(t))] for x, y in zip(u, v)]
    return arcify(pts, tol=1.0)


def frame(data):
    xs, ys = [], []
    for fid, d in data.items():
        tf = similarity(FLOORS[fid]['transform'])
        for o in d['outlines']:
            for x, y in xy(o):
                X, Y = tf(x, y)
                xs.append(X)
                ys.append(Y)
    x0, y0 = min(xs) - PAD, min(ys) - PAD
    return x0, y0, max(xs) - x0 + PAD, max(ys) - y0 + PAD


def read_frame(path):
    """(x0, y0, width, height) from an existing frame.ts."""
    src = open(path).read()
    f = re.search(r'FRAME = \{ width: ([\d.]+), height: ([\d.]+) \}', src)
    o = re.search(r'ORIGIN = \{ x: ([\d.-]+), y: ([\d.-]+) \}', src)
    if not f or not o:
        raise SystemExit(f'{path} has no FRAME/ORIGIN; run with every floor present to define the frame')
    return float(o.group(1)), float(o.group(2)), float(f.group(1)), float(f.group(2))


def fmt_poly(poly):
    return '[' + ', '.join(f'[{p[0]:.1f}, {p[1]:.1f}]' if len(p) < 3 or not p[2] else f'[{p[0]:.1f}, {p[1]:.1f}, {p[2]:.4f}]' for p in poly) + ']'


def ts_str(s):
    return "'" + s.replace('\\', '\\\\').replace("'", "\\'").replace('\n', '\\n') + "'"


def emit_floor(fid, d, x0, y0, out_dir):
    cfg = FLOORS[fid]
    tf = similarity(cfg['transform'])
    to_frame = lambda poly: [(lambda q, rest: (q[0] - x0, q[1] - y0, *rest))(tf(p[0], p[1]), p[2:]) for p in poly]
    lines = []
    lines.append(f"// GENERATED by tools/trace_cad/emit_ts.py from the CAD plan '{cfg['source']}' — do not edit by hand.")
    lines.append('// Coordinates are the shared floor frame (PDF points of the upper-floor sheets, origin shifted; see tools/trace_cad/README.md).')
    lines.append("import type { DoorSpec, PoiSpec, RoomSpec } from './floor';")
    lines.append("import type { XY } from '../helpers';")
    lines.append('')
    outlines = [to_frame(o) for o in d['outlines']]
    lines.append(f'export const outline: XY[] = {fmt_poly(outlines[0])};')
    lines.append('export const islands: XY[][] = [' + ', '.join(fmt_poly(o) for o in outlines[1:]) + '];')
    lines.append('')
    lines.append('/** Desks in the open workspaces (worksurface outlines), drawn for orientation only. */')
    lines.append('export const desks: XY[][] = [' + ', '.join(fmt_poly(to_frame(dsk)) for dsk in d.get('desks', [])) + '];')
    def door_ts(dr):
        flags = ['leaves: 2'] if dr.get('leaves', 1) == 2 else []
        if dr.get('show'):
            flags.append('show: true')
        if dr.get('name'):
            flags.append(f"name: {ts_str(dr['name'])}")
        return '[' + fmt_poly(to_frame([dr['a'], dr['b'], dr['o']]))[1:-1] + (', { ' + ', '.join(flags) + ' }' if flags else '') + ']'
    doors_at = len(lines)  # written once the rooms are final: a marker may sit on a room's edge
    lines.append('')
    lines.append('')
    lines.append('export const rooms: RoomSpec[] = [')
    entries = []  # (priority, wing, id, category, polygon, extra); lower priority keeps its shape
    seen = {}
    for r in sorted(d['rooms'], key=lambda r: (r['kind'] != 'room', r['id'])):
        if r['id'] in cfg['skip'] or not r.get('polygon'):
            continue
        if category(r['name'], r['id']) == 'circulation':
            continue  # corridors and lobbies (xCORRxx, x000 PIAZZA CIRCULATION) are not drawn as rooms
        rid = r['id']
        seen[rid] = seen.get(rid, 0) + 1
        if seen[rid] > 1:
            rid = f"{rid}-{seen[rid]}"
        if r['id'] in cfg['rename']:  # a room whose use differs from the plan's label
            r = {**r, 'name': cfg['rename'][r['id']]}
        cat = category(r['name'], r['id'])
        name = display_name(r['name'], r['id']) if r['id'] != 'terrace' else 'Roof Terrace'
        w = wing(r['id'])
        extra = {'name': name, 'label': r['id'] if r['id'] != 'terrace' else 'Terrace'}
        if r.get('holes'):
            extra['holes'] = r['holes']
        tags = [t for t in r['name'].lower().replace('/', ' ').split() if len(t) > 2 and t not in {'the', 'and'}]
        if r['kind'] == 'open':
            tags.append('open plan')
        if tags:
            extra['tags'] = tags
        entries.append((0 if r['kind'] == 'room' else 2, w, rid, cat, r['polygon'], extra))
    from shapely.geometry import MultiPolygon, Polygon
    placed = [Polygon(xy(r['polygon']), [xy(h) for h in r.get('holes', [])]).buffer(0) for r in d['rooms'] if r.get('polygon')]
    resolved = []
    # the elevator banks are drawn from their shafts' X marks, by seed, whatever the regions
    banks = {}
    for px, py, uid, cat, name, label, tags in cfg['named']:
        m = re.fullmatch(r'(\w+)-elevator-\d+', uid)
        if m and not isinstance(px, list):
            banks.setdefault(m.group(1), []).append((uid, (px, py)))
    cells = {}
    for prefix, seeds in banks.items():
        cells.update(bank_cells(seeds, d.get('shafts', [])) or {})
    if cells:
        print(f'  floor {fid}: {len(cells)} elevators drawn from their shafts\' X marks')
    for px, py, uid, cat, name, label, tags in cfg['named']:
        points = px if isinstance(px, list) else [(px, py)]
        regions = []
        for qx, qy in points:
            u = region_at(d['unlabelled'], qx, qy)
            if u is not None and all(u is not r for r in regions):
                regions.append(u)
        if not regions and uid not in cells:
            print(f'  floor {fid}: no unlabelled region at {points} for {uid}')
            continue
        resolved.append((uid, cat, name, label, tags, points, regions))
    # Several named entries may resolve to one region (three elevator shafts whose X marks
    # merge into a single cluster): split that region between them by nearest point.
    bank_regions = set()
    for uid, cat, name, label, tags, points, regions in resolved:
        if uid in cells:
            poly = cells[uid]
            placed.append(Polygon(xy(poly)).buffer(0))
            # the whole traced bank is taken too: a bigger shaft reaches behind the cells
            for r in regions:
                if id(r) not in bank_regions and r['area'] <= 4 * Polygon(xy(poly)).area * len(cells):
                    bank_regions.add(id(r))
                    placed.append(Polygon(xy(r['polygon'])).buffer(0))
            entries.append((1, cfg['wings'].get(uid) or wing(uid) or ('Northeast' if uid.startswith('ne-') else 'Southwest' if uid.startswith('sw-') else None),
                            uid, cat, poly, with_icon({'name': name, 'label': label, 'tags': tags})))
            continue
        sharers = [o for o in resolved if len(o[6]) == 1 and len(regions) == 1 and o[6][0] is regions[0]]
        axis = regions[0].get('axis')  # the walls' direction around the region, from the tracer
        if len(sharers) > 1:
            parts = split_shared(regions[0]['polygon'], [o[5][0] for o in sharers], d['outlines'], axis, d.get('shafts', []))
            poly = parts[[o[0] for o in sharers].index(uid)]
        else:
            poly = regions[0]['polygon'] if len(regions) == 1 else union_polys([r['polygon'] for r in regions])
        drawn = len(regions) == 1 and regions[0].get('named') == uid
        if drawn:  # a patch area drawn for this region: as given, a box squared to the walls
            if BOXED_TAGS & set(tags) and axis is not None:
                poly = turned_to(poly, axis)
        elif {'atrium', 'oval'} & set(tags):  # an oval room (the atrium, the event space): a clean ellipse through its traced outline
            poly = ellipse_of(poly)
        else:
            if BOXED_TAGS & set(tags):
                poly = box_of(poly, axis)
            # a box (or a region traced into a doorway) may reach into a neighbour: trim it
            g = Polygon(xy(poly)).buffer(0)
            trimmed = False
            for other in placed:
                if g.intersects(other) and g.intersection(other).area > 2:
                    g = g.difference(other)
                    trimmed = True
                    if isinstance(g, MultiPolygon):
                        g = max(g.geoms, key=lambda q: q.area)
            if trimmed or BOXED_TAGS & set(tags):
                poly = [[float(x), float(y)] for x, y in g.simplify(0.3).exterior.coords[:-1]]
        placed.append(Polygon(xy(poly)).buffer(0))
        extra = with_icon({'name': name, 'label': label, 'tags': tags})
        w = cfg['wings'].get(uid) or wing(uid) or ('Northeast' if uid.startswith('ne-') else 'Southwest' if uid.startswith('sw-') else None)
        entries.append((1, w, uid, cat, poly, extra))
    for uid, cat, name, label, tags, poly in cfg['manual']:
        extra = with_icon({'name': name, 'label': label, 'tags': tags})
        w = cfg['wings'].get(uid) or wing(uid)
        poly = clip_to(poly, d['outlines'])
        if uid not in cfg['suites']:  # a suite is drawn around rooms, so it takes no space from them
            placed.append(Polygon(xy(poly)).buffer(0))
        entries.append((1, w, uid, cat, poly, extra))
    moved = align_cores(entries)
    if moved:
        print(f'  floor {fid}: {moved} core walls put in line with their neighbours')
    if cfg['unnamed']:
        # Floors whose plan numbers only the furnished rooms (Lower Level, 1, 5): every other
        # enclosed room of room size is drawn too, unnamed, so the floor is not a blank slab.
        # Pockets inside a placed room (a table, a bench block) and slivers are left out.
        from shapely.ops import unary_union
        taken = unary_union(placed) if placed else Polygon()
        from rooms import flatten_arcs
        inside = unary_union([Polygon(flatten_arcs(o)).buffer(0) for o in d['outlines']])
        used = {id(r) for o in resolved for r in o[6]}
        # closets the floor config leaves off the map
        used |= {id(u) for u in (region_at(d['unlabelled'], bx, by) for bx, by in cfg['blank']) if u is not None}
        k = 0
        for u in sorted(d['unlabelled'], key=lambda u: -u['area']):
            if id(u) in used or u.get('atrium') or not cfg['unnamed'] <= u['area'] <= cfg['unnamed_max']:
                continue
            g = Polygon(xy(u['polygon'])).buffer(0)
            if g.is_empty or not inside.contains(g.representative_point()) or g.intersection(taken).area > 0.3 * g.area:
                continue
            # a long thin strip is a wall cavity or a planting bed along a facade, not a room
            import cv2
            import numpy as np
            (_, _), (rw, rh), _ = cv2.minAreaRect(np.array(xy(u['polygon']), np.float32))
            if min(rw, rh) < 20 or max(rw, rh) > 6 * min(rw, rh):
                continue
            # and a region that fills little of its bounding rectangle is a corridor or a
            # leftover between rooms, not a room
            if g.area < 0.5 * rw * rh and not any(g.contains(Point(*p)) for p in cfg['square']):
                continue
            # a pocket inside a larger unnamed room (its tables) is part of that room
            if any(o.contains(g.representative_point()) for o in placed):
                continue
            # most rooms have four walls: a region that nearly fills its bounding rectangle is
            # drawn as that rectangle (the notches are fixtures and door recesses); a round
            # room (the oval on the roof) as the ellipse through its outline; any other gets
            # the simplest corner fit that still covers it
            from rooms import flatten_arcs
            ell = ellipse_of(u['polygon']) if len(u['polygon']) >= 8 else None
            e = Polygon(flatten_arcs(ell)).buffer(0) if ell else None
            iou_ell = e.intersection(g).area / e.union(g).area if e is not None and not e.is_empty else 0.0
            if iou_ell >= 0.92:
                poly = ell
            elif iou_ell > g.area / (rw * rh):
                poly = u['polygon']  # round but not an ellipse (the oval with its flat side): the traced curve
            elif g.area >= 0.75 * rw * rh or any(g.contains(Point(*p)) for p in cfg['square']):  # a plain box, or one the floor asks for
                poly = [[float(x), float(y)] for x, y in cv2.boxPoints(cv2.minAreaRect(np.array(xy(u['polygon']), np.float32)))]
            else:
                poly = tidy_room(u['polygon'])
            g = Polygon(flatten_arcs(poly)).buffer(0)
            if g.difference(inside).area > 2:
                g = g.intersection(inside)
                if isinstance(g, MultiPolygon):
                    g = max(g.geoms, key=lambda q: q.area)
                poly = [[float(x), float(y)] for x, y in g.simplify(0.3).exterior.coords[:-1]]
            if g.intersects(taken) and g.intersection(taken).area > 2:
                g = g.difference(taken)
                if isinstance(g, MultiPolygon):
                    g = max(g.geoms, key=lambda q: q.area)
                poly = [[float(x), float(y)] for x, y in g.simplify(0.3).exterior.coords[:-1]]
            k += 1
            placed.append(g)
            taken = taken.union(g)
            entries.append((3, None, f'room-{k}', 'service', poly, {'name': 'Room', 'label': '', 'tags': ['unnumbered']}))
        print(f'  floor {fid}: {k} unnumbered rooms')
    n_walls, n_rooms, worst = align_walls(entries, d['outlines'])
    print(f'  floor {fid}: {n_walls} walls of {n_rooms} rooms turned parallel to their neighbours (largest turn {worst:.1f}°)')
    suited = mark_suites(entries, cfg)
    if suited:
        print(f'  floor {fid}: {suited} rooms inside a suite take its name')
    cut = resolve_overlaps(entries)
    print(f'  floor {fid}: {cut} overlaps cut')
    clipped = clip_entries(entries, d['outlines'])
    if clipped:
        print(f'  floor {fid}: {clipped} rooms clipped to the outline')
    print(f'  floor {fid}: {inset_entries(entries)} rooms pulled in by {INSET:g} pt')
    doors = d.get('doors', [])
    snapped = snap_doors(doors, entries)
    if snapped:
        print(f"  floor {fid}: {snapped} door markers moved onto a room's edge")
    lines[doors_at] = 'export const doors: DoorSpec[] = [' + ', '.join(door_ts(dr) for dr in doors) + '];'
    for _, w, rid, cat, poly, extra in entries:
        if extra.get('holes'):
            extra = {**extra, 'holes': [to_frame(h) for h in extra['holes']]}
        lines.append(f"  [{ts_str(w) if w else 'undefined'}, {ts_str(rid)}, {ts_str(cat)}, {fmt_poly(to_frame(poly))}, {fmt_extra(extra)}],")
    lines.append('];')
    lines.append('')
    lines.append('export const pois: PoiSpec[] = [')
    for i, (ex, ey) in enumerate(d.get('exits', []), 1):
        X, Y = tf(ex, ey)
        lines.append(f"  ['entrance-{i}', 'Entrance {i}', 'exit', [{X - x0:.1f}, {Y - y0:.1f}]],")
    for pid, name, kind, (px, py), *desc in cfg['pois']:
        X, Y = tf(px, py)
        lines.append(f"  [{ts_str(pid)}, {ts_str(name)}, {ts_str(kind)}, [{X - x0:.1f}, {Y - y0:.1f}]{', ' + ts_str(desc[0]) if desc else ''}],")
    lines.append('];')
    lines.append('')
    open(os.path.join(out_dir, f'level{fid}.ts'), 'w').write('\n'.join(lines))
    print(f'level{fid}.ts: {len(d["rooms"])} rooms + {len(cfg["named"])} named regions, {len(d.get("desks", []))} desks, {len(d.get("doors", []))} doors')


def tidy_room(poly):
    """A cleaner shape for an unnumbered room traced around its fixtures: the region is
    rounded (a 9 px close then open drops sinks, benches and door recesses) and fitted with the
    simplest polygon of 4 to 8 line-fitted walls that still covers it, or failing that with
    line-fitted straight runs."""
    import cv2
    import numpy as np
    from rooms import EPS, _prep, straight_runs, straighten
    pts = np.array(xy(poly), np.float32)
    x0, y0 = np.floor(pts.min(0)).astype(int) - 8
    x1, y1 = np.ceil(pts.max(0)).astype(int) + 8
    m = np.zeros((y1 - y0, x1 - x0), np.uint8)
    cv2.fillPoly(m, [np.round(pts - [x0, y0]).astype(np.int32)], 255)
    m = _prep(m, 0, 9)
    fit = straighten(m, ns=(4, 5, 6, 8), min_iou=0.85, max_shift=30, max_dev=None) or straight_runs(m, EPS, eps_coarse=10, min_len=30)
    if not fit or len(fit) < 3:
        return poly
    return [[round(float(x) + x0, 1), round(float(y) + y0, 1)] for x, y in fit]


ALIGN_ANGLE = 6.0    # degrees; walls further apart in angle are genuinely different walls
ALIGN_DIST = 8.0     # px; perpendicular offset between the two faces of a partition (plus fitting noise)
ALIGN_DIST_OUT = 14.0  # px; a room's exterior wall sits a wall thickness (10 px) inside the outline
ALIGN_GAP = 25.0     # px; collinear walls this far apart along their line (a doorway) still share it
ALIGN_MIN = 12.0     # px; shorter edges are curve pieces or notches, not walls
ALIGN_SHIFT = 6.0    # px; a corner may move this far when its walls are turned


def align_walls(entries, outlines):
    """Walls of neighbouring rooms that are nearly parallel are made exactly parallel. Rooms are
    fitted one by one, so the two faces of a shared partition (or the exterior walls of a row of
    offices along a facade) come out a degree or two apart and the gap between them is a wedge.
    Straight edges of different polygons that run within `ALIGN_ANGLE` of each other, lie within
    `ALIGN_DIST` of each other's line and overlap along it (or stop within `ALIGN_GAP`, a
    doorway) are grouped; each group is turned about the midpoints of its edges to one angle,
    the length-weighted mean of its edges' tilts (the plain midpoint for two walls of a kind).
    The outline is a fixed reference: a group containing a facade takes the facade's angle.
    Corners are rebuilt as the intersections of the turned walls (a corner next to an arc or a
    near-collinear jog is projected onto the turned wall instead). Holes are left alone.
    Returns (edges turned, polygons touched, largest turn in degrees)."""
    import numpy as np
    from rooms import _intersect
    polys = [[list(p) for p in e[4]] for e in entries]
    owner, idx, A, B, fixed = [], [], [], [], []

    def collect(poly, k, fix):
        n = len(poly)
        for i in range(n):
            p, q = poly[i], poly[(i + 1) % n]
            if len(p) == 3 and p[2]:
                continue
            a, b = np.array(p[:2], float), np.array(q[:2], float)
            if np.linalg.norm(b - a) < ALIGN_MIN:
                continue
            owner.append(k)
            idx.append(i)
            A.append(a)
            B.append(b)
            fixed.append(fix)
    for k, poly in enumerate(polys):
        collect(poly, k, False)
    for j, o in enumerate(outlines):
        collect(o, -1 - j, True)
    if len(A) < 2:
        return 0, 0, 0.0
    owner, idx, fixed = np.array(owner), np.array(idx), np.array(fixed, bool)
    A, B = np.array(A), np.array(B)
    M, D = (A + B) / 2, B - A
    L = np.linalg.norm(D, axis=1)
    U = D / L[:, None]
    N = np.column_stack([-U[:, 1], U[:, 0]])
    ang = np.degrees(np.arctan2(U[:, 1], U[:, 0])) % 180.0
    dang = np.abs(ang[:, None] - ang[None, :])
    dang = np.minimum(dang, 180.0 - dang)
    rel = M[None, :, :] - M[:, None, :]                      # from edge i's midpoint to edge j's
    perp = np.abs((rel * N[:, None, :]).sum(-1))             # distance of j's midpoint from i's line
    perp = np.maximum(perp, perp.T)
    ta = ((A[None, :, :] - M[:, None, :]) * U[:, None, :]).sum(-1)   # j's ends along i's line
    tb = ((B[None, :, :] - M[:, None, :]) * U[:, None, :]).sum(-1)
    lo, hi = np.minimum(ta, tb), np.maximum(ta, tb)
    gap = np.maximum(lo - L[:, None] / 2, -L[:, None] / 2 - hi)  # along-line gap (negative = overlap)
    gap = np.maximum(gap, gap.T)
    dist_tol = np.where(fixed[:, None] | fixed[None, :], ALIGN_DIST_OUT, ALIGN_DIST)
    pair = (dang <= ALIGN_ANGLE) & (perp <= dist_tol) & (gap <= ALIGN_GAP)
    pair &= owner[:, None] != owner[None, :]
    pair &= ~(fixed[:, None] & fixed[None, :])
    # groups of mutually aligned edges (union-find over the pairs)
    parent = list(range(len(A)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    for i, j in zip(*np.nonzero(np.triu(pair, 1))):
        ri, rj = find(int(i)), find(int(j))
        if ri != rj:
            parent[ri] = rj
    groups = {}
    for e in range(len(A)):
        groups.setdefault(find(e), []).append(e)
    turned = {}  # (polygon, edge index) -> new unit direction
    worst = 0.0
    for members in groups.values():
        if len(members) < 2:
            continue
        m = np.array(members)
        ref = m[fixed[m]] if fixed[m].any() else m
        # the mean of angles that repeat every 180°: average the doubled angles as vectors
        th = np.radians(2 * ang[ref])
        mean = np.degrees(np.arctan2((L[ref] * np.sin(th)).sum(), (L[ref] * np.cos(th)).sum())) / 2 % 180.0
        for e in m[~fixed[m]]:
            d = (ang[e] - mean + 90) % 180 - 90
            if abs(d) < 0.05 or abs(d) > ALIGN_ANGLE:  # already there, or a chain drifted too far
                continue
            worst = max(worst, abs(d))
            t = np.radians(mean)
            u = np.array([np.cos(t), np.sin(t)])
            turned[(int(owner[e]), int(idx[e]))] = u if np.dot(u, U[e]) >= 0 else -u
    touched = set()
    for (k, i), u in turned.items():
        touched.add(k)
    for k in touched:
        poly = polys[k]
        n = len(poly)
        lines = []
        for i in range(n):
            p, q = poly[i], poly[(i + 1) % n]
            if len(p) == 3 and p[2]:
                lines.append(None)
                continue
            a, b = np.array(p[:2], float), np.array(q[:2], float)
            d = b - a
            if np.linalg.norm(d) < 1e-9:
                lines.append(None)
                continue
            lines.append(((a + b) / 2, turned.get((k, i), d / np.linalg.norm(d))))
        new = [list(p) for p in poly]
        for i in range(n):
            e0, e1 = (i - 1) % n, i
            if (k, e0) not in turned and (k, e1) not in turned:
                continue
            v = np.array(poly[i][:2], float)
            q = None
            if lines[e0] is not None and lines[e1] is not None:
                q = _intersect(lines[e0], lines[e1])
                if q is not None and np.linalg.norm(q - v) > ALIGN_SHIFT:
                    q = None
            if q is None:  # next to an arc or a near-collinear jog: project onto the turned wall(s)
                projs = []
                for e in (e0, e1):
                    if (k, e) in turned and lines[e] is not None:
                        p0, u = lines[e]
                        projs.append(p0 + u * np.dot(v - p0, u))
                q = np.mean(projs, axis=0)
            new[i][0], new[i][1] = round(float(q[0]), 1), round(float(q[1]), 1)
        polys[k] = new
        prio, w, rid, cat, _, extra = entries[k]
        entries[k] = (prio, w, rid, cat, new, extra)
    return len(turned), len(touched), worst


def clip_to(poly, outlines):
    """Intersection of a hand polygon with the floor outline(s), via a 1 px/pt raster."""
    import cv2
    import numpy as np
    pts = np.array(xy(poly), np.float32)
    x0, y0 = np.floor(pts.min(0)).astype(int) - 2
    x1, y1 = np.ceil(pts.max(0)).astype(int) + 2
    a = np.zeros((y1 - y0, x1 - x0), np.uint8)
    b = np.zeros_like(a)
    cv2.fillPoly(a, [np.round(pts - [x0, y0]).astype(np.int32)], 255)
    for o in outlines:
        cv2.fillPoly(b, [np.round(np.array(xy(o)) - [x0, y0]).astype(np.int32)], 255)
    cs, _ = cv2.findContours(a & b, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not cs:
        return poly
    c = cv2.approxPolyDP(max(cs, key=cv2.contourArea), 1.5, True).reshape(-1, 2) + [x0, y0]
    return [[float(x), float(y)] for x, y in c]


def min_area_rect(points):
    """(centre, unit vector along the long side, length, width) of the smallest rectangle
    around the points, trying every edge direction of their hull (no OpenCV needed)."""
    import numpy as np
    P = np.array(points, float)
    best = None
    for i in range(len(P)):
        d = P[(i + 1) % len(P)] - P[i]
        n = np.linalg.norm(d)
        if n < 1e-6:
            continue
        u = d / n
        v = np.array([-u[1], u[0]])
        a, b = P @ u, P @ v
        L, W = a.max() - a.min(), b.max() - b.min()
        if best is None or L * W < best[0]:
            c = u * (a.max() + a.min()) / 2 + v * (b.max() + b.min()) / 2
            best = (L * W, c, u, L, W) if L >= W else (L * W, c, v, W, L)
    _, c, u, L, W = best
    return c, u, L, W


def facade_direction(outlines, at, min_len=100.0):
    """Unit vector along the straight edge of the building outline nearest to a point: an edge
    of at least `min_len` (the chords of a flattened curve and the jogs are shorter)."""
    import numpy as np
    from rooms import flatten_arcs
    best = None
    p = np.array(at, float)
    for o in outlines:
        pts = np.array(flatten_arcs(o), float)
        for i in range(len(pts)):
            a, b = pts[i], pts[(i + 1) % len(pts)]
            d = b - a
            L = np.linalg.norm(d)
            if L < min_len:
                continue
            t = np.clip(np.dot(p - a, d) / (L * L), 0.0, 1.0)
            dist = np.linalg.norm(a + t * d - p)
            if best is None or dist < best[0]:
                best = (dist, d / L)
    return None if best is None else best[1]


BANK_REACH = 45.0  # pt; a shaft's X mark this close to an elevator's seed point is that shaft


def bank_cells(seeds, shafts):
    """The cells of an elevator bank from its shafts' X marks: one per seed, the pitch of the
    marks wide (a shaft and the wall beside it), as deep as the marks, side by side along the
    bank. A seed without a mark (the biggest shaft of a bank carries no plain X) gets the cell
    at that pitch beyond its neighbours. None when fewer than two marks are found."""
    import numpy as np
    S = [np.array(p, float) for _, p in seeds]
    boxes = [np.array(b, float) for b in shafts]
    found = {}
    for i, s in enumerate(S):
        near = sorted((np.linalg.norm(b.mean(0) - s), j) for j, b in enumerate(boxes))
        for dist, j in near:
            if dist > BANK_REACH:
                break
            if j not in found.values():
                found[i] = j
                break
    if len(found) < 2:
        return None
    cs = {i: boxes[j].mean(0) for i, j in found.items()}
    (a, b) = max(((p, q) for p in cs.values() for q in cs.values()), key=lambda t: np.linalg.norm(t[1] - t[0]))
    u = (b - a) / np.linalg.norm(b - a)
    first = boxes[next(iter(found.values()))]
    sides = [first[(k + 1) % 4] - first[k] for k in range(4)]
    e = max(sides, key=lambda e: abs((e / np.linalg.norm(e)) @ u))
    u = e / np.linalg.norm(e) * (1 if e @ u >= 0 else -1)
    v = np.array([-u[1], u[0]])
    cu = sorted(c @ u for c in cs.values())
    pitch = min(q - p for p, q in zip(cu, cu[1:]))
    mv = np.concatenate([boxes[j] for j in found.values()]) @ v
    depth = (mv.min(), mv.max())
    cells = {}
    for i, (uid, _) in enumerate(seeds):
        c = cs[i] @ u if i in found else cu[0] + round((S[i] @ u - cu[0]) / pitch) * pitch
        cells[uid] = [[round(float(x), 1), round(float(y), 1)] for x, y in
                      (u * uu + v * vv for uu, vv in ((c - pitch / 2, depth[0]), (c + pitch / 2, depth[0]), (c + pitch / 2, depth[1]), (c - pitch / 2, depth[1])))]
    return cells


def split_shared(poly, points, outlines=(), axis=None, shafts=()):
    """Split a polygon between seed points: the regions that share one polygon are the
    shafts of an elevator bank, so the bank is drawn as equal boxes side by side along the
    bank's axis (the n-th of the bank's length), one per seed, in the seeds' order along
    that axis. The boxes are as deep as the shafts' X marks (`shafts`, from the tracer: the
    biggest shaft of a bank is drawn like the others, so nothing reaches behind the small
    ones into the next room); without X marks they are squares. The axis is the X marks'
    (the direction from shaft to shaft), else the shaft walls' (`axis`, from the tracer),
    else that of the nearest straight facade, else the region's long axis."""
    import numpy as np
    P = np.array(xy(poly), float)
    S = np.array(points, float)
    region = Polygon(xy(poly)).buffer(10)
    marks = [np.array(b, float) for b in shafts if region.contains(Polygon(b).centroid)]
    u = depth = None
    if marks:
        cs = [b.mean(0) for b in marks]
        if len(cs) > 1:
            u = cs[-1] - cs[0]
        else:  # one mark: its long side runs along the bank
            u = max((marks[0][(k + 1) % 4] - marks[0][k] for k in range(4)), key=lambda e: np.linalg.norm(e))
        u = u / np.linalg.norm(u)
        # snap to the mark's own side direction
        sides = [marks[0][(k + 1) % 4] - marks[0][k] for k in range(4)]
        e = max(sides, key=lambda e: abs((e / np.linalg.norm(e)) @ u))
        u = e / np.linalg.norm(e) * (1 if e @ u >= 0 else -1)
        v = np.array([-u[1], u[0]])
        mv = np.concatenate(marks) @ v
        depth = (mv.min(), mv.max())
    elif axis is not None:
        u = np.array([math.cos(math.radians(axis)), math.sin(math.radians(axis))])
    else:
        u = facade_direction(outlines, P.mean(0)) if outlines else None
    if u is None:
        c, u, L, _ = min_area_rect(xy(poly))
        v = np.array([-u[1], u[0]])
        b = P @ v
        depth = (c @ v - L / len(points) / 2, c @ v + L / len(points) / 2)
    else:
        v = np.array([-u[1], u[0]])
        if depth is None and len(S) > 1 and np.ptp(S @ v) > np.ptp(S @ u):  # the seeds spread across the facade: the bank stands end-on
            u, v = v, -u
        a, b = P @ u, P @ v
        L = a.max() - a.min()
        c = u * (a.max() + a.min()) / 2 + v * (b.max() + b.min()) / 2
        if depth is None:  # squares
            depth = (c @ v - L / len(points) / 2, c @ v + L / len(points) / 2)
    n = len(points)
    side = L / n
    along = (S - c) @ u
    cells = {}
    for rank, i in enumerate(np.argsort(along)):
        u0 = c @ u + (rank - n / 2) * side
        cells[int(i)] = [[round(float(x), 1), round(float(y), 1)] for x, y in
                         (u * uu + v * vv for uu, vv in ((u0, depth[0]), (u0 + side, depth[0]), (u0 + side, depth[1]), (u0, depth[1])))]
    return [cells[i] for i in range(n)]

CORE_ALIGN = 30.0  # pt; a stair's wall within this of its elevator bank's is put on one line (the X marks the cab; the hoistway's back wall is the stair's)
CORE_GAP = 50.0    # pt; a stair this close to the bank along it stands beside it
OVERLAP_MIN = 0.5  # pt²; smaller overlaps are rounding


def align_cores(entries):
    """An elevator bank and the stair beside it share their back wall: where an edge of the
    stair parallel to the bank lies within CORE_ALIGN of the bank's edge, the one that falls
    short is brought out to the other (the thick wall behind the shafts is drawn as part of
    them). Returns the number of polygons moved."""
    import numpy as np
    by_id = {e[2]: i for i, e in enumerate(entries)}
    banks = {}
    for i, e in enumerate(entries):
        m = re.fullmatch(r'(\w+)-elevator-\d+', e[2])
        if m and len(e[4]) == 4:
            banks.setdefault(m.group(1), []).append(i)
    moved = 0

    def replace(i, poly):
        entries[i] = entries[i][:4] + ([[round(float(x), 1), round(float(y), 1)] for x, y in poly],) + entries[i][5:]

    for prefix, idxs in banks.items():
        j = by_id.get(f'{prefix}-stair')
        if j is None or len(entries[j][4]) != 4 or any(len(p) > 2 and p[2] for p in entries[j][4]):
            continue
        boxes = [np.array(xy(entries[i][4]), float) for i in idxs]
        cs = [b.mean(0) for b in boxes]
        u = cs[-1] - cs[0] if len(cs) > 1 else max((boxes[0][(k + 1) % 4] - boxes[0][k] for k in range(4)), key=lambda e: np.linalg.norm(e))
        u = u / np.linalg.norm(u)
        v = np.array([-u[1], u[0]])
        stair = np.array(xy(entries[j][4]), float)
        bank = np.concatenate(boxes)
        if (stair @ u).min() > (bank @ u).max() + CORE_GAP or (stair @ u).max() < (bank @ u).min() - CORE_GAP:
            continue  # not beside the bank
        for k in range(4):
            a, b = stair[k], stair[(k + 1) % 4]
            e = (b - a) / np.linalg.norm(b - a)
            if abs(e @ u) < math.cos(math.radians(3)):
                continue  # not parallel to the bank
            ev = ((a + b) / 2) @ v
            bv = bank @ v
            for sign, edge in ((-1, bv.min()), (1, bv.max())):
                d = (ev - edge) * sign  # > 0: the stair's edge lies beyond the bank's
                if abs(d) > CORE_ALIGN or abs(d) < 0.2:
                    continue
                if d > 0:  # the bank comes out to the stair
                    for i in idxs:
                        poly = np.array(xy(entries[i][4]), float)
                        mask = np.isclose(poly @ v, edge, atol=0.5)
                        poly[mask] += v * (ev - edge)
                        replace(i, poly)
                    bank = np.concatenate([np.array(xy(entries[i][4]), float) for i in idxs])
                else:  # the stair comes out to the bank
                    mask = np.isclose(stair @ v, ev, atol=0.5)
                    stair[mask] += v * (edge - ev)
                    replace(j, stair)
                moved += 1
    return moved


def shrink_wall(quad, other):
    """A four-walled polygon pulled off a neighbour it overlaps: the wall the overlap lies
    along moves inward just past it and the corners are rebuilt, so the room stays four
    walls instead of getting a notch. None when a wall shift does not clear the overlap or
    would cost more than a tenth of the room."""
    import numpy as np
    from shapely.geometry import Polygon
    Q = np.array(xy(quad), float)
    g = Polygon(Q).buffer(0)
    x = g.intersection(other)
    if x.is_empty:
        return g
    pts = np.array(x.exterior.coords if x.geom_type == 'Polygon' else [c for p in getattr(x, 'geoms', []) if p.geom_type == 'Polygon' for c in p.exterior.coords], float)
    if len(pts) < 3:
        return None
    ccw = 1 if np.cross(Q[1] - Q[0], Q[2] - Q[1]) > 0 else -1
    best = None
    for i in range(4):
        a, b = Q[i], Q[(i + 1) % 4]
        e = (b - a) / np.linalg.norm(b - a)
        n = np.array([-e[1], e[0]]) * ccw  # inward normal
        depth = ((pts - a) @ n).max()      # how far the overlap reaches in from this wall
        if best is None or depth < best[0]:
            best = (depth, i)
    depth, i = best
    if depth <= 0 or depth > 40:
        return None
    a, b = Q[i], Q[(i + 1) % 4]
    e = (b - a) / np.linalg.norm(b - a)
    n = np.array([-e[1], e[0]]) * ccw
    a2, b2 = a + n * (depth + 0.3), b + n * (depth + 0.3)

    def meet(p, d, q, f):
        t = np.linalg.solve(np.array([d, -f]).T, q - p)[0]
        return p + t * d
    prev, nxt = Q[(i - 1) % 4], Q[(i + 2) % 4]
    new = Q.copy()
    new[i] = meet(a2, e, prev, a - prev)
    new[(i + 1) % 4] = meet(a2, e, nxt, b - nxt)
    r = Polygon(new).buffer(0)
    if r.is_empty or r.area < 0.9 * g.area or r.intersection(other).area > OVERLAP_MIN:
        return None
    return r


INSET = 1.0  # pt; every room is drawn this far inside its boundary, so neighbours never touch and each border shows


def inset_entries(entries):
    """Every room pulled in by INSET (holes pushed out by as much), arcs refitted where the
    room had them. A room that would lose half of itself is left alone. Returns the count."""
    from shapely.geometry import MultiPolygon, Polygon
    from rooms import arcify, flatten_arcs
    n = 0
    for i, e in enumerate(entries):
        poly, extra = e[4], e[5]
        had_arcs = any(len(p) > 2 and p[2] for p in poly)
        g = Polygon(flatten_arcs(poly), [flatten_arcs(h) for h in extra.get('holes', [])]).buffer(0)
        r = g.buffer(-INSET, join_style='mitre', mitre_limit=3.0)
        if isinstance(r, MultiPolygon):
            r = max(r.geoms, key=lambda q: q.area)
        if r.is_empty or r.geom_type != 'Polygon' or r.area < 0.5 * g.area:
            continue
        ext = [[float(x), float(y)] for x, y in r.exterior.coords[:-1]]
        new = arcify(ext) if had_arcs else ext
        new = [[round(float(p[0]), 1), round(float(p[1]), 1)] + ([round(float(p[2]), 4)] if len(p) > 2 and p[2] else []) for p in new]
        ex2 = dict(extra)
        holes = [[[round(float(x), 1), round(float(y), 1)] for x, y in h.coords[:-1]] for h in r.interiors if Polygon(h).area >= 20]
        if holes:
            ex2['holes'] = holes
        elif 'holes' in ex2:
            del ex2['holes']
        entries[i] = e[:4] + (new, ex2)
        n += 1
    return n


def mark_suites(entries, cfg):
    """A suite (floors.py `suites`: id -> (category, name, tags[, points])) is a named region
    drawn around or between several rooms: the rooms whose centre lies in it, and the rooms
    holding one of the points, take the suite's category and name; those inside become its
    holes; the suite itself carries the 'suite' tag (drawn lighter). Returns the number of
    rooms taken in."""
    from shapely.geometry import Point, Polygon
    from rooms import flatten_arcs
    n = 0
    for i, e in enumerate(entries):
        spec = cfg['suites'].get(e[2])
        if not spec:
            continue
        cat, name, tags, *members = spec
        points = [Point(p) for p in (members[0] if members else [])]
        g = Polygon(flatten_arcs(e[4])).buffer(0)
        holes = []
        for j, o in enumerate(entries):
            if j == i or o[0] != 3:  # only the unnumbered rooms join a suite
                continue
            og = Polygon(flatten_arcs(o[4])).buffer(0)
            inside = g.contains(og.representative_point())
            if not inside and not any(og.contains(q) for q in points):
                continue
            extra = dict(o[5]); extra['name'] = name; extra['label'] = ''
            extra['tags'] = sorted(set(extra.get('tags', [])) | set(tags))
            entries[j] = (o[0], o[1], o[2], cat, o[4], extra)
            if inside:
                holes.append([[round(float(x), 1), round(float(y), 1)] for x, y in og.exterior.coords[:-1]])
            n += 1
        extra = dict(e[5]); extra['tags'] = sorted(set(extra.get('tags', [])) | set(tags) | {'suite'})
        if holes:
            extra['holes'] = holes
        entries[i] = (e[0], e[1], e[2], cat, e[4], extra)
    return n


def snap_doors(doors, entries):
    """A door marker the patches put on a room's edge (`snap`: the room's id) is moved to the
    point of that room's boundary nearest the doorway and turned along the edge there, so a
    suite's entrances sit on the suite as drawn. Returns the number moved."""
    import numpy as np
    from shapely.geometry import LineString, Point, Polygon
    from rooms import flatten_arcs
    n = 0
    for dr in doors:
        rid = dr.get('snap')
        if not rid:
            continue
        e = next((e for e in entries if e[2] == rid), None)
        if e is None:
            print(f"  door {dr.get('name', '')!r}: no room {rid!r} to sit on")
            continue
        ring = Polygon(flatten_arcs(e[4])).exterior
        a, b, o = (np.array(dr[k], float) for k in 'abo')
        m = (a + b) / 2
        p = np.array(ring.interpolate(ring.project(Point(m))).coords[0])
        coords = np.array(ring.coords)
        s, t = min(zip(coords[:-1], coords[1:]), key=lambda st: LineString(st).distance(Point(p)))
        u = t - s
        u /= np.linalg.norm(u) or 1.0
        v = b - a
        v /= np.linalg.norm(v) or 1.0
        if np.dot(u, v) < 0:
            u = -u
        ang = math.atan2(u[1], u[0]) - math.atan2(v[1], v[0])
        c, sn = math.cos(ang), math.sin(ang)
        rot = np.array([[c, -sn], [sn, c]])
        for k, q in (('a', a), ('b', b), ('o', o)):
            dr[k] = [round(float(x), 1) for x in rot @ (q - m) + p]
        n += 1
    return n


def clip_entries(entries, outlines):
    """No room reaches past the building: a polygon that sticks out of the outline by more
    than a couple of points is cut to it (arcs refitted). Returns the number cut."""
    from shapely.geometry import MultiPolygon, Polygon
    from shapely.ops import unary_union
    from rooms import arcify, flatten_arcs
    inside = unary_union([Polygon(flatten_arcs(o)).buffer(0) for o in outlines])
    n = 0
    for i, e in enumerate(entries):
        g = Polygon(flatten_arcs(e[4]), [flatten_arcs(h) for h in e[5].get('holes', [])]).buffer(0)
        if g.is_empty or g.difference(inside).area <= 2.0:
            continue
        r = g.intersection(inside)
        if isinstance(r, MultiPolygon):
            r = max(r.geoms, key=lambda q: q.area)
        if r.is_empty or r.geom_type != 'Polygon' or r.area < 0.5 * g.area:
            continue
        had_arcs = any(len(p) > 2 and p[2] for p in e[4])
        ext = [[float(x), float(y)] for x, y in r.simplify(0.3).exterior.coords[:-1]]
        new = arcify(ext) if had_arcs else ext
        new = [[round(float(p[0]), 1), round(float(p[1]), 1)] + ([round(float(p[2]), 4)] if len(p) > 2 and p[2] else []) for p in new]
        extra = dict(e[5])
        holes = [[[round(float(x), 1), round(float(y), 1)] for x, y in h.coords[:-1]] for h in r.interiors if Polygon(h).area >= 20]
        if holes:
            extra['holes'] = holes
        elif 'holes' in extra:
            del extra['holes']
        entries[i] = e[:4] + (new, extra)
        n += 1
    return n


def resolve_overlaps(entries):
    """Rooms do not overlap. Where two polygons do, the overlap is cut from the one with the
    lower standing: a traced room over an open area or a named region, those over an
    unnumbered room; between equals the bigger polygon gives way. A polygon with arcs is cut
    only when the other cannot give way (the cut would lose its arcs). Returns the number of
    polygons cut."""
    from shapely.geometry import MultiPolygon, Polygon
    from shapely.strtree import STRtree
    from rooms import flatten_arcs

    def geom(e):
        return Polygon(flatten_arcs(e[4]), [flatten_arcs(h) for h in e[5].get('holes', [])]).buffer(0)

    arcs = [any(len(p) > 2 and p[2] for p in e[4]) for e in entries]
    polys = [geom(e) for e in entries]
    cut = 0
    for _ in range(3):
        tree = STRtree(polys)
        changed = False
        for i in range(len(polys)):
            for j in tree.query(polys[i]):
                j = int(j)
                if j <= i or not polys[i].intersects(polys[j]):
                    continue
                x = polys[i].intersection(polys[j])
                if x.area < OVERLAP_MIN:
                    continue
                a, b = entries[i], entries[j]
                if a[0] != b[0]:
                    v = i if a[0] > b[0] else j
                elif arcs[i] != arcs[j]:
                    v = j if arcs[i] else i
                else:
                    v = i if polys[i].area >= polys[j].area else j
                o = j if v == i else i
                if arcs[v] and not arcs[o]:
                    v, o = o, v
                if arcs[v]:
                    print(f'  overlap of {a[2]} and {b[2]} ({x.area:.1f} pt²) left: both have arcs')
                    continue
                # a four-walled room keeps its four walls: the wall nearest the overlap moves in
                r = shrink_wall(entries[v][4], polys[o]) if len(entries[v][4]) == 4 and not arcs[v] else None
                if r is None:
                    r = polys[v].difference(polys[o].buffer(0.05))
                if isinstance(r, MultiPolygon):
                    r = max(r.geoms, key=lambda q: q.area)
                if r.is_empty or r.area < 0.5 * polys[v].area:
                    print(f'  overlap of {a[2]} and {b[2]} ({x.area:.1f} pt²) left: {entries[v][2]} would lose most of itself')
                    continue
                r = r.simplify(0.3)
                extra = dict(entries[v][5])
                holes = [[[round(float(px), 1), round(float(py), 1)] for px, py in h.coords[:-1]] for h in r.interiors if Polygon(h).area >= 20]
                if holes:
                    extra['holes'] = holes
                elif 'holes' in extra:
                    del extra['holes']
                entries[v] = entries[v][:4] + ([[round(float(px), 1), round(float(py), 1)] for px, py in r.exterior.coords[:-1]], extra)
                polys[v] = r
                cut += 1
                changed = True
        if not changed:
            break
    return cut


def union_polys(polys):
    """Outer contour of the union of polygons (closed by a few px so touching flights join)."""
    import cv2
    import numpy as np
    pts = np.concatenate([np.array(xy(p), np.float32) for p in polys])
    x0, y0 = np.floor(pts.min(0)).astype(int) - 6
    x1, y1 = np.ceil(pts.max(0)).astype(int) + 6
    a = np.zeros((y1 - y0, x1 - x0), np.uint8)
    for p in polys:
        cv2.fillPoly(a, [np.round(np.array(xy(p)) - [x0, y0]).astype(np.int32)], 255)
    a = cv2.morphologyEx(a, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    cs, _ = cv2.findContours(a, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    c = cv2.approxPolyDP(max(cs, key=cv2.contourArea), 2.0, True).reshape(-1, 2) + [x0, y0]
    return [[float(x), float(y)] for x, y in c]


def region_at(unlabelled, x, y):
    """The unlabelled region whose polygon contains (x, y), smallest first."""
    import cv2
    import numpy as np
    # anything bigger than a big room is the unenclosed hall, not the room the point meant
    dist = [(cv2.pointPolygonTest(np.array(xy(u['polygon']), np.float32), (float(x), float(y)), True), u) for u in unlabelled if u['area'] <= 150000 or u.get('atrium')]
    hits = [u for d, u in dist if d >= 0]
    if hits:
        return min(hits, key=lambda u: u['area'])
    # the point may sit on a line (e.g. the centre of an elevator's X): take the nearest region
    d, u = max(dist, key=lambda t: t[0])
    return u if d >= -8 else None


def fmt_extra(extra):
    parts = []
    for k, v in extra.items():
        if k == 'holes':
            parts.append(f"{k}: [{', '.join(fmt_poly(h) for h in v)}]")
        elif isinstance(v, list):
            parts.append(f"{k}: [{', '.join(ts_str(t) for t in v)}]")
        else:
            parts.append(f'{k}: {ts_str(v)}')
    return '{ ' + ', '.join(parts) + ' }'


def main(workdir, out_dir, reframe=False):
    data = load(workdir)
    frame_path = os.path.join(out_dir, 'frame.ts')
    fits = False
    if os.path.exists(frame_path) and not reframe:
        # Keep the frame the levels are already drawn in (so hand-placed coordinates such as
        # the street stay put) as long as the traced outlines still fit in it; `--reframe`
        # forces a new one. Only some floors traced: the frame is kept regardless.
        x0, y0, w, h = read_frame(frame_path)
        nx, ny, nw, nh = frame(data)
        fits = len(data) < len(FLOORS) or (nx >= x0 - FRAME_SLACK and ny >= y0 - FRAME_SLACK and nx + nw <= x0 + w + FRAME_SLACK and ny + nh <= y0 + h + FRAME_SLACK)
        print(f'floors {", ".join(sorted(data))}: keeping the existing frame' if fits else 'traced outlines fall outside the existing frame: recomputing it')
    if not fits:
        x0, y0, w, h = frame(data)
        open(frame_path, 'w').write(
            '// GENERATED by tools/trace_cad/emit_ts.py — do not edit by hand.\n'
            '/** Shared floor frame: every level is drawn in this coordinate box. */\n'
            f'export const FRAME = {{ width: {w:.0f}, height: {h:.0f} }};\n'
            '/** Sheet point (upper-floor PDFs) at the frame origin; lets one floor be regenerated alone. */\n'
            f'export const ORIGIN = {{ x: {x0:.0f}, y: {y0:.0f} }};\n'
        )
        print(f'frame {w:.0f} x {h:.0f}')
    for fid, d in data.items():
        emit_floor(fid, d, x0, y0, out_dir)


if __name__ == '__main__':
    args = [a for a in sys.argv[1:] if a != '--reframe']
    main(args[0], args[1], reframe='--reframe' in sys.argv)
