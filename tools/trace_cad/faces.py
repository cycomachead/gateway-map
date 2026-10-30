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
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'departments'))
from levels import flatten  # noqa: E402  (bulged polygons back to vertices)
from patches import load_patches
from walls import BORDER, fit_circle, scale_of

warnings.filterwarnings('ignore', category=RuntimeWarning, module='shapely')  # degenerate envelopes of slivers

BUF = 1.5          # pt; half the width the strokes are painted with (seals drafting gaps up to 3 pt)
GROW = 0.0         # pt; how far a face is grown back towards the stroke centres (0 keeps the level files' inset, 1.5 would be the stroke centre)
MIN_FACE = 4       # pt²; smaller pockets are drafting slivers; the cells of hatched cores (tiles) are kept to be merged
MIN_LABEL_FACE = 300  # pt²; a label is never given to a smaller face
MAX_ROOM = 150000  # pt²; anything bigger is the corridor network
MIN_ROOM = 600     # pt²; smaller unlabelled faces are closets and cavities, not rooms (floors.py `min_room` overrides)
LABEL_REACH = 8.0  # pt; a label on a wall line is given to the nearest face this close
SIMPLIFY = 0.5     # pt; vertex tolerance after growing the face back to the wall faces
OUTLINE_TOL = 1.5  # pt; the outline's tolerance (the drafting along the facades is removed first, see tidy_outline)
OUTLINE_SMOOTH = 8.0  # pt; jogs of the facade narrower than twice this (the mullion boxes are 13 pt wide, door chords 3) are not the outline
OUTLINE_JOG = 60.0  # pt; ... and no longer than this (a column bump is 20 pt; a channel along a canopy is hundreds)
OUTLINE_ARC_TOL = 2.0  # pt; the outline's curves are fitted with arcs this loosely ...
OUTLINE_ARC_DEV = 6.0  # pt; ... and kept while they stray at most this far (the building is 3,000 pt across)
OPEN = 2.5         # pt; notches narrower than twice this (strokes against a wall) are dropped from a room's shape
CLOSE = 2.0        # pt; slits narrower than twice this (a single stroke poking into the room) are filled
BITE = 10.0        # pt; a column standing in a wall bites this deep into a room, or bulges this far out of the outline
ALIGN_TOL = 1.5    # pt; walls of neighbouring rooms this close to one line are drawn on it
ALIGN_TURN = 1.0   # degrees; ... when they run within this of parallel
ALIGN_GAP = 30.0   # pt; ... and continue each other across at most this gap (a partition, a closet)
POCKET_MIN = 150.0 # pt²; a piece of the room this big behind a narrow neck (a desk against the wall) is kept
QUAD_IOU = 0.9     # a rectangle covering a room this well replaces its shape
ARC_TOL = 1.0      # pt; a run of short edges within this of a circle becomes one arc
ARC_DEV = 2.0      # pt; arcs that stray further from the traced shape are discarded
SLIVER_MAX = 60.0  # pt²; a four-wall fit must cover the shape but for slivers this small
POCKET_MAX = 1000.0  # pt²; an unlabelled face this small touching one room only is furniture standing in it
NOTCH_MAX = 400.0  # pt²; ... and may fill notches up to this (a credenza, a column's bite); a bowed wall leaves far more
NOTCH_SHARE = 0.25 # or up to this share of the room (a desk drawn against the wall of a small office)
NOTCH_TOTAL = 0.3  # all notches together at most this share of the room
NOTCH_CAP = 1200.0 # pt²; no notch bigger than this however big the room (an oval's corners are not notches)
FIT_OUTLIER = 3.0  # pt; boundary points further from a fitted wall are dropped once (a notch)
CORNER_ZONE = 5.0  # pt; boundary points this close to a rectangle corner (rounded by the opening) fit no wall
WALL_SUPPORT = 0.5 # a fitted wall's points must span at least this share of its length
CURVE_SAG = 3.0    # pt; a wall along which the drawing's curves bow further than this is an arc
BOW_REACH = 30.0   # pt; boundary points this far from a fitted wall may be that wall bowing
BOW_RES = 3.5      # pt; the boundary must lie this close to one circle for the wall to be an arc
EXIT_DIST = 25.0   # pt; a door hinge this close to the outline is an entrance
CELL_MAX = 4.0     # x the floor's minimum room: smaller unlabelled faces are cells of a hatched core, merged across strokes
CELL_GAP = 0.6     # pt; extra reach when joining cells (a stroke is 3 pt wide, cells meet across it)
DECK_CELL = 1500.0 # pt²; faces up to this on a terrace floor may be paver cells of the deck
WALL = 3.0         # pt; a block standing on the terrace is its rooms plus their walls
DECK_BLOB = 20000.0 # pt²; an unlabelled region this big inside the terrace is paving, not a room
DESK_SHORT = (9.0, 20.0)
DESK_LONG = (18.0, 45.0)
DESK_WIDTH = 0.9
DESK_REACH = 5.0   # pt; a desk is drawn when its centre stands this close to an open area
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


def shape(face, scale, quad=False, boxed=False, arcs=True):
    """A room's polygon from its face, as vertices: grown back to the wall faces, simplified,
    collinear runs merged; the minimum rectangle when it covers the room well (or is forced);
    otherwise curved runs (a facade, a bay) collapsed into arcs, as bulge values."""
    fitted = fit(face, scale, quad, boxed)
    return fitted if isinstance(fitted, list) else ring(fitted, arcs)


