"""Rooms from the wall-only drawing: the faces of the free space, labelled.

Usage: python3 faces.py <floor id> <workdir>

Reads <workdir>/<pdf>_walls.json and <pdf>_geom.json and the floor's patches, writes
<workdir>/<pdf>_rooms.json in the schema emit_ts.py reads (rooms, outlines, unlabelled,
exits, desks). Rooms whose label sits in the corridor network and have no patch area, and
faces holding more than one label, are reported on stdout.

See docs/superpowers/specs/2026-10-29-vector-tracer-design.md.
"""
import json
import math
import os
import re
import sys
import warnings

import numpy as np
from shapely import voronoi_polygons
from shapely.geometry import LineString, MultiPoint, MultiPolygon, Point, Polygon, box
from shapely.ops import unary_union
from shapely.strtree import STRtree

from floors import FLOORS, category
from patches import load_patches
from walls import BORDER, scale_of

warnings.filterwarnings('ignore', category=RuntimeWarning, module='shapely')  # degenerate envelopes of slivers

BUF = 1.5          # pt; half the width the strokes are painted with (seals drafting gaps up to 3 pt)
GROW = 0.0         # pt; how far a face is grown back towards the stroke centres (0 keeps the level files' inset, 1.5 would be the stroke centre)
MIN_FACE = 20      # pt²; smaller pockets are drafting slivers; cells of hatched cores are kept to be merged
MIN_LABEL_FACE = 300  # pt²; a label is never given to a smaller face
MAX_ROOM = 150000  # pt²; anything bigger is the corridor network
LABEL_REACH = 8.0  # pt; a label on a wall line is given to the nearest face this close
SIMPLIFY = 0.5     # pt; vertex tolerance after growing the face back to the wall faces
QUAD_IOU = 0.9     # a rectangle covering a room this well replaces its shape
EXIT_DIST = 25.0   # pt; a door hinge this close to the outline is an entrance
CELL_MAX = 4.0     # x the floor's minimum room: smaller unlabelled faces are cells of a hatched core, merged across strokes
CELL_GAP = 0.6     # pt; extra reach when joining cells (a stroke is 3 pt wide, cells meet across it)
DESK_SHORT = (9.0, 20.0)
DESK_LONG = (18.0, 45.0)
DESK_WIDTH = 0.9
OPEN_KINDS = {'open', 'piazza', 'informal', 'porch', 'lounge'}  # categories drawn as open-plan areas
IGNORE_NAMES = {'FEC', 'UP', 'DN', 'DOWN', 'RAMP', 'OPEN TO BELOW', 'WAP', 'Side A', 'Side B', 'Side C', 'Side D', '?'}


def labels(geom, cfg):
    """Room labels: [{'id', 'name', 'x', 'y'}], each number with the name lines nearest it
    (the same rule as the raster tracer)."""
    lo, hi = cfg['label_sizes']
    number_re = re.compile(cfg['number_re'])
    skip = cfg['skip']
    lines = [l for l in geom['lines'] if lo <= l['size'] <= hi and l['bbox'][0] < BORDER[2]]
    centre = lambda l: ((l['bbox'][0] + l['bbox'][2]) / 2, (l['bbox'][1] + l['bbox'][3]) / 2)
    numbers = [l for l in lines if number_re.match(l['text']) and l['text'] not in skip]
    names = [l for l in lines if not number_re.match(l['text']) and l['text'] not in IGNORE_NAMES and not re.match(r"^\d+'", l['text'])]
    out = [{'id': n['text'], 'x': centre(n)[0], 'y': centre(n)[1], 'names': []} for n in numbers]
    for nm in names:
        cx, cy = centre(nm)
        best = min(out, key=lambda o: math.hypot(o['x'] - cx, o['y'] - cy), default=None)
        if best is not None and math.hypot(best['x'] - cx, best['y'] - cy) < 30 * hi / 5.0:
            best['names'].append((cy, cx, nm['text']))
    for o in out:
        o['name'] = ' '.join(t for _, _, t in sorted(o['names'])).replace('/ ', '/').replace(' -', '').strip()
        del o['names']
    return out


