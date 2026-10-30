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
ICONS = {'men': 'man', 'women': 'woman', 'all gender': 'all-gender'}


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
    lines.append("import type { PoiSpec, RoomSpec } from './floor';")
    lines.append("import type { XY } from '../helpers';")
    lines.append('')
    outlines = [to_frame(o) for o in d['outlines']]
    lines.append(f'export const outline: XY[] = {fmt_poly(outlines[0])};')
    lines.append('export const islands: XY[][] = [' + ', '.join(fmt_poly(o) for o in outlines[1:]) + '];')
    lines.append('')
    lines.append('/** Desks in the open workspaces (worksurface outlines), drawn for orientation only. */')
    lines.append('export const desks: XY[][] = [' + ', '.join(fmt_poly(to_frame(dsk)) for dsk in d.get('desks', [])) + '];')
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
    for px, py, uid, cat, name, label, tags in cfg['named']:
        points = px if isinstance(px, list) else [(px, py)]
        regions = []
        for qx, qy in points:
            u = region_at(d['unlabelled'], qx, qy)
            if u is not None and all(u is not r for r in regions):
                regions.append(u)
        if not regions:
            print(f'  floor {fid}: no unlabelled region at {points} for {uid}')
            continue
        resolved.append((uid, cat, name, label, tags, points, regions))
    # Several named entries may resolve to one region (three elevator shafts whose X marks
    # merge into a single cluster): split that region between them by nearest point.
    for uid, cat, name, label, tags, points, regions in resolved:
        sharers = [o for o in resolved if len(o[6]) == 1 and len(regions) == 1 and o[6][0] is regions[0]]
        axis = regions[0].get('axis')  # the walls' direction around the region, from the tracer
        if len(sharers) > 1:
            parts = split_shared(regions[0]['polygon'], [o[5][0] for o in sharers], d['outlines'], axis)
            poly = parts[[o[0] for o in sharers].index(uid)]
        else:
            poly = regions[0]['polygon'] if len(regions) == 1 else union_polys([r['polygon'] for r in regions])
        drawn = len(regions) == 1 and regions[0].get('named') == uid
        if drawn:  # a patch area drawn for this region: as given, a box squared to the walls
            if BOXED_TAGS & set(tags) and axis is not None:
                poly = turned_to(poly, axis)
        elif 'atrium' in tags:  # the atrium is an oval: a clean ellipse through its traced outline
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
        w = wing(uid) or ('Northeast' if uid.startswith('ne-') else 'Southwest' if uid.startswith('sw-') else None)
        entries.append((1, w, uid, cat, poly, extra))
    for uid, cat, name, label, tags, poly in cfg['manual']:
        extra = with_icon({'name': name, 'label': label, 'tags': tags})
        w = wing(uid)
        poly = clip_to(poly, d['outlines'])
        placed.append(Polygon(xy(poly)).buffer(0))
        entries.append((1, w, uid, cat, poly, extra))
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
            if g.area < 0.5 * rw * rh:
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
            elif g.area >= 0.75 * rw * rh:
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
    resolve_overlaps(entries)
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
    print(f'level{fid}.ts: {len(d["rooms"])} rooms + {len(cfg["named"])} named regions, {len(d.get("desks", []))} desks')


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


SLIVER = 1.5  # px; an overlap nowhere wider than this is a shared wall, not an overlap


def resolve_overlaps(entries, min_area=2.0):
    """Rooms never overlap. The traced polygons were reconciled, but arcs fitted afterwards
    (and boxes, ellipses and hand shapes added here) can still bite a neighbour: each polygon
    gives up whatever an entry of higher priority (enclosed rooms, then cores and named
    regions, then open areas, then unnumbered rooms; earlier first within a rank) already
    covers. A trimmed polygon keeps its arcs as finely flattened curves. An overlap nowhere
    wider than `SLIVER` is a shared wall whose faces were turned parallel and is left alone."""
    from shapely.geometry import MultiPolygon, Polygon
    from rooms import flatten_arcs
    shape = lambda poly, extra: Polygon(flatten_arcs(poly), [xy(h) for h in extra.get('holes', [])]).buffer(0)
    order = sorted(range(len(entries)), key=lambda i: (entries[i][0], i))
    kept = []
    for i in order:
        prio, w, rid, cat, poly, extra = entries[i]
        g = shape(poly, extra)
        if isinstance(g, MultiPolygon):
            g = max(g.geoms, key=lambda q: q.area)
        cut = g
        for other in kept:
            if not cut.intersects(other):
                continue
            inter = cut.intersection(other)
            # a hairline sliver along a shared wall (the two faces turned parallel by a
            # fraction of a degree) counts as touching: cutting it would notch the wall
            if inter.area <= min_area or inter.buffer(-SLIVER / 2).is_empty:
                continue
            cut = cut.difference(other)
            if isinstance(cut, MultiPolygon):
                cut = max(cut.geoms, key=lambda q: q.area)
        if cut is not g and not cut.is_empty and cut.area > 0.2 * g.area:
            # a cut can leave a zero-width spike where a sliver ended: a mitred inset and
            # outset by less than a pixel removes it without moving the corners
            cut = cut.buffer(-SLIVER / 2, join_style='mitre').buffer(SLIVER / 2, join_style='mitre')
            if isinstance(cut, MultiPolygon):
                cut = max(cut.geoms, key=lambda q: q.area)
            cut = cut.simplify(0.2)
            poly = [[round(float(x), 1), round(float(y), 1)] for x, y in cut.exterior.coords[:-1]]
            holes = [[[round(float(x), 1), round(float(y), 1)] for x, y in r.coords[:-1]] for r in cut.interiors if Polygon(r).area >= 20]
            extra = {**extra, 'holes': holes} if holes else {k: v for k, v in extra.items() if k != 'holes'}
            entries[i] = (prio, w, rid, cat, poly, extra)
            g = cut
        kept.append(g)


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


def split_shared(poly, points, outlines=(), axis=None):
    """Split a polygon between seed points: the regions that share one polygon are the
    shafts of an elevator bank, so the bank is drawn as equal squares side by side along
    the bank's axis (the n-th of the bank's length), one per seed, in the seeds' order
    along that axis. The axis is the direction of the shaft walls (`axis`, from the tracer;
    the X marks on the shafts make the traced region's own rectangle unreliable), else that
    of the nearest straight facade, which the shafts stand parallel to, else the region's
    long axis."""
    import numpy as np
    P = np.array(xy(poly), float)
    S = np.array(points, float)
    if axis is not None:
        u = np.array([math.cos(math.radians(axis)), math.sin(math.radians(axis))])
    else:
        u = facade_direction(outlines, P.mean(0)) if outlines else None
    if u is None:
        c, u, L, _ = min_area_rect(xy(poly))
    else:
        v = np.array([-u[1], u[0]])
        if len(S) > 1 and np.ptp(S @ v) > np.ptp(S @ u):  # the seeds spread across the facade: the bank stands end-on
            u, v = v, -u
        a, b = P @ u, P @ v
        L = a.max() - a.min()
        c = u * (a.max() + a.min()) / 2 + v * (b.max() + b.min()) / 2
    v = np.array([-u[1], u[0]])
    n = len(points)
    side = L / n
    along = (S - c) @ u
    cells = {}
    for rank, i in enumerate(np.argsort(along)):
        cc = c + u * ((rank - (n - 1) / 2) * side)
        cells[int(i)] = [[round(float(x), 1), round(float(y), 1)] for x, y in
                         (cc + u * sx * side / 2 + v * sy * side / 2 for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1)))]
    return [cells[i] for i in range(n)]


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