def ring(poly, arcs=False, tol=ARC_TOL, dev=ARC_DEV, min_iou=0.985):
    pts = [[round(float(x), 1), round(float(y), 1)] for x, y in poly.exterior.coords[:-1]]
    if arcs and len(pts) >= 8:
        from rooms import arcify
        arced = arcify(pts, tol=tol)
        # keep the arcs only when they still trace the shape (a run of notch edges can be
        # mistaken for a curve and come back as a bulge that is not there)
        back = Polygon(flatten(arced)).buffer(0)
        if not back.is_empty and iou(back, poly) >= min_iou and back.hausdorff_distance(poly) <= dev:
            pts = arced
    return pts


COLUMNS = None  # STRtree of the floor's column discs, set by build(); fill_slits() closes their bites


def fill_slits(face, scale):
    """The face without the drafting that cuts into it: a single stroke poking in (a wall line
    overshooting its corner, a leader) leaves a slit a stroke wide, closed with a mitred closing
    that keeps the corners; a column standing in the wall leaves a round bite, closed only
    within the column's disc, so a doorway recess of the same width stays."""
    d = CLOSE * scale
    g = valid(biggest(face.buffer(d, join_style='mitre').buffer(-d, join_style='mitre')), face)
    if COLUMNS is not None:
        near = [COLUMNS.geometries[i] for i in COLUMNS.query(face.buffer(1.0))]
        near = [c for c in near if c.distance(face) < 1.0]
        if near:
            D = BITE * scale
            closed = valid(biggest(face.buffer(D, join_style='mitre').buffer(-D, join_style='mitre')), face)
            bites = closed.intersection(unary_union([c.buffer(1.0) for c in near]))
            if not bites.is_empty:
                g = valid(biggest(unary_union([g, bites]).buffer(0)), g)
    g = Polygon(g.exterior)
    return g if g.is_valid and g.area >= face.area else face


def tidy_outline(building, scale, discs):
    """The building without the drafting along its facade: strokes poking out or in (the door
    chords of the entrances, the mullion boxes, lines overshooting a corner) are narrower than
    any part of a building and go with a mitred closing and opening, which keep the corners;
    a column standing in the facade bulges out by its radius and goes only within its disc."""
    d = OUTLINE_SMOOTH * scale

    def pieces(g):
        return [p for p in (g.geoms if hasattr(g, 'geoms') else [g]) if not p.is_empty and p.area > 0]

    def jog(p):  # nowhere wider than twice the smoothing and no longer than a bay: a jog, not a channel or a court
        x0, y0, x1, y1 = p.bounds
        return math.hypot(x1 - x0, y1 - y0) <= OUTLINE_JOG * scale and p.buffer(-(d + 0.1)).is_empty
    # a closing fills the jogs cut into the facade, an opening drops the ones sticking out;
    # only the jogs are taken, so a court reached through a narrow passage (which the closing
    # would turn into a hole and the outline then swallow) stays outside, and so does the
    # channel between the facade and a canopy standing in front of it
    parts = [p for p in pieces(building) if p.area > 1]
    closed = building.buffer(d, join_style='mitre').buffer(-d, join_style='mitre')
    fills = [p for p in pieces(closed.difference(building)) if jog(p) and sum(q.intersects(p.buffer(0.1)) for q in parts) == 1]
    g = unary_union([building] + fills) if fills else building
    # a fill that closes the passage into a court makes the court a hole, which the outline
    # (the outer ring) would swallow: fills touching a hole that was not one before are dropped
    old_holes = unary_union([Polygon(r) for p in pieces(building) for r in p.interiors]) if any(p.interiors for p in pieces(building)) else Polygon()
    new_holes = [Polygon(r) for p in pieces(g) for r in p.interiors if not old_holes.buffer(0.1).contains(Polygon(r).representative_point())]
    if new_holes:
        court = unary_union(new_holes).buffer(0.2)
        fills = [f for f in fills if not f.intersects(court)]
        g = unary_union([building] + fills) if fills else building
    opened = g.buffer(-d, join_style='mitre').buffer(d, join_style='mitre')
    cuts = [p for p in pieces(g.difference(opened)) if jog(p)]
    if cuts:
        g = g.difference(unary_union(cuts))
    if discs and not g.is_empty:
        D = BITE * scale
        slim = g.buffer(-D, join_style='mitre').buffer(D, join_style='mitre')
        bumps = g.difference(slim).intersection(unary_union([c.buffer(1.0) for c in discs]))
        if not bumps.is_empty:
            g = g.difference(bumps)
    return g if not g.is_empty else building