def free_space(w, patches):
    """(faces, exterior faces) of the free space: the plan border minus the painted walls."""
    lines = [LineString([(a, b), (c, d)]) for a, b, c, d in w['walls']]
    lines += [LineString([(a, b), (c, d)]) for a, b, c, d in w['closures']]
    lines += [LineString([(a, b), (c, d)]) for a, b, c, d, *_ in patches['lines']]
    scale = w['scale']
    mass = unary_union([ln.buffer(BUF * scale, cap_style='flat') for ln in lines if ln.length > 0]
                       + [Point(cx, cy).buffer(r + 0.5) for cx, cy, r in w['columns']])
    border = box(*BORDER)
    free = border.difference(mass)
    pieces = [p for p in (free.geoms if isinstance(free, MultiPolygon) else [free]) if p.area >= MIN_FACE * scale * scale]
    # a face is its outer ring: furniture standing in a room never cuts it. The outside is
    # kept with its holes (the building is a hole in it) to find the outline.
    faces = [Polygon(p.exterior) for p in pieces]
    rim = border.exterior
    exterior = [(f, p) for f, p in zip(faces, pieces) if p.intersects(rim)]
    return faces, exterior


def biggest(g):
    if isinstance(g, MultiPolygon):
        return max(g.geoms, key=lambda q: q.area)
    return g


def ring(poly):
    return [[round(float(x), 1), round(float(y), 1)] for x, y in poly.exterior.coords[:-1]]


def iou(a, b):
    u = a.union(b).area
    return a.intersection(b).area / u if u else 0.0


def valid(g, fallback):
    """A valid polygon or the fallback (simplification can fold a sliver over itself)."""
    if g.is_valid and not g.is_empty:
        return g
    g = biggest(g.buffer(0))
    return g if g.is_valid and not g.is_empty and g.area > 0.5 * fallback.area else fallback


def merge_collinear(poly, deg=2.0):
    pts = list(poly.exterior.coords[:-1])
    if len(pts) < 5:
        return poly
    out = []
    n = len(pts)
    for i in range(n):
        p, q, r = np.array(pts[i - 1]), np.array(pts[i]), np.array(pts[(i + 1) % n])
        a, b = q - p, r - q
        na, nb = np.linalg.norm(a), np.linalg.norm(b)
        if na < 1e-9 or nb < 1e-9:
            continue
        cos = np.clip(np.dot(a, b) / (na * nb), -1, 1)
        if math.degrees(math.acos(cos)) < deg:
            continue
        out.append(tuple(q))
    return Polygon(out) if len(out) >= 3 else poly


def shape(face, scale, quad=False, boxed=False):
    """A room's polygon from its face: grown back to the wall faces, simplified, collinear
    runs merged; the minimum rectangle when it covers the room well (or is forced)."""
    g = biggest(face.buffer(GROW * scale, join_style='mitre', mitre_limit=3.0)) if GROW else face
    g = valid(merge_collinear(biggest(g.simplify(SIMPLIFY * scale))), face)
    if g.area <= 0 or len(g.exterior.coords) < 4:
        return face
    rect = g.minimum_rotated_rectangle
    if rect.area > 0 and (boxed or (quad and iou(rect, g) >= 0.75) or iou(rect, g) >= QUAD_IOU):
        return rect
    # the simplest polygon that still is the room: coarser tolerances while the shape holds
    for tol in (1.0, 2.0, 3.0, 4.0):
        s = valid(biggest(g.simplify(tol * scale)), g)
        if iou(s, g) >= 0.97 and len(s.exterior.coords) < len(g.exterior.coords):
            g = s
    return g


def atrium_polygon(cfg, n=48):
    if not cfg['atrium']:
        return None
    cx, cy, a, b, ang = cfg['atrium']
    t = math.radians(ang)
    pts = []
    for k in range(n):
        u = 2 * math.pi * k / n
        x, y = a * math.cos(u), b * math.sin(u)
        pts.append((cx + x * math.cos(t) - y * math.sin(t), cy + x * math.sin(t) + y * math.cos(t)))
    return Polygon(pts)


def desks(geom, scale):
    out = []
    for q in geom.get('quads', []):
        pts, width, black = q[:4], q[4], q[5]
        if not black or width < DESK_WIDTH:
            continue
        sides = [math.dist(pts[i], pts[(i + 1) % 4]) for i in range(4)]
        s, l = min(sides), max(sides)
        if DESK_SHORT[0] * scale <= s <= DESK_SHORT[1] * scale and DESK_LONG[0] * scale <= l <= DESK_LONG[1] * scale:
            out.append([[round(x, 1), round(y, 1)] for x, y in pts])
    return out