def fit(face, scale, quad=False, boxed=False):
    face = fill_slits(face, scale)
    # a round opening drops the notches narrower than 2 x OPEN: a cabinet or bench drawn
    # against a wall, the door leaf's closure chord, a column's bite
    # ... but a pocket behind a desk that connects through a narrow neck is still the room:
    # the pieces the opening keeps are grown back over the face, so only the thin parts go
    opened = face.buffer(-OPEN * scale).buffer(OPEN * scale)
    pieces = [p for p in (opened.geoms if isinstance(opened, MultiPolygon) else [opened]) if p.area >= POCKET_MIN * scale * scale]
    if pieces:
        kept = unary_union(pieces)
        # the thin parts the opening removed: a neck joining two kept pieces (the gap between
        # a desk and the wall) comes back, a spike touching one piece (a stroke) does not
        thin = face.difference(kept.buffer(0.01))
        necks = [t for t in (thin.geoms if hasattr(thin, 'geoms') else [thin])
                 if not t.is_empty and sum(t.distance(p) < 0.1 for p in pieces) >= 2]
        g = biggest(unary_union([kept] + necks).buffer(0.05).buffer(-0.05))
        g = biggest(face.intersection(g.buffer(OPEN * scale + 0.6)))
        g = biggest(g.buffer(-1.0 * scale).buffer(1.0 * scale))
    else:
        g = face
    if g.is_empty or g.area < 0.5 * face.area:
        g = face
    if GROW:
        g = biggest(g.buffer(GROW * scale, join_style='mitre', mitre_limit=3.0))
    g = valid(merge_collinear(biggest(g.simplify(SIMPLIFY * scale))), face)
    if g.area <= 0 or len(g.exterior.coords) < 4:
        return face
    # most rooms have four walls, not always at right angles: four lines fitted through the
    # boundary replace a notched or many-cornered shape when they still cover the room and
    # fill nothing bigger than a notch (a credenza against the wall, a column's bite). A
    # bowed wall (a curved facade, the kitchen's bay) leaves far more outside and keeps its
    # traced curve.
    rect = g.minimum_rotated_rectangle
    if boxed:
        return rect if rect.area > 0 else g
    def fits(cand):
        if cand is None or cand.area <= 0:
            return False
        covers = largest_piece(g.difference(cand)) <= SLIVER_MAX * scale * scale
        filled = cand.difference(g)
        fills = largest_piece(filled) <= max(NOTCH_MAX, min(NOTCH_SHARE * g.area, NOTCH_CAP)) * scale * scale and filled.area <= NOTCH_TOTAL * g.area
        return covers and fills
    # the rectangle first (it is the exact answer for most rooms), four fitted walls for the
    # rooms whose walls are not at right angles
    if fits(rect):
        return rect
    four = four_walls(g, scale)
    if fits(four):
        return four
    if quad and four is not None:  # four walls by the floor config: one of them may bow
        return bowed_walls(four, g, scale)
    # the simplest polygon that still is the room: coarser tolerances while the shape holds
    for tol in (1.0, 2.0, 3.0, 4.0):
        s = valid(biggest(g.simplify(tol * scale)), g)
        if iou(s, g) >= 0.97 and len(s.exterior.coords) < len(g.exterior.coords):
            g = s
    return g


POCKETS_TAKEN = set()  # ids of faces absorbed into a room as furniture pockets


def absorb_pockets(faces, owners, tree, ext_ids, scale, max_room, ext_geoms=None, furniture=None):
    """{owner key: room face grown over its pockets}. A pocket is an unlabelled face below
    POCKET_MAX that touches (across a stroke) one labelled room and no other face of room
    size, and holds furniture: the inside of a desk, a cabinet, a bench drawn against the
    wall. An empty cavity (a chase, a wedge behind a partition) stays out of the room.
    `ext_geoms` maps an exterior face to its true shape (the building is a hole in it; the
    hole-filled face would touch everything); `furniture` is an STRtree of furniture points."""
    # a pocket touches its room across a single stroke (3 pt painted); a wall is two strokes
    # and wider, so neighbours across a wall do not count
    reach = 2 * BUF * scale + 0.3
    labelled = {id(f): key for key, (f, _) in owners.items()}
    ext_geoms = ext_geoms or {}
    out = {}
    for f in faces:
        if id(f) in labelled or id(f) in ext_ids or f.area > POCKET_MAX * scale * scale:
            continue
        if furniture is not None and not any(f.contains(furniture.geometries[i]) for i in furniture.query(f)):
            continue
        zone = f.buffer(reach)
        touching = [faces[i] for i in tree.query(zone) if faces[i] is not f and ext_geoms.get(id(faces[i]), faces[i]).intersects(zone)]
        rooms_touched = {labelled[id(t)] for t in touching if id(t) in labelled}
        big_touched = [t for t in touching if id(t) not in labelled and (t.area >= POCKET_MAX * scale * scale or id(t) in ext_ids)]
        if len(rooms_touched) != 1 or big_touched:
            continue
        key = rooms_touched.pop()
        out.setdefault(key, []).append(f)
        POCKETS_TAKEN.add(id(f))
    grown = {}
    for key, pockets in out.items():
        f = owners[key][0]
        g = unary_union([f.buffer(reach / 2 + 0.1)] + [p.buffer(reach / 2 + 0.1) for p in pockets]).buffer(-(reach / 2 + 0.1))
        g = biggest(g)
        grown[key] = Polygon(g.exterior) if not g.is_empty and g.area > f.area else f
    return grown


def largest_piece(g):
    """Area of the largest connected piece of a geometry."""
    if g.is_empty:
        return 0.0
    return max(p.area for p in (g.geoms if hasattr(g, 'geoms') else [g]))


def four_walls(g, scale):
    """Four walls fitted to the shape: boundary points are assigned to the nearest side of the
    minimum rectangle, a line is fitted through each side's points (outliers, such as a notch,
    dropped once), and the corners are the intersections of neighbouring lines. None when a
    side has too few points or two lines run parallel."""
    rect = g.minimum_rotated_rectangle
    if rect.area <= 0 or len(rect.exterior.coords) != 5:
        return None
    R = np.array(rect.exterior.coords[:-1], float)
    sides = [LineString([R[i], R[(i + 1) % 4]]) for i in range(4)]
    boundary = g.exterior
    ts = np.arange(0, boundary.length, 2.0 * scale)
    P = np.array([boundary.interpolate(t).coords[0] for t in ts])
    if len(P) < 12:
        return None
    which = np.argmin([[side.distance(Point(p)) for side in sides] for p in P], axis=1)
    # the opening rounded the corners: points near a rectangle corner belong to no wall
    near_corner = np.array([min(math.dist(p, c) for c in R) <= CORNER_ZONE * scale for p in P])
    centre = np.array(g.centroid.coords[0])
    lines = []
    for k in range(4):
        Q = P[(which == k) & ~near_corner]
        if len(Q) < 3:
            return None
        # the wall is the outermost run of points: anything standing well inside the fitted
        # line (a credenza, a bench, the door leaf) is dropped and the line fitted again
        for _ in range(3):
            c = Q.mean(0)
            u = np.linalg.svd(Q - c)[2][0]
            nrm = np.array([-u[1], u[0]])
            if np.dot(nrm, c - centre) < 0:
                nrm = -nrm  # pointing out of the room
            depth = (Q - c) @ nrm
            keep = depth >= -FIT_OUTLIER * scale
            if keep.sum() < 3 or keep.all():
                break
            Q = Q[keep]
        lines.append((c, u, (Q @ u).max() - (Q @ u).min()))
    out = []
    for k in range(4):
        (c1, u1, _), (c2, u2, _) = lines[k - 1], lines[k]
        A = np.array([u1, -u2]).T
        if abs(np.linalg.det(A)) < 1e-3:
            return None
        t = np.linalg.solve(A, c2 - c1)
        out.append(c1 + u1 * t[0])
    # every wall must be supported by points along most of its length: a three-walled room
    # gives the rectangle a fourth side with almost no points, and the corner shoots off
    for k in range(4):
        side = np.linalg.norm(out[(k + 1) % 4] - out[k])
        if side < 4.0 * scale or lines[k][2] < WALL_SUPPORT * side:
            return None
    q = Polygon(out)
    return q if q.is_valid and q.area > 0 else None


def bowed_walls(four, g, scale):
    """A four-walled polygon whose walls take an arc where the traced boundary lies on a
    circle that bows away from the straight wall (the social kitchen's bay). Furniture
    standing against the wall pushes boundary points into the room; those are dropped from
    the circle fit. The corners of a bowed wall move onto its circle along the neighbouring
    walls; the result is a polygon as vertices, with a bulge on each bowed wall."""
    corners = [np.array(p, float) for p in four.exterior.coords[:-1]]
    centroid = np.array(g.centroid.coords[0])
    boundary = g.exterior
    ts = np.arange(0, boundary.length, 2.0 * scale)
    P = np.array([boundary.interpolate(t).coords[0] for t in ts])
    chords = [LineString([corners[i], corners[(i + 1) % 4]]) for i in range(4)]
    nearest = np.argmin([[ch.distance(Point(p)) for ch in chords] for p in P], axis=1)
    arcs = {}
    for i in range(4):
        a, b = corners[i], corners[(i + 1) % 4]
        d = b - a
        L = np.linalg.norm(d)
        if L < 1e-6:
            continue
        u, nrm = d / L, np.array([-d[1], d[0]]) / L
        along = (P - a) @ u
        sag = (P - a) @ nrm
        on = (nearest == i) & (along > 0.05 * L) & (along < 0.95 * L) & (np.abs(sag) <= min(0.2 * L, BOW_REACH * scale))
        Q = P[on]
        if len(Q) < 10:
            continue
        ok = None
        for _ in range(4):
            (cx, cy), r, res = fit_circle(Q)
            if r < L / 2 or r > 20 * L:
                break
            radial = np.hypot(Q[:, 0] - cx, Q[:, 1] - cy) - r
            room_side = np.sign(np.hypot(*(centroid - [cx, cy])) - r) or 1.0
            inward = radial * room_side > FIT_OUTLIER * scale  # standing in the room, off the wall
            if not inward.any():
                ok = ((cx, cy), r, res, Q)
                break
            if (~inward).sum() < 10:
                break
            Q = Q[~inward]
        if ok is None:
            continue
        (cx, cy), r, res, Q = ok
        span = (Q @ u).max() - (Q @ u).min()
        if res > BOW_RES * scale or span < 0.6 * L:
            continue
        sagitta = r - math.sqrt(max(r * r - L * L / 4, 0))
        if sagitta < CURVE_SAG * scale:
            continue
        arcs[i] = ((cx, cy), r)
    if not arcs:
        return [[round(float(x), 1), round(float(y), 1)] for x, y in corners]
    # corners next to an arc slide along the straight neighbour onto the circle
    moved = list(corners)
    for i, ((cx, cy), r) in arcs.items():
        for j, k in ((i, (i - 1) % 4), ((i + 1) % 4, (i + 1) % 4)):  # corner index, straight wall index
            if k in arcs:
                continue
            c = corners[j]
            far = corners[k] if k != j else corners[(k + 1) % 4]  # the far end of the straight wall
            v = c - far
            n = np.linalg.norm(v)
            if n < 1e-6:
                continue
            v /= n
            oc = far - np.array([cx, cy])
            bq = 2 * np.dot(oc, v)
            cq = np.dot(oc, oc) - r * r
            disc = bq * bq - 4 * cq
            if disc < 0:
                continue
            roots = [(-bq + sq) / 2 for sq in (math.sqrt(disc), -math.sqrt(disc))]
            t = min(roots, key=lambda t: abs(t - n))
            if abs(t - n) <= 0.5 * n:
                moved[j] = far + v * t
    out = []
    for i in range(4):
        x, y = moved[i]
        if i in arcs:
            (cx, cy), r = arcs[i]
            a, b = moved[i], moved[(i + 1) % 4]
            L = np.linalg.norm(b - a)
            theta = 2 * math.asin(min(1.0, L / (2 * r)))
            bulge = math.tan(theta / 4)
            # the map bows a positive bulge to the right of travel (y down): the sign that puts
            # the arc's midpoint on the far side from the circle's centre
            d = b - a
            nrm = np.array([-d[1], d[0]]) / (L or 1.0)
            mid = (a + b) / 2
            towards_centre = np.dot(nrm, np.array([cx, cy]) - mid)
            bulge = bulge if towards_centre < 0 else -bulge
            out.append([round(float(x), 1), round(float(y), 1), round(float(bulge), 4)])
        else:
            out.append([round(float(x), 1), round(float(y), 1)])
    return out