def build(fid, workdir):
    cfg = FLOORS[fid]
    prefix = os.path.join(workdir, cfg['pdf'])
    w = json.load(open(prefix + '_walls.json'))
    geom = json.load(open(prefix + '_geom.json'))
    patches = load_patches(fid)
    scale = w['scale']
    faces, exterior = free_space(w, patches)
    # a covered plaza or a roof deck the floor config marks exterior
    for sx, sy in cfg['exterior']:
        for f in faces:
            if f.contains(Point(sx, sy)) and all(f is not e for e, _ in exterior):
                exterior.append((f, f))
    tree = STRtree(faces)
    ext_ids = {id(f) for f, _ in exterior}
    outside = unary_union([p for _, p in exterior]) if exterior else Polygon()
    inside = unary_union([f for f in faces if id(f) not in ext_ids])  # the free space of the building

    def face_at(x, y):
        p = Point(x, y)
        hits = [faces[i] for i in tree.query(p) if faces[i].contains(p) and faces[i].area >= MIN_LABEL_FACE * scale * scale]
        if hits:
            return min(hits, key=lambda f: f.area)
        near = [(faces[i].distance(p), faces[i]) for i in tree.query(p.buffer(LABEL_REACH * scale))]
        near = [(d, f) for d, f in near if d <= LABEL_REACH * scale and id(f) not in ext_ids and f.area >= MIN_LABEL_FACE * scale * scale]
        return min(near, key=lambda t: (t[0], t[1].area))[1] if near else None

    max_room = MAX_ROOM * scale * scale
    rooms, owners, open_labels, patched = [], {}, [], []
    for lab in labels(geom, cfg):
        rid = lab['id']
        if rid in cfg['hand']:
            rooms.append({'id': rid, 'name': lab['name'], 'kind': 'room', 'polygon': [[float(x), float(y)] for x, y in cfg['hand'][rid]], 'hand': True})
            continue
        f = face_at(lab['x'], lab['y'])
        if f is None:
            print(f'  {rid}: label on no face')
            continue
        if rid in patches['areas']:
            patched.append((lab, f))
        elif f.area > max_room or id(f) in ext_ids:
            open_labels.append((lab, f))
        else:
            owners.setdefault(id(f), (f, []))[1].append(lab)
    for f, labs in owners.values():
        if len(labs) == 1:
            parts = [f]
        else:
            # two numbers in one face: a partition the sheet leaves open, or a merged pair.
            # Split by nearest label and report it for a patch line.
            print(f"  one face holds {', '.join(l['id'] for l in labs)}: split by nearest label (add a patch line if they are rooms)")
            cells = voronoi_polygons(MultiPoint([(l['x'], l['y']) for l in labs]), extend_to=f.buffer(10))
            parts = [biggest(c.intersection(f)) for c in cells.geoms]
            parts = [next(p for p in parts if p.contains(Point(l['x'], l['y'])) or p.distance(Point(l['x'], l['y'])) < 1) for l in labs]
        for lab, part in zip(labs, parts):
            rid = lab['id']
            g = shape(part, scale, quad=rid in cfg['quad'], boxed=rid in cfg['box'])
            room = {'id': rid, 'name': lab['name'], 'kind': 'room', 'area': int(part.area), 'polygon': ring(g)}
            if len(labs) > 1:
                room['shared'] = [l['id'] for l in labs if l is not lab]
            rooms.append(room)
    for r in rooms:
        if r.get('hand'):
            r['area'] = int(Polygon(r['polygon']).area)
            del r['hand']
    # patch areas: the polygon clipped to the free space of the label's face (an open office
    # in the corridor network, a booth whose label stands outside its open front), minus the
    # rooms already placed. Open-plan kinds carry the 'open plan' tag; a booth is a room.
    placed = Polygon()
    for lab, f in patched:
        rid = lab['id']
        kind = 'open' if category(lab['name'], rid) in OPEN_KINDS else 'room'
        g = Polygon(patches['areas'][rid]).buffer(0)
        if kind == 'open':  # an open-plan area stops at the walls and at the rooms standing in it
            g = g.intersection(inside.buffer(BUF * scale, join_style='mitre'))
        g = biggest(g.difference(placed))
        if g.is_empty:
            print(f'  {rid}: patch area lies outside its face')
            continue
        # a traced room reaching over the area (a lab box whose open side faces a workspace)
        # gives the area up: it becomes a hole in, or a bite out of, that room
        for r in rooms:
            rg = Polygon(r['polygon'], r.get('holes', [])).buffer(0)
            if rg.intersects(g) and rg.intersection(g).area > 0.5 * g.area:
                cut = biggest(rg.difference(g))
                r['polygon'] = ring(cut)
                holes = [[[round(float(x), 1), round(float(y), 1)] for x, y in h.coords[:-1]] for h in cut.interiors if Polygon(h).area >= 20]
                if holes:
                    r['holes'] = holes
                elif 'holes' in r:
                    del r['holes']
        room = {'id': rid, 'name': lab['name'], 'kind': kind, 'area': int(g.area), 'polygon': ring(g)}
        holes = [[[round(float(x), 1), round(float(y), 1)] for x, y in h.coords[:-1]] for h in g.interiors if Polygon(h).area >= 20]
        if holes:
            room['holes'] = holes
        rooms.append(room)
        placed = placed.union(g)
    for lab, f in open_labels:
        if category(lab['name'], lab['id']) != 'circulation':
            print(f"  {lab['id']} {lab['name']!r}: label in the open (face {int(f.area)} pt²), no patch area")
    # the building: the border minus the outside; its boundary is the outline
    building = box(*BORDER).difference(outside)
    pieces = sorted((list(building.geoms) if isinstance(building, MultiPolygon) else [building]), key=lambda p: -p.area)
    # a piece of the building holds rooms; the legend box and the north arrow do not
    room_points = [Point(Polygon(r['polygon']).representative_point()) for r in rooms if len(r['polygon']) >= 3]
    pieces = [p for p in pieces if p.area >= max_room / 10 and any(p.contains(q) for q in room_points)]
    outlines = [ring(merge_collinear(biggest(Polygon(p.exterior).simplify(1.0 * scale)))) for p in pieces]
    # faces nobody labelled: cores, restrooms, stairs, closets, for floors.py's `named` list
    labelled = set(owners)
    min_room = cfg.get('min_room', 600) * scale * scale
    spare = [f for f in faces if id(f) not in labelled and id(f) not in ext_ids and f.area <= max_room
             and not any(f.contains(Point(l['x'], l['y'])) for l, _ in open_labels + patched)]
    # Hatched floors, stair treads, elevator X marks and stall partitions chop a core into
    # cells: cells below room size that touch across a stroke are merged back into one region.
    small = [f for f in spare if f.area < min_room * CELL_MAX]
    merged = []
    if small:
        joined = unary_union([f.buffer(BUF * scale + CELL_GAP) for f in small])
        for blob in (joined.geoms if isinstance(joined, MultiPolygon) else [joined]):
            g = biggest(Polygon(blob.exterior).buffer(-(BUF * scale + CELL_GAP), join_style='mitre'))
            if not g.is_empty and g.area >= min_room:
                merged.append(g)
    unl = []
    for f in [f for f in spare if f.area >= min_room * CELL_MAX] + merged:
        if f.area < min_room:
            continue
        g = shape(f, scale)
        c = f.representative_point()
        unl.append({'area': int(f.area), 'x': round(c.x, 1), 'y': round(c.y, 1), 'polygon': ring(g)})
    ell = atrium_polygon(cfg)
    if ell is not None:
        c = ell.centroid
        unl.append({'area': int(ell.area), 'atrium': True, 'x': round(c.x, 1), 'y': round(c.y, 1), 'polygon': ring(ell)})
    # entrances: door hinges on the outline
    exits = []
    if cfg['exits'] and outlines:
        conts = [Polygon(o).exterior for o in outlines]
        for cx, cy, r, p0, p1 in w['doors']:
            mx, my = (p0[0] + p1[0]) / 2 - cx, (p0[1] + p1[1]) / 2 - cy
            n = math.hypot(mx, my) or 1.0
            mid = (cx + r * mx / n, cy + r * my / n)
            at = ((mid[0] + cx) / 2, (mid[1] + cy) / 2)
            d = min(c.distance(Point(at)) for c in conts)
            if d <= EXIT_DIST * scale and all(math.dist(at, e) > 40 * scale for e in exits):
                exits.append([round(at[0], 1), round(at[1], 1)])
    out = {'floor': fid, 'rooms': rooms, 'outlines': outlines, 'unlabelled': unl, 'exits': exits, 'desks': desks(geom, scale)}
    json.dump(out, open(prefix + '_rooms.json', 'w'))
    n_open = sum(r['kind'] == 'open' for r in rooms)
    print(f"floor {fid}: {len(rooms) - n_open} enclosed rooms, {n_open} open areas ({len(open_labels)} labels in the open), "
          f"{len(outlines)} outline(s), {len(unl)} unlabelled regions, {len(exits)} exits, {len(out['desks'])} desks")
    return out


if __name__ == '__main__':
    build(sys.argv[1], sys.argv[2])