def wall_axis(poly, wall_tree, segs, scale):
    """The direction (degrees, in (-45, 45]) of the walls drawn in and around a region: the
    length-weighted mean direction of the wall strokes within its reach, taken modulo 90°
    (a core's walls stand at right angles; the X marks on a shaft and the stall partitions
    are short and cancel out). None when there is too little wall to tell."""
    zone = poly.buffer(4.0 * scale)
    hits = [segs[i] for i in wall_tree.query(zone) if segs[i].length >= 6.0 * scale and segs[i].intersects(zone)]
    if sum(s.length for s in hits) < 40.0 * scale:
        return None
    cx = cy = 0.0
    for s in hits:
        (x0, y0), (x1, y1) = s.coords[0], s.coords[-1]
        a = 4 * math.atan2(y1 - y0, x1 - x0)
        cx += s.length * math.cos(a)
        cy += s.length * math.sin(a)
    return round(math.degrees(math.atan2(cy, cx)) / 4, 2)


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


def desks(geom, scale, zones):
    """Worksurface quads standing in the open areas (`zones`); the furniture of an enclosed
    room is not drawn."""
    if zones.is_empty:
        return []
    zone = zones.buffer(DESK_REACH * scale)
    out = []
    for q in geom.get('quads', []):
        pts, width, black = q[:4], q[4], q[5]
        if not black or width < DESK_WIDTH:
            continue
        sides = [math.dist(pts[i], pts[(i + 1) % 4]) for i in range(4)]
        s, l = min(sides), max(sides)
        if not (DESK_SHORT[0] * scale <= s <= DESK_SHORT[1] * scale and DESK_LONG[0] * scale <= l <= DESK_LONG[1] * scale):
            continue
        if zone.contains(Point(sum(p[0] for p in pts) / 4, sum(p[1] for p in pts) / 4)):
            out.append([[round(x, 1), round(y, 1)] for x, y in pts])
    return out


def align_walls(rooms, scale):
    """Walls of rooms standing in a row, on one line. Every room's rectangle is fitted on its
    own, so the fronts of a row of offices come out a few tenths of a point and of a degree
    apart. Walls of different rooms that face the same way, run within ALIGN_TURN of parallel,
    lie within ALIGN_TOL of one line and continue each other (across at most ALIGN_GAP) are
    put on their common line, length-weighted; the corners move to the intersections. A room
    is left alone when that changes it by more than a sliver."""
    quads = [r for r in rooms if len(r['polygon']) == 4 and all(len(p) == 2 for p in r['polygon']) and not r.get('holes')]
    edges = []  # (room index, edge index, p, q, outward normal, offset, start, end along the direction)
    for ri, r in enumerate(quads):
        P = np.array(r['polygon'], float)
        poly = Polygon(P)
        if not poly.is_valid or poly.area <= 0:
            continue
        c = np.array(poly.centroid.coords[0])
        for k in range(4):
            p, q = P[k], P[(k + 1) % 4]
            d = q - p
            L = np.linalg.norm(d)
            if L < 1e-6:
                continue
            u = d / L
            n = np.array([-u[1], u[0]])
            if np.dot(n, (p + q) / 2 - c) < 0:
                n = -n
            edges.append((ri, k, p, q, n, float(np.dot(n, p)), L))
    parent = list(range(len(edges)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    cos_turn = math.cos(math.radians(ALIGN_TURN))
    for i in range(len(edges)):
        ri, _, p1, q1, n1, o1, _ = edges[i]
        u1 = np.array([n1[1], -n1[0]])
        a1 = sorted((np.dot(u1, p1), np.dot(u1, q1)))
        for j in range(i + 1, len(edges)):
            rj, _, p2, q2, n2, o2, _ = edges[j]
            if rj == ri or np.dot(n1, n2) < cos_turn:
                continue
            if abs(np.dot(n1, p2) - o1) > ALIGN_TOL * scale or abs(np.dot(n1, q2) - o1) > ALIGN_TOL * scale:
                continue
            a2 = sorted((np.dot(u1, p2), np.dot(u1, q2)))
            if a2[0] > a1[1] + ALIGN_GAP * scale or a1[0] > a2[1] + ALIGN_GAP * scale:
                continue
            parent[find(i)] = find(j)
    groups = {}
    for i in range(len(edges)):
        groups.setdefault(find(i), []).append(i)
    line_of = {}  # edge index -> (point on the line, unit normal)
    for members in groups.values():
        if len({edges[i][0] for i in members}) < 2:
            continue
        n = sum(edges[i][4] * edges[i][6] for i in members)
        n /= np.linalg.norm(n)
        o = sum(np.dot(n, (edges[i][2] + edges[i][3]) / 2) * edges[i][6] for i in members) / sum(edges[i][6] for i in members)
        for i in members:
            line_of[i] = (n * o, n)
    moved = 0
    by_room = {}
    for i, e in enumerate(edges):
        by_room.setdefault(e[0], {})[e[1]] = i
    for ri, ks in by_room.items():
        if len(ks) < 4 or not any(ks[k] in line_of for k in ks):
            continue
        lines = []
        for k in range(4):
            e = edges[ks[k]]
            if ks[k] in line_of:
                lines.append(line_of[ks[k]])
            else:
                lines.append((e[2], e[4]))
        corners = []
        for k in range(4):
            (c1, n1), (c2, n2) = lines[k - 1], lines[k]
            A = np.array([n1, n2])
            if abs(np.linalg.det(A)) < 1e-6:
                break
            corners.append(np.linalg.solve(A, [np.dot(n1, c1), np.dot(n2, c2)]))
        if len(corners) < 4:
            continue
        old = Polygon(quads[ri]['polygon'])
        new = Polygon(corners)
        if new.is_valid and new.area > 0 and iou(old, new) >= 0.97:
            quads[ri]['polygon'] = [[round(float(x), 1), round(float(y), 1)] for x, y in corners]
            moved += 1
    return moved


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
    ext_geoms = {id(f): p for f, p in exterior}
    outside = unary_union([p for _, p in exterior]) if exterior else Polygon()
    global COLUMNS
    discs = [Point(cx, cy).buffer(r + 0.5) for cx, cy, r in w['columns']]
    COLUMNS = STRtree(discs) if discs else None
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
            poly = cfg['hand'][rid]
            name = lab['name']
            if isinstance(poly, tuple):
                name, poly = poly
            rooms.append({'id': rid, 'name': name, 'kind': 'room', 'polygon': [[float(x), float(y)] for x, y in poly], 'hand': True})
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
    # a desk or cabinet drawn against a wall encloses a pocket of its own: a small face that
    # touches exactly one room (and nothing else of room size) is part of that room
    furniture = [Point(sum(p[0] for p in q[:4]) / 4, sum(p[1] for p in q[:4]) / 4) for q in geom.get('quads', [])]
    furniture += [Point((s[0] + s[2]) / 2, (s[1] + s[3]) / 2) for s in geom['segs'] if s[5] and s[7]]  # black, furniture-flagged
    pockets = absorb_pockets(faces, owners, tree, ext_ids, scale, max_room, ext_geoms, STRtree(furniture) if furniture else None)
    for key in list(owners):
        f, labs = owners[key]
        if key in pockets:
            owners[key] = (pockets[key], labs)
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
            room = {'id': rid, 'name': lab['name'], 'kind': 'room', 'area': int(part.area),
                    'polygon': shape(part, scale, quad=rid in cfg['quad'], boxed=rid in cfg['box'])}
            if len(labs) > 1:
                room['shared'] = [l['id'] for l in labs if l is not lab]
            rooms.append(room)
    # hand polygons whose room has no label on this sheet (the Lower Level's teaching rooms,
    # the lecture halls) carry their name in the config: ('name', polygon)
    drawn_ids = {r['id'] for r in rooms}
    for rid, poly in cfg['hand'].items():
        if rid in drawn_ids:
            continue
        if isinstance(poly, tuple):
            name, poly = poly
            rooms.append({'id': rid, 'name': name, 'kind': 'room', 'polygon': [[float(x), float(y)] for x, y in poly], 'hand': True})
        else:
            print(f'  hand polygon for {rid}: no such label')
    for r in rooms:
        if r.get('hand'):
            r['area'] = int(Polygon(flatten(r['polygon'])).area)
            del r['hand']
    # a boxed room (a lab whose benches are drawn as walls) is its minimum rectangle, which
    # may reach over a neighbour: it gives up whatever another room already covers
    others = {r['id']: Polygon(flatten(r['polygon'])).buffer(0) for r in rooms}
    for r in rooms:
        if r['id'] not in cfg['box']:
            continue
        g = others[r['id']]
        for oid, og in others.items():
            if oid != r['id'] and oid not in cfg['box'] and g.intersects(og) and g.intersection(og).area > 2:
                g = biggest(g.difference(og.buffer(0.5)))
        if g is not others[r['id']]:
            r['polygon'] = ring(g)
            others[r['id']] = g
    # patch areas: the polygon clipped to the free space of the label's face (an open office
    # in the corridor network, a booth whose label stands outside its open front), minus the
    # rooms already placed. Open-plan kinds carry the 'open plan' tag; a booth is a room.
    placed = Polygon()
    for lab, f in patched:
        rid = lab['id']
        kind = 'open' if category(lab['name'], rid) in OPEN_KINDS else 'room'
        drawn = patches['areas'][rid]
        g = Polygon(flatten(drawn)).buffer(0)
        if kind == 'open':  # an open-plan area stops at the walls and at the rooms standing in it
            g = g.intersection(inside.buffer(BUF * scale, join_style='mitre'))
        g = biggest(g.difference(placed))
        if g.is_empty:
            print(f'  {rid}: patch area lies outside its face')
            continue
        # a traced room reaching over the area (a lab box whose open side faces a workspace)
        # gives the area up: it becomes a hole in, or a bite out of, that room
        for r in rooms:
            rg = Polygon(flatten(r['polygon']), [flatten(h) for h in r.get('holes', [])]).buffer(0)
            if rg.intersects(g) and rg.intersection(g).area > 0.5 * g.area:
                cut = biggest(rg.difference(g))
                r['polygon'] = ring(cut)
                holes = [[[round(float(x), 1), round(float(y), 1)] for x, y in h.coords[:-1]] for h in cut.interiors if Polygon(h).area >= 20]
                if holes:
                    r['holes'] = holes
                elif 'holes' in r:
                    del r['holes']
        # a room drawn by hand keeps its vertices (and arcs) as given; an open area takes the clip
        poly = [list(pt) for pt in drawn] if kind == 'room' and g.area >= 0.95 * Polygon(flatten(drawn)).area else ring(g)
        room = {'id': rid, 'name': lab['name'], 'kind': kind, 'area': int(g.area), 'polygon': poly}
        holes = [[[round(float(x), 1), round(float(y), 1)] for x, y in h.coords[:-1]] for h in g.interiors if Polygon(h).area >= 20]
        if holes and kind == 'open':
            room['holes'] = holes
        rooms.append(room)
        placed = placed.union(g)
    for lab, f in open_labels:
        if category(lab['name'], lab['id']) != 'circulation':
            print(f"  {lab['id']} {lab['name']!r}: label in the open (face {int(f.area)} pt²), no patch area")
    aligned = align_walls(rooms, scale)
    # the building: the border minus the outside; its boundary is the outline
    building = box(*BORDER).difference(outside).buffer(-BUF * scale, join_style='mitre', mitre_limit=2.0)  # back to the strokes' centres
    building = tidy_outline(building, scale, discs)
    pieces = sorted((list(building.geoms) if isinstance(building, MultiPolygon) else [building]), key=lambda p: -p.area)
    # a piece of the building holds rooms; the legend box and the north arrow do not
    room_points = [Point(Polygon(flatten(r['polygon'])).representative_point()) for r in rooms if len(r['polygon']) >= 3]
    pieces = [p for p in pieces if p.area >= max_room / 10 and any(p.contains(q) for q in room_points)]
    # a fine tolerance keeps the corners and leaves the curved facades enough vertices for arcs
    outlines = [ring(merge_collinear(valid(biggest(Polygon(p.exterior).simplify(OUTLINE_TOL * scale)), Polygon(p.exterior))),
                     arcs=True, tol=OUTLINE_ARC_TOL, dev=OUTLINE_ARC_DEV, min_iou=0.995) for p in pieces]
    # faces nobody labelled: cores, restrooms, stairs, closets, for floors.py's `named` list
    labelled = set(owners)
    min_room = cfg['min_room'] if 'min_room' in cfg else MIN_ROOM * scale * scale  # a configured minimum is in the sheet's own points
    spare = [f for f in faces if id(f) not in labelled and id(f) not in ext_ids and id(f) not in POCKETS_TAKEN and f.area <= max_room
             and not any(f.contains(Point(l['x'], l['y'])) for l, _ in open_labels + patched)]
    # Hatched floors, stair treads, elevator X marks and stall partitions chop a core into
    # cells: cells below room size that touch across a stroke are merged back together and
    # into the room-sized face they touch (the stalls into the restroom); room-sized faces
    # never merge with each other (the shafts of a bank stay apart).
    reach = BUF * scale + CELL_GAP
    small = [f for f in spare if f.area < min_room * CELL_MAX]
    big = [f for f in spare if f.area >= min_room * CELL_MAX]
    merged = []
    blobs = []
    if small:
        joined = unary_union([f.buffer(reach) for f in small])
        blobs = list(joined.geoms) if isinstance(joined, MultiPolygon) else [joined]
    big_tree = STRtree(big)
    taken = set()
    grown = {id(f): [f] for f in big}
    for k, blob in enumerate(blobs):
        hits = [big[i] for i in big_tree.query(blob) if big[i].intersects(blob)]
        if hits:  # the blob joins the room-sized face it touches most
            host = max(hits, key=lambda f: f.intersection(blob).area)
            grown[id(host)].append(Polygon(blob.exterior).buffer(-reach, join_style='mitre'))
            taken.add(k)
    for f in big:
        parts = [p for p in grown[id(f)] if not p.is_empty]
        g = f if len(parts) == 1 else biggest(unary_union([p.buffer(reach / 2 + 0.1) for p in parts]).buffer(-(reach / 2 + 0.1)))
        merged.append(Polygon(g.exterior) if not g.is_empty else f)
    for k, blob in enumerate(blobs):
        if k in taken:
            continue
        g = biggest(Polygon(blob.exterior).buffer(-reach, join_style='mitre'))
        if not g.is_empty and g.area >= min_room:
            merged.append(g)
    unl = []
    for f in merged:
        if f.area < min_room:
            continue
        c = f.representative_point()
        unl.append({'area': int(f.area), 'x': round(c.x, 1), 'y': round(c.y, 1), 'polygon': shape(f, scale)})
    # a patch area for a named region (a restroom, a shaft, a stair, by the id floors.py
    # names it) is that region, drawn as given; whatever was traced inside it goes
    number_re = re.compile(cfg['number_re'])
    label_ids = {l['id'] for l in labels(geom, cfg)}
    for rid, drawn in patches['areas'].items():
        if number_re.match(rid) or rid in label_ids:
            continue
        g = Polygon(flatten(drawn)).buffer(0)
        if g.is_empty or rid == 'terrace':
            continue
        unl = [u for u in unl if g.intersection(Polygon(flatten(u['polygon'])).buffer(0)).area <= 0.5 * u['area']]
        c = g.representative_point()
        unl.append({'area': int(g.area), 'x': round(c.x, 1), 'y': round(c.y, 1), 'polygon': [list(pt) for pt in drawn], 'named': rid})
    ell = atrium_polygon(cfg)
    if ell is not None:
        # the stairs winding down inside the atrium's rail chop the opening into pieces: the
        # configured ellipse replaces whatever was traced inside it
        unl = [u for u in unl if not ell.contains(Point(u['x'], u['y']))]
        c = ell.centroid
        unl.append({'area': int(ell.area), 'atrium': True, 'x': round(c.x, 1), 'y': round(c.y, 1), 'polygon': ring(ell)})
    # a roof terrace (floor 5): the paved decks holding the configured seeds, one open area
    # around the indoor blocks (which become its holes)
    if cfg['terrace'] and 'terrace' in patches['areas']:
        # the deck as drawn in the patch file; the blocks standing on it (the rooms and
        # regions inside, with their walls) are its holes
        drawn = patches['areas']['terrace']
        deck = Polygon(flatten(drawn)).buffer(0)
        # the merged paver cells are not regions to name (a block's rooms are far smaller)
        unl = [u for u in unl if u.get('atrium') or u.get('named') or not (deck.contains(Point(u['x'], u['y'])) and u['area'] > DECK_BLOB * scale * scale)]
        inside = [Polygon(flatten(r['polygon'])).buffer(0) for r in rooms if deck.contains(Point(Polygon(flatten(r['polygon'])).representative_point()))]
        inside += [Polygon(flatten(u['polygon'])).buffer(0) for u in unl if deck.contains(Point(u['x'], u['y']))]
        blocks = unary_union([b.buffer(WALL * scale, join_style='mitre') for b in inside]) if inside else Polygon()
        room = {'id': 'terrace', 'name': 'ROOF TERRACE', 'kind': 'open', 'area': int(deck.difference(blocks).area), 'polygon': [list(pt) for pt in drawn]}
        holes = []
        for b in (blocks.geoms if isinstance(blocks, MultiPolygon) else ([blocks] if not blocks.is_empty else [])):
            b = b.intersection(deck)
            for piece in (b.geoms if hasattr(b, 'geoms') else [b]):
                if piece.area >= 200:
                    holes.append(ring(piece.simplify(SIMPLIFY * scale)))
        if holes:
            room['holes'] = holes
        rooms.append(room)
    elif cfg['terrace']:
        # the pavers' hatching chops the deck into cells: the cells joined across their
        # strokes form the deck, and a seed on any paver takes the whole deck it stands on
        reach = BUF * scale + CELL_GAP
        cells = [f for f in faces if id(f) not in ext_ids and f.area < DECK_CELL * scale * scale]
        joined = unary_union([f.buffer(reach) for f in cells]) if cells else Polygon()
        blobs = list(joined.geoms) if isinstance(joined, MultiPolygon) else ([joined] if not joined.is_empty else [])
        decks = []
        for sx, sy in cfg['terrace']:
            p = Point(sx, sy)
            hit = [b for b in blobs if b.contains(p)]
            if hit:
                decks.append(Polygon(max(hit, key=lambda b: b.area).exterior).buffer(-reach, join_style='mitre'))
            else:
                hit = [f for f in faces if id(f) not in ext_ids and f.contains(p)]
                if hit:
                    decks.append(min(hit, key=lambda f: f.area))
        if decks:
            deck = unary_union(decks)
            deck = biggest(deck) if isinstance(deck, MultiPolygon) else deck
            unl = [u for u in unl if not deck.buffer(reach).contains(Point(u['x'], u['y']))]  # paver cells are not regions to name
            # the blocks standing on the deck: everything the deck's outer ring encloses but the deck
            outer = Polygon(deck.exterior)
            room = {'id': 'terrace', 'name': 'ROOF TERRACE', 'kind': 'open', 'area': int(deck.area), 'polygon': ring(outer.simplify(SIMPLIFY * scale), arcs=True)}
            holes = [[[round(float(x), 1), round(float(y), 1)] for x, y in Polygon(h).simplify(SIMPLIFY * scale).exterior.coords[:-1]] for h in deck.interiors if Polygon(h).area >= 200]
            if holes:
                room['holes'] = holes
            rooms.append(room)
            for f in decks:
                ext_ids.add(id(f))  # the deck is not a region to name
    # entrances: door hinges on the outline
    exits = []
    if cfg['exits'] and outlines:
        conts = [Polygon(flatten(o)).exterior for o in outlines]
        for cx, cy, r, p0, p1 in w['doors']:
            mx, my = (p0[0] + p1[0]) / 2 - cx, (p0[1] + p1[1]) / 2 - cy
            n = math.hypot(mx, my) or 1.0
            mid = (cx + r * mx / n, cy + r * my / n)
            at = ((mid[0] + cx) / 2, (mid[1] + cy) / 2)
            d = min(c.distance(Point(at)) for c in conts)
            if d <= EXIT_DIST * scale and all(math.dist(at, e) > 40 * scale for e in exits):
                exits.append([round(at[0], 1), round(at[1], 1)])
    # the walls' direction around every region, for the emitter to square the cores to
    # (a shaft's X marks and a restroom's stalls mislead a fit to the region's own outline)
    segs = [LineString([(a, b), (c, e)]) for a, b, c, e in w['walls']]
    wall_tree = STRtree(segs)
    for u in unl:
        ax = wall_axis(Polygon(flatten(u['polygon'])), wall_tree, segs, scale)
        if ax is not None:
            u['axis'] = ax
    open_zones = unary_union([Polygon(flatten(r['polygon']), [flatten(h) for h in r.get('holes', [])]).buffer(0)
                              for r in rooms if r['kind'] == 'open' and len(r['polygon']) >= 3])
    out = {'floor': fid, 'rooms': rooms, 'outlines': outlines, 'unlabelled': unl, 'exits': exits, 'desks': desks(geom, scale, open_zones)}
    json.dump(out, open(prefix + '_rooms.json', 'w'))
    n_open = sum(r['kind'] == 'open' for r in rooms)
    print(f"floor {fid}: {len(rooms) - n_open} enclosed rooms, {n_open} open areas ({len(open_labels)} labels in the open), "
          f"{len(outlines)} outline(s), {len(unl)} unlabelled regions, {len(exits)} exits, {len(out['desks'])} desks, "
          f"{aligned} rooms aligned with their neighbours")
    return out


if __name__ == '__main__':
    build(sys.argv[1], sys.argv[2])
