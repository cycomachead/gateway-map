"""Segment rooms from the extracted CAD geometry of one floor.

Usage: python3 rooms.py <floor> <geom.json> <out_prefix>

1. Rasterise the "architectural" line work: black strokes longer than MIN_LINE points and
   black bezier arcs with a chord longer than MIN_CURVE (door swings; they seal doorways so
   rooms become closed regions). Short strokes are furniture, hatching and text outlines.
   Structural columns (small circles at wall junctions) are painted as solid discs, since the
   walls stop at their face and the disc is what joins them.
2. Read the room labels (a 4-digit number plus the name lines next to it). Labels usually sit
   in the corridor just outside the room's door, so flood-fill first from the label itself and,
   if that leaks into the corridor network, from just beyond the nearest door swing arc (the
   arc bulges into the room). An enclosed region becomes the room polygon; it is re-traced on
   a furniture-free raster and the door swings (rasterised as walls so the rooms close) are
   added back, so the door is simply part of the room. Every polygon is then straightened: the
   simplest corner count (4, 5, 6, 8) whose line-fitted walls still cover the region, or, for
   irregular shapes and the outline, line-fitted straight runs with finely traced curves.
   Rooms listed in the floor's `box` are reduced to their minimum-area bounding rectangle
   (labs whose internal lines are not walls).
3. Labels whose fill leaks into the corridor network are "open" areas: the unenclosed free
   space, on the furniture-free raster, is partitioned between them by geodesic distance
   (watershed). Desks (bold quads of worksurface size) standing in an open area are exported
   so the map can draw them.
4. The exterior is the fill from the sheet corner; the building outline is the outer contour
   of the components (containing labels) that are not exterior.
Writes <out_prefix>_rooms.json and a debug overlay <out_prefix>_debug.png.
"""
import json
import os
import re
import sys

import cv2
import numpy as np
from scipy.ndimage import gaussian_filter1d
import shapely
from shapely import snap
from shapely.geometry import MultiPolygon, Point, Polygon
from skimage.segmentation import watershed

import sign
from floors import category

HERE = os.path.dirname(os.path.abspath(__file__))
SCALE = 1.0          # raster pixels per PDF point
MIN_LINE = 2.0       # points; the walls are drawn from short pieces, so keep almost everything
MIN_CURVE = 14.0     # points (chord); shorter arcs are chairs, not door swings
PLAN_X_MAX = 3230    # title block starts here
BORDER = (72.0, 54.0, 3424.2, 2538.0)
LABEL_SIZES = (3.5, 5.0)
NUMBER_RE = re.compile(r'^(\d{4}[A-Z]?|\dCORR\d{2})$')
IGNORE_NAMES = {'FEC', 'UP', 'DN', 'DOWN', 'RAMP', 'OPEN TO BELOW', 'WAP', 'Side A', 'Side B', 'Side C', 'Side D', '?'}


def bezier(p, n=12):
    t = np.linspace(0, 1, n)[:, None]
    p = np.asarray(p, float)
    return ((1 - t) ** 3) * p[0] + 3 * ((1 - t) ** 2) * t * p[1] + 3 * (1 - t) * t ** 2 * p[2] + t ** 3 * p[3]


def on_border(x0, y0, x1, y1):
    bx0, by0, bx1, by1 = BORDER
    same_x = abs(x0 - x1) < 0.5 and (abs(x0 - bx0) < 1 or abs(x0 - bx1) < 1)
    same_y = abs(y0 - y1) < 0.5 and (abs(y0 - by0) < 1 or abs(y0 - by1) < 1)
    return same_x or same_y


def raster(geom, scale=SCALE, min_line=MIN_LINE, min_curve=MIN_CURVE, extra=(), furniture=True, arcs=(), columns=()):
    """Line-work raster (255 = stroke). With furniture=False only walls (single strokes and
    long paths) plus the given door arcs are drawn; room polygons are traced on that one so
    desks against a wall do not notch them. `columns` (cx, cy, r) are painted as solid discs."""
    w, h = geom['page']
    img = np.zeros((int(h * scale), int(w * scale)), np.uint8)  # 255 = line work
    s = np.array(geom['segs'])
    length = np.hypot(s[:, 2] - s[:, 0], s[:, 3] - s[:, 1])
    keep = (s[:, 5] == 1) & (length >= min_line)
    if not furniture and s.shape[1] > 7:
        keep &= s[:, 7] == 0
    for x0, y0, x1, y1 in s[keep][:, :4]:
        if on_border(x0, y0, x1, y1) or (x0 > PLAN_X_MAX and x1 > PLAN_X_MAX):
            continue
        cv2.line(img, (int(round(x0 * scale)), int(round(y0 * scale))), (int(round(x1 * scale)), int(round(y1 * scale))), 255, 1)
    if furniture:
        for c in geom['curves']:
            if not c[5]:
                continue
            pts = np.array(c[:4], float)
            if np.hypot(*(pts[3] - pts[0])) < min_curve:
                continue
            cv2.polylines(img, [np.round(bezier(pts) * scale).astype(np.int32)], False, 255, 1)
    for _, _, p in arcs:
        cv2.polylines(img, [np.round(np.asarray(p) * scale).astype(np.int32)], False, 255, 1)
    for cx, cy, r in columns:
        cv2.circle(img, (int(round(cx * scale)), int(round(cy * scale))), int(round(r * scale)), 255, -1)
    for x0, y0, x1, y1 in extra:  # hand-drawn closing strokes
        cv2.line(img, (int(round(x0 * scale)), int(round(y0 * scale))), (int(round(x1 * scale)), int(round(y1 * scale))), 255, 1)
    # Partitions often stop a pixel or two short of the wall they meet; close those gaps
    # (door openings are an order of magnitude wider and survive).
    return cv2.morphologyEx(img, cv2.MORPH_CLOSE, np.ones((CLOSE, CLOSE), np.uint8))


def labels(geom, sizes=LABEL_SIZES, number_re=NUMBER_RE, skip=()):
    """Room labels: [{'id', 'name', 'x', 'y', 'size'}] with the name lines nearest to each number."""
    number_re = re.compile(number_re) if isinstance(number_re, str) else number_re
    lines = [l for l in geom['lines'] if sizes[0] <= l['size'] <= sizes[1] and l['bbox'][0] < PLAN_X_MAX]
    centre = lambda l: ((l['bbox'][0] + l['bbox'][2]) / 2, (l['bbox'][1] + l['bbox'][3]) / 2)
    numbers = [l for l in lines if number_re.match(l['text']) and l['text'] not in skip]
    names = [l for l in lines if not number_re.match(l['text']) and l['text'] not in IGNORE_NAMES and not re.match(r"^\d+'", l['text'])]
    out = [{'id': n['text'], 'x': centre(n)[0], 'y': centre(n)[1], 'size': n['size'], 'names': []} for n in numbers]
    for nm in names:
        cx, cy = centre(nm)
        best, bd = None, 1e9
        for o in out:
            d = np.hypot(o['x'] - cx, o['y'] - cy)
            if d < bd:
                best, bd = o, d
        if best is not None and bd < 30 * sizes[1] / 5.0:
            best['names'].append((cy, cx, nm['text']))
    for o in out:
        o['name'] = ' '.join(t for _, _, t in sorted(o['names'])).replace('/ ', '/').replace(' -', '').strip()
        del o['names']
    return out


def flood(img, seed, tol=6, conn=4):
    """4-connected flood fill of the white space from seed (px). Returns mask (uint8) or None."""
    h, w = img.shape
    x, y = int(round(seed[0])), int(round(seed[1]))
    if img[y, x]:
        found = None
        for r in range(1, tol + 1):
            ys, xs = np.ogrid[max(0, y - r):y + r + 1, max(0, x - r):x + r + 1]
            win = img[max(0, y - r):y + r + 1, max(0, x - r):x + r + 1]
            if (win == 0).any():
                yy, xx = np.argwhere(win == 0)[0]
                found = (max(0, x - r) + xx, max(0, y - r) + yy)
                break
        if found is None:
            return None
        x, y = found
    mask = np.zeros((h + 2, w + 2), np.uint8)
    cv2.floodFill(img.copy(), mask, (x, y), 255, flags=conn | (255 << 8) | cv2.FLOODFILL_MASK_ONLY)
    return mask[1:-1, 1:-1]


def fit_circle(pts):
    """Algebraic least-squares circle fit: returns (cx, cy, r, rms residual)."""
    x, y = pts[:, 0], pts[:, 1]
    A = np.column_stack([x, y, np.ones_like(x)])
    b = x ** 2 + y ** 2
    sol, *_ = np.linalg.lstsq(A, b, rcond=None)
    cx, cy = sol[0] / 2, sol[1] / 2
    r = np.sqrt(max(sol[2] + cx ** 2 + cy ** 2, 1e-9))
    res = np.sqrt(np.mean((np.hypot(x - cx, y - cy) - r) ** 2))
    return cx, cy, r, res


def door_arcs(geom):
    """Door swings: (arc midpoint, outward unit vector away from the hinge) for each polyline
    that lies on a circle of door-leaf radius and sweeps roughly a quarter turn."""
    arcs = []
    for pl in geom.get('polylines', []):
        p = np.array(pl, float)
        if len(p) < 4 or np.hypot(*(p[-1] - p[0])) < MIN_CURVE:
            continue
        cx, cy, r, res = fit_circle(p)
        if res > 0.25 or not (8 <= r <= 45):
            continue
        ang = np.unwrap(np.arctan2(p[:, 1] - cy, p[:, 0] - cx))
        sweep = abs(ang[-1] - ang[0])
        if not (np.radians(45) <= sweep <= np.radians(200)):
            continue
        mid = p[len(p) // 2]
        out = mid - np.array([cx, cy])
        arcs.append((mid, out / np.hypot(*out), p))
    return arcs


def columns(geom, walls=None, r_range=(3.0, 7.0)):
    """Structural columns: closed circles of column size, drawn as many strokes shorter than
    MIN_LINE (so they never reach the raster) or as four bezier arcs. The walls stop at the
    column's face, so without the disc every wall junction at a column is a gap the fill
    leaks through. With `walls` given (a raster of long strokes only), just the circles whose
    rim meets a wall are kept: round chairs and tables are circles too, but larger, and only
    their own short leg strokes come near them."""
    found = []
    for pl in geom.get('polylines', []):
        p = np.array(pl, float)
        if len(p) < 12 or np.hypot(*(p[-1] - p[0])) > 1.0:
            continue
        cx, cy, r, res = fit_circle(p)
        if res <= 0.3 and r_range[0] <= r <= r_range[1]:
            found.append((cx, cy, r))
    curves = [c for c in geom.get('curves', []) if c[5]]
    i = 0
    while i + 3 < len(curves):
        q = curves[i:i + 4]
        if all(np.allclose(q[k][3], q[k + 1][0], atol=0.05) for k in range(3)) and np.allclose(q[3][3], q[0][0], atol=0.05):
            pts = np.array([pt for c in q for pt in c[:4]], float)
            cx, cy, r, res = fit_circle(pts)
            if res <= 0.5 and r_range[0] <= r <= r_range[1]:
                found.append((cx, cy, r))
            i += 4
        else:
            i += 1
    if walls is None:
        return found
    h, w = walls.shape
    out = []
    for cx, cy, r in found:
        # a wall line must meet the circle's face (round chairs sit clear of the walls)
        x, y, rr = int(round(cx * SCALE)), int(round(cy * SCALE)), int(r * SCALE) + 2
        win = walls[max(0, y - rr):y + rr + 1, max(0, x - rr):x + rr + 1]
        yy, xx = np.mgrid[max(0, y - rr):y + rr + 1, max(0, x - rr):x + rr + 1]
        if (win[(xx - x) ** 2 + (yy - y) ** 2 <= (r * SCALE + 1.5) ** 2] > 0).any():
            out.append((cx, cy, r))
    return out


def door_seeds(lab, arcs, radius=45.0):
    """Candidate seeds just beyond the door arcs near a label, nearest first."""
    c = np.array([lab['x'], lab['y']])
    near = sorted(((np.hypot(*(mid - c)), mid, out) for mid, out, _ in arcs), key=lambda t: t[0])
    return [mid + out * 4 for d, mid, out in near if d <= radius][:3]


DESK_SHORT = (9.0, 20.0)   # pt; worksurface depth (30" at this scale is ~11 pt)
DESK_LONG = (18.0, 45.0)   # pt; worksurface width (60"-72" is 22-27 pt)
DESK_WIDTH = 0.9           # pt; desks are the bold (1 pt) quads, casework is drawn at 0.5 pt
MAX_ROOM = 150000  # px; anything bigger is the corridor network, not a room
MIN_ROOM = 600     # px; smaller pockets are wall cavities or furniture (a phone booth is ~650)
SMALL_ROOM = 6000  # px; a room this small may have its doorway sealed if it is drawn open
POD_ROOM = 250     # px; the inside of a phone booth pod, ring around its seat
DOOR_DIST = 20.0   # pt; a label this close to a door arc belongs to that door
DOOR_R = 10.0      # pt; typical door-leaf length used to step behind the hinge
VERBOSE = False
TINY = 1200        # px; unlabelled regions below this are hatch cells, treads, X marks
CLOSE = 3          # px; morphological closing kernel for the wall raster


def hatch_clusters(img):
    """Mask of hatched areas: unions of adjacent tiny free-space cells (tiles, treads)."""
    n, cc, stats, _ = cv2.connectedComponentsWithStats((img == 0).astype(np.uint8), connectivity=4)
    tiny = np.zeros_like(img)
    for k in range(1, n):
        area = stats[k, cv2.CC_STAT_AREA]
        if 4 <= area < TINY and min(stats[k, cv2.CC_STAT_WIDTH], stats[k, cv2.CC_STAT_HEIGHT]) >= 4:
            tiny[cc == k] = 255
    return tiny


def split_region(mask, seed_a, seed_b):
    """Split a region between two seeds by geodesic distance (watershed on a flat image)."""
    markers = np.zeros(mask.shape, np.int32)
    for k, sd in ((1, seed_a), (2, seed_b)):
        cv2.circle(markers, (int(sd[0] * SCALE), int(sd[1] * SCALE)), 2, k, -1)
    markers[mask == 0] = 0
    ws = watershed(np.zeros(mask.shape, np.uint8), markers, mask=mask > 0)
    a = ((ws == 1) * 255).astype(np.uint8)
    b = ((ws == 2) * 255).astype(np.uint8)
    if np.count_nonzero(a) < MIN_ROOM or np.count_nonzero(b) < MIN_ROOM:
        return None, None
    return a, b


def with_door_swings(mask, arcs, band=7):
    """Add each door swing that opens into the room (the pie slice between hinge, leaf and
    arc) to the room mask. The arcs are rasterised as walls so rooms fill as closed regions,
    which leaves a quarter-circle notch at every door; on the map the door belongs to the room.
    An arc belongs to the room when most of it runs along the room's fill."""
    h, w = mask.shape
    near = cv2.dilate(mask, np.ones((band, band), np.uint8))
    out = mask.copy()
    for _, _, p in arcs:
        p = np.asarray(p, float)
        px = np.round(p * SCALE).astype(int)
        px[:, 0] = np.clip(px[:, 0], 0, w - 1)
        px[:, 1] = np.clip(px[:, 1], 0, h - 1)
        if (near[px[:, 1], px[:, 0]] > 0).mean() < 0.6:
            continue
        cx, cy, _, _ = fit_circle(p)
        sector = np.vstack([[cx, cy], p])
        cv2.fillPoly(out, [np.round(sector * SCALE).astype(np.int32)], 255)
    return out


def box_poly(mask):
    """Minimum-area bounding rectangle of the mask's largest component (thin slivers such as
    a wall cavity the fill crept into are opened away first)."""
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((9, 9), np.uint8))
    cs, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not cs:
        return None
    box = cv2.boxPoints(cv2.minAreaRect(max(cs, key=cv2.contourArea))) / SCALE
    return [[round(float(x), 1), round(float(y), 1)] for x, y in box]


def desks(geom, mask, tol=5):
    """Worksurface quads whose centre stands on the mask (the open areas)."""
    if not geom.get('quads'):
        return []
    zone = cv2.dilate(mask, np.ones((tol, tol), np.uint8))
    h, w = zone.shape
    out = []
    for *pts, width, black in geom['quads']:
        if not black or width is None or width < DESK_WIDTH:
            continue
        p = np.array(pts, float)
        sides = np.hypot(*(p - np.roll(p, -1, axis=0)).T)
        short, long_ = (sides[0] + sides[2]) / 2, (sides[1] + sides[3]) / 2
        if short > long_:
            short, long_ = long_, short
        if not (DESK_SHORT[0] <= short <= DESK_SHORT[1] and DESK_LONG[0] <= long_ <= DESK_LONG[1]):
            continue
        cx, cy = np.round(p.mean(0) * SCALE).astype(int)
        if 0 <= cx < w and 0 <= cy < h and zone[cy, cx]:
            out.append([[round(float(x), 1), round(float(y), 1)] for x, y in p])
    return out


SMOOTH = 7  # px; round close/open kernel that drops the jogs along traced walls
SMOOTH_NAMES = ('PIAZZA', 'PORCH')  # open areas drawn as sweeping shapes, not hugging the rooms
SMOOTH_OPEN = 25    # px; features narrower than this (door notches, office corners) vanish
SMOOTH_INSET = 4    # px; the sweeping shape stands clear of the rooms around it
EPS = 2.0    # px; polygon simplification tolerance for rooms


def _approx_n(c, n):
    """approxPolyDP of the contour with exactly n vertices, or None. For n = 4 the corners are
    taken from the minimum-area rectangle when the simplification never lands on four (a
    column disc biting a corner splits it into two vertices that vanish together)."""
    eps = 1.0
    while eps < 60:
        a = cv2.approxPolyDP(c.astype(np.float32), eps, True).reshape(-1, 2)
        if len(a) == n:
            return a.astype(float)
        if len(a) < n:
            break
        eps *= 1.15
    if n != 4:
        return None
    box = cv2.boxPoints(cv2.minAreaRect(c.astype(np.float32)))
    idx = sorted(int(np.argmin(np.linalg.norm(c - q, axis=1))) for q in box)
    if len(set(idx)) < 4:
        return None
    return c[idx].astype(float)


def _edge_dist(c, poly):
    """Distance from each contour point to every polygon edge (points x edges)."""
    a = poly
    b = np.roll(poly, -1, axis=0)
    ab = b - a
    ap = c[:, None, :] - a[None, :, :]
    t = np.clip((ap * ab[None]).sum(-1) / np.maximum((ab ** 2).sum(-1)[None], 1e-9), 0, 1)
    return np.linalg.norm(ap - t[..., None] * ab[None], axis=-1)


def _edge_of(c, poly):
    """Index of the polygon edge nearest to each contour point."""
    return _edge_dist(c, poly).argmin(1)


def _fit_lines(c, poly, edges=None, min_pts=6):
    """Least-squares line (point, unit direction) through the contour points nearest to each
    polygon edge; None for edges with too few points. `edges` limits which edges are fitted."""
    owner = _edge_of(c, poly)
    lines = []
    for i in range(len(poly)):
        pts = c[owner == i]
        if (edges is not None and i not in edges) or len(pts) < min_pts:
            lines.append(None)
            continue
        vx, vy, x0, y0 = cv2.fitLine(pts.astype(np.float32), cv2.DIST_L2, 0, 0.01, 0.01).ravel()
        lines.append((np.array([x0, y0]), np.array([vx, vy])))
    return lines


def _intersect(l1, l2, min_angle=20):
    (p1, d1), (p2, d2) = l1, l2
    cross = d1[0] * d2[1] - d1[1] * d2[0]
    if abs(cross) < np.sin(np.radians(min_angle)):
        return None
    t = ((p2 - p1)[0] * d2[1] - (p2 - p1)[1] * d2[0]) / cross
    return p1 + t * d1


def _iou(mask, poly):
    h, w = mask.shape
    m2 = np.zeros_like(mask)
    cv2.fillPoly(m2, [np.round(poly * SCALE).astype(np.int32)], 255)
    a, b = mask > 0, m2 > 0
    return np.count_nonzero(a & b) / max(np.count_nonzero(a | b), 1)


def straighten(mask, ns=(4, 5, 6, 8), min_iou=0.88, max_shift=12, max_dev=3.0, curved_edges=False):
    """The simplest polygon with straight, line-fitted walls that still covers the room: the
    contour is reduced to n corners, each edge is refitted to the wall pixels it runs along and
    the corners are the intersections of neighbouring walls. A fit is accepted when it covers
    the region (IoU) and nearly all of the traced wall lies within `max_dev` px of it (so a
    curved wall is never faceted). Returns None if no n fits."""
    cs, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    if not cs:
        return None
    c = max(cs, key=cv2.contourArea).reshape(-1, 2).astype(float)
    for n in ns:
        poly = _approx_n(c, n)
        if poly is None:
            continue
        lines = _fit_lines(c, poly)
        if any(l is None for l in lines):
            continue
        # a wall that bows systematically to one side of its fitted line is curved: no corner
        # fit then, the run tracer draws it as an arc
        owner = _edge_of(c, poly)
        curved = [_is_curved(c[owner == i], poly[i], poly[(i + 1) % n]) for i in range(n)]
        if curved_edges:
            # a box with a curved wall (the social kitchens): the curved edges become arcs
            # through the corners, which are where the straight walls meet those arcs
            circles = [fit_circle(c[owner == i]) if curved[i] else None for i in range(n)]
            corners = []
            for i in range(n):
                q = None
                if not curved[i - 1] and not curved[i]:
                    q = _intersect(lines[i - 1], lines[i])
                elif curved[i - 1] != curved[i]:
                    line = lines[i] if curved[i - 1] else lines[i - 1]
                    cx, cy, r, _ = circles[i - 1] if curved[i - 1] else circles[i]
                    p0, d = line
                    t0 = np.dot(np.array([cx, cy]) - p0, d)
                    h = r * r - np.sum((p0 + d * t0 - [cx, cy]) ** 2)
                    if h >= 0:
                        cands = [p0 + d * (t0 + np.sqrt(h)), p0 + d * (t0 - np.sqrt(h))]
                        q = min(cands, key=lambda v: np.linalg.norm(v - poly[i]))
                if q is None or np.linalg.norm(q - poly[i]) > max_shift:
                    q = poly[i]
                corners.append(q)
            corners = np.array(corners) / SCALE
            out = []
            for i in range(n):
                a, b = corners[i], corners[(i + 1) % n]
                if curved[i] and circles[i] is not None:
                    cx, cy, r, _ = circles[i]
                    chord = np.linalg.norm(b - a)
                    theta = 2 * np.arcsin(min(chord / (2 * r), 1.0))
                    d = b - a
                    n_right = np.array([-d[1], d[0]]) / max(chord, 1e-9)
                    side = np.sign(np.dot(c[owner == i].mean(0) - a, n_right)) or 1.0
                    out.append([round(float(a[0]), 1), round(float(a[1]), 1), round(float(side * np.tan(theta / 4)), 4)])
                else:
                    out.append([round(float(a[0]), 1), round(float(a[1]), 1)])
            return out
        if any(np.linalg.norm(poly[(i + 1) % n] - poly[i]) >= LONG_WALL and curved[i] for i in range(n)):
            return None
        corners = []
        for i in range(n):
            q = _intersect(lines[i - 1], lines[i])
            if q is None or np.linalg.norm(q - poly[i]) > max_shift:
                break
            corners.append(q)
        if len(corners) < n:
            continue
        corners = np.array(corners)
        # four fifths of the traced wall must lie on the fit: a column disc bites a corner,
        # a curved wall misses everywhere
        if max_dev is not None and np.percentile(_edge_dist(c, corners).min(1), 80) > max_dev:
            continue
        corners = corners / SCALE
        if _iou(mask, corners) >= min_iou:
            return [[round(float(x), 1), round(float(y), 1)] for x, y in corners]
    return None


def _smooth_curve(seg, eps, sigma=6.0):
    """A curved run traced finely: the pixel staircase is low-pass filtered along the run
    (ends pinned) before it is simplified, so the curve comes out smooth."""
    if len(seg) > 8:
        sm = gaussian_filter1d(seg, sigma, axis=0, mode='nearest')
        sm[0], sm[-1] = seg[0], seg[-1]
        seg = sm
    return cv2.approxPolyDP(seg.astype(np.float32), eps, False).reshape(-1, 2).astype(float)


def _is_curved(pts, a, b, res_tol=None):
    """Do the points bow as a curved wall between a and b: consistently to one side of the
    chord, spread along it (a door swing or a column bite bows only locally)?"""
    chord = b - a
    c = np.linalg.norm(chord)
    if c < 1 or len(pts) < 6:
        return False
    off = (pts - a) @ np.array([-chord[1], chord[0]]) / c
    mag = np.abs(off)
    if not (mag.mean() > CURVE_SAG and np.median(mag) > 0.5 * CURVE_SAG and abs(off.mean()) > 0.8 * mag.mean()):
        return False
    # and it must actually lie on a circle: a stepped or zigzag partition bows too but is no curve
    cx, cy, r, res = fit_circle(pts)
    return res <= (CURVE_RES if res_tol is None else res_tol) and r >= MIN_ARC_R


def _fit(pts):
    vx, vy, x0, y0 = cv2.fitLine(pts.astype(np.float32), cv2.DIST_L2, 0, 0.01, 0.01).ravel()
    return np.array([x0, y0]), np.array([vx, vy])


def _project(q, line):
    p0, d = line
    return p0 + d * np.dot(q - p0, d)


def straight_runs(mask, eps, eps_coarse=8.0, min_len=60, close=0, smooth=0, curve_res=None):
    """Polygon whose straight runs are single line-fitted edges while the curved runs keep
    their traced vertices. A coarse simplification finds the runs: a coarse edge at least
    `min_len` long is a straight wall and is refitted to the pixels along it; shorter coarse
    edges are curves and are traced finely (`eps`). Used for the outline and irregular rooms."""
    m = _prep(mask, close, smooth)
    cs, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    if not cs:
        return None
    c = max(cs, key=cv2.contourArea).reshape(-1, 2).astype(float)
    coarse = cv2.approxPolyDP(c.astype(np.float32), eps_coarse, True).reshape(-1, 2)
    where = {tuple(p): i for i, p in enumerate(c.astype(np.int64).tolist())}
    idx = [where.get(tuple(p)) for p in coarse.astype(np.int64).tolist()]
    idx = [i for i in idx if i is not None]
    # a gentle curve is split by the coarse simplification at its apex into pieces that each
    # bow only a little: merge neighbouring pieces meeting at a shallow angle when together
    # they bow as a curve
    changed = True
    while changed and len(idx) > 3:
        changed = False
        for k in range(len(idx)):
            i0, i1, i2 = idx[k - 1], idx[k], idx[(k + 1) % len(idx)]
            d1, d2 = c[i1] - c[i0], c[i2] - c[i1]
            turn = np.degrees(np.arccos(np.clip(np.dot(d1, d2) / max(np.linalg.norm(d1) * np.linalg.norm(d2), 1e-9), -1, 1)))
            if turn > 25:
                continue
            seg = c[i0:i2 + 1] if i2 > i0 else np.vstack([c[i0:], c[:i2 + 1]])
            if _is_curved(seg, c[i0], c[i2], curve_res):
                del idx[k]
                changed = True
                break
    n = len(idx)
    if n < 3:
        return contour_poly(mask, eps, close, smooth)
    runs = []  # ('line', (p0, d), start, end) or ('curve', vertices)
    for k in range(n):
        i0, i1 = idx[k], idx[(k + 1) % n]
        seg = c[i0:i1 + 1] if i1 > i0 else np.vstack([c[i0:], c[:i1 + 1]])
        if np.linalg.norm(c[i1] - c[i0]) >= min_len and len(seg) >= 6:
            if _is_curved(seg, c[i0], c[i1], curve_res):
                runs.append(('curve', _smooth_curve(seg, CURVE_EPS)))
            else:
                runs.append(('line', _fit(seg), c[i0], c[i1]))
        else:
            runs.append(('curve', _smooth_curve(seg, CURVE_EPS)))
    out = []
    for k in range(n):
        prev, cur = runs[k - 1], runs[k]
        # the joint vertex between run k-1 and run k
        if prev[0] == 'line' and cur[0] == 'line':
            q = _intersect(prev[1], cur[1])
            if q is None or np.linalg.norm(q - cur[2]) > 20:
                q = (_project(prev[3], prev[1]) + _project(cur[2], cur[1])) / 2
            out.append(q)
        elif cur[0] == 'line':
            out.append(_project(cur[2], cur[1]))
        elif prev[0] == 'line':
            out.append(_project(cur[1][0], prev[1]))
        else:
            out.append(cur[1][0])
        if cur[0] == 'curve':
            out.extend(cur[1][1:-1])
    out = np.array(out) / SCALE
    return [[round(float(x), 1), round(float(y), 1)] for x, y in out]


def _prep(mask, close, smooth):
    m = mask.copy()
    if close:
        m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((close, close), np.uint8))
    if smooth:
        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (smooth, smooth))
        m = cv2.morphologyEx(cv2.morphologyEx(m, cv2.MORPH_CLOSE, k), cv2.MORPH_OPEN, k)
    return m


def _xy(poly):
    return [[float(p[0]), float(p[1])] for p in poly]


MIN_ARC_R = 40.0   # px; tighter circles are jagged corners, not curved walls
CURVE_SAG = 1.5    # px; a "straight" run bowing more than this is a curved wall
LOOSE_ARC = 2.5    # px; a whole curved run may be one arc within this rather than kinked pieces
LONG_WALL = 120.0  # px; only a wall this long can refuse a corner fit for being curved
CURVE_EPS = 0.6    # px; curves are traced this finely so the arc fitter sees a run of edges
CURVE_RES = 2.5    # px; a curved wall fits a circle this well (mullion ticks add ~2 px of noise; a folding partition zigzags more)
MAX_ARC_DEG = 100  # an arc sweeps at most this much; a longer curve is split


def _arc_piece(pts, tol):
    """One circular arc through the run, as (bulge) if every point lies within tol of it."""
    a, b = pts[0], pts[-1]
    d = b - a
    chord = np.linalg.norm(d)
    if chord < 8 or len(pts) < 3:
        return None
    cx, cy, r, res = fit_circle(pts)
    if res > tol or r < max(chord / 2, MIN_ARC_R):
        return None
    dev = np.abs(np.hypot(pts[:, 0] - cx, pts[:, 1] - cy) - r)
    if dev.max() > tol:
        return None
    theta = 2 * np.arcsin(min(chord / (2 * r), 1.0))
    if theta > np.radians(MAX_ARC_DEG):
        return None
    n_right = np.array([-d[1], d[0]]) / chord  # right of travel on a y-down screen
    side = np.sign(np.dot(pts[len(pts) // 2] - a, n_right)) or 1.0
    return float(side * np.tan(theta / 4))


def _fit_arcs(pts, tol, loose=True):
    """Points (with bulges) replacing a run of contour points, excluding the run's last point.
    A run that is nearly one circle becomes one arc (`loose`) rather than kinked pieces."""
    b = _arc_piece(pts, tol)
    if b is None and loose:
        b = _arc_piece(pts, LOOSE_ARC)
    if b is not None:
        return [[round(float(pts[0][0]), 1), round(float(pts[0][1]), 1), round(b, 4)]]
    if len(pts) <= 3:
        return [[round(float(x), 1), round(float(y), 1)] for x, y in pts[:-1]]
    k = len(pts) // 2
    return _fit_arcs(pts[:k + 1], tol, loose=False) + _fit_arcs(pts[k:], tol, loose=False)


def arcify(poly, tol=1.0, short=90.0, max_turn=40.0, min_run=3, fixed=None):
    """Replace each run of gently turning edges (a curve traced as a polyline) by circular
    arcs. Points on the result may carry a third value, the DXF-style bulge of the edge that
    starts there (tan of a quarter of the included angle, positive when the arc bows to the
    right of the direction of travel), which the map draws as a true arc."""
    P = np.array(_xy(poly), float)
    n = len(P)
    if n < 4:
        return poly
    D = np.roll(P, -1, axis=0) - P
    L = np.linalg.norm(D, axis=1)
    ang = np.degrees(np.arctan2(D[:, 1], D[:, 0]))
    turn_before = np.abs((ang - np.roll(ang, 1) + 180) % 360 - 180)  # turn at the edge's start vertex
    turn_after = np.roll(turn_before, -1)                              # turn at the edge's end vertex
    # an edge belongs to a curve when it is short and bends gently into a neighbour; a run
    # never continues through a vertex that turns sharply (a corner)
    is_short = (L <= short) & ((turn_before <= max_turn) | (turn_after <= max_turn)) & (turn_before + turn_after <= 2 * max_turn + 90)
    if fixed is not None:
        is_short &= ~np.asarray(fixed, bool)
    if is_short.all() and (turn_before <= max_turn).all():  # a closed curve: two runs from an arbitrary start
        h = n // 2
        return _fit_arcs(P[:h + 1], tol) + _fit_arcs(np.vstack([P[h:], P[:1]]), tol)
    if is_short.all():
        start = int(np.argmax(turn_before > max_turn))
    else:
        start = int(np.argmin(is_short))  # rotate so index 0 begins a long edge
    P = np.roll(P, -start, axis=0)
    is_short = np.roll(is_short, -start)
    turn_before = np.roll(turn_before, -start)
    out = []
    i = 0
    while i < n:
        if not is_short[i]:
            out.append([round(float(P[i][0]), 1), round(float(P[i][1]), 1)])
            i += 1
            continue
        j = i
        while j < n and is_short[j] and (j == i or turn_before[j] <= max_turn):
            j += 1
        if j - i >= min_run:
            run = np.vstack([P[i:j], P[j % n:j % n + 1]])
            out.extend(_fit_arcs(run, tol))
        else:
            out.extend([[round(float(x), 1), round(float(y), 1)] for x, y in P[i:j]])
        i = j
    return out


def _arc_circle(p, q, b):
    """Centre and radius of the arc from p to q with bulge b."""
    d = q - p
    c = np.linalg.norm(d)
    sag = abs(b) * c / 2
    R = (c * c / 4 + sag * sag) / (2 * sag)
    n = np.array([-d[1], d[0]]) / c
    centre = (p + q) / 2 - n * np.sign(b) * (R - sag)
    return centre, R


def arcify_all(polys, n_straight=0, near=8.0, refit_small=0.0, **kw):
    """arcify every polygon of the list (in place). Where a polygon runs along a curve an
    earlier polygon already holds as an arc, it adopts that arc (the same circle, traversed
    the other way), so the two sides coincide; edges lying on an earlier polygon's boundary
    stay straight, and so does anything within a few px of the first `n_straight` polygons
    (the enclosed rooms, whose walls are straight)."""
    shapes = [Polygon(_xy(p)).buffer(0) for p in polys]
    bounds = [s.bounds for s in shapes]
    arcs_done = []  # (p, q, bulge) of the arcs fitted so far
    for i, poly in enumerate(polys):
        P = np.array(_xy(poly), float)
        n = len(P)
        if n < 4:
            continue
        x0, y0, x1, y1 = bounds[i]
        existing = {(round(float(p[0]), 1), round(float(p[1]), 1)): p[2] for p in poly if len(p) == 3 and p[2] and abs(p[2]) >= refit_small}
        # adopt the arcs of earlier polygons along this one: every chain of vertices lying on
        # such a circle, within its sweep, collapses to one edge on the same circle
        adopted = {}
        for p, q, b in arcs_done:
            centre, R = _arc_circle(p, q, b)
            if not (x0 - R <= centre[0] <= x1 + R and y0 - R <= centre[1] <= y1 + R):
                continue
            rel = P - centre
            on = np.abs(np.hypot(rel[:, 0], rel[:, 1]) - R) <= near
            if on.sum() < 2:
                continue
            # inside the sweep: the angle from p to the vertex (in the arc's direction) is
            # below the angle from p to q
            sweep_sign = -np.sign(b)  # y down: a right-bowing arc runs clockwise on screen (negative angle)
            a0 = np.arctan2(*(p - centre)[::-1])
            a1 = (np.arctan2(*(q - centre)[::-1]) - a0) * sweep_sign % (2 * np.pi)
            av = (np.arctan2(rel[:, 1], rel[:, 0]) - a0) * sweep_sign % (2 * np.pi)
            on &= (av <= a1 + 1e-3) | (av >= 2 * np.pi - 1e-3)
            if on.sum() < 2:
                continue
            # maximal cyclic chains of consecutive vertices on the arc
            idx = np.nonzero(on)[0]
            chains = []
            k0 = idx[0]
            if on.all():
                continue
            # rotate so the scan starts at a vertex that is not on the arc
            first_off = int(np.argmin(on))
            order = [(first_off + k) % n for k in range(n)]
            chain = []
            for k in order:
                if on[k]:
                    chain.append(k)
                else:
                    if len(chain) >= 2:
                        chains.append(chain)
                    chain = []
            if len(chain) >= 2:
                chains.append(chain)
            for chain in chains:
                a, z = chain[0], chain[-1]
                if any(k in adopted for k in chain[:-1]):
                    continue
                d = P[z] - P[a]
                c = np.linalg.norm(d)
                if c < 8 or c > 2 * R:
                    continue
                theta = 2 * np.arcsin(min(c / (2 * R), 1.0))
                n_right = np.array([-d[1], d[0]]) / c
                side = -np.sign(np.dot(centre - (P[a] + P[z]) / 2, n_right)) or 1.0
                adopted[a] = ((z - a) % n, float(side * np.tan(theta / 4)))
        # rebuild the vertex list with the adopted arcs collapsed to single edges
        keep = []
        j = 0
        while j < n:
            if j in adopted:
                steps, bulge = adopted[j]
                keep.append((P[j], bulge, True))
                j += steps
                if j >= n:
                    break
            else:
                keep.append((P[j], None, False))
                j += 1
        if keep and np.allclose(keep[0][0], keep[-1][0]) and len(keep) > 1:
            keep.pop()
        P2 = np.array([k[0] for k in keep])
        fixed = np.array([k[2] for k in keep], bool)
        for k_, kp in enumerate(keep):  # arcs the polygon already carries stay as they are
            if (round(float(kp[0][0]), 1), round(float(kp[0][1]), 1)) in existing:
                fixed[k_] = True
        # edges lying on an earlier polygon's boundary stay straight
        others = [(shapes[j].boundary, 6.0 if j < n_straight else 0.3) for j in range(i) if not (bounds[j][2] < x0 - 6 or bounds[j][0] > x1 + 6 or bounds[j][3] < y0 - 6 or bounds[j][1] > y1 + 6)]
        Q = np.roll(P2, -1, axis=0)
        M = (P2 + Q) / 2
        for b, tol_b in others:
            d = np.max([shapely.distance(shapely.points(P2), b), shapely.distance(shapely.points(Q), b), shapely.distance(shapely.points(M), b)], axis=0)
            fixed |= d < tol_b
        out = arcify([[float(x), float(y)] for x, y in P2], fixed=fixed, **kw)
        # put the adopted bulges back (arcify keeps fixed edges as plain points)
        want = {(round(float(k[0][0]), 1), round(float(k[0][1]), 1)): k[1] for k in keep if k[2] and k[1] is not None}
        want.update(existing)
        for pt in out:
            key = (round(pt[0], 1), round(pt[1], 1))
            if key in want and len(pt) == 2:
                pt.append(round(want[key], 4))
        polys[i][:] = out
        for k, pt in enumerate(out):
            if len(pt) == 3 and pt[2]:
                nxt = out[(k + 1) % len(out)]
                arcs_done.append((np.array(pt[:2], float), np.array(nxt[:2], float), pt[2]))


def merge_collinear(poly, max_turn=15.0, max_dev=5.0, flat=0.06):
    """Collapse chains of nearly collinear edges into one straight edge: a vertex between two
    (nearly) straight edges that turns little and lies close to the chord of its neighbours
    is dropped, repeatedly. A curtain wall traced as a zigzag of mullion ticks becomes one
    line, while a real curve (an arc with a bulge above `flat`) is left alone."""
    pts = [list(p) for p in poly]
    changed = True
    while changed and len(pts) > 3:
        changed = False
        n = len(pts)
        for i in range(n):
            a, b, c = pts[i - 1], pts[i], pts[(i + 1) % n]
            if (len(a) == 3 and abs(a[2]) > flat) or (len(b) == 3 and abs(b[2]) > flat):
                continue
            d1 = np.array(b[:2]) - np.array(a[:2])
            d2 = np.array(c[:2]) - np.array(b[:2])
            l1, l2 = np.linalg.norm(d1), np.linalg.norm(d2)
            if l1 < 1e-6 or l2 < 1e-6:
                continue
            turn = np.degrees(np.arccos(np.clip(np.dot(d1, d2) / (l1 * l2), -1, 1)))
            chord = np.array(c[:2]) - np.array(a[:2])
            v = np.array(b[:2]) - np.array(a[:2])
            dev = abs(chord[0] * v[1] - chord[1] * v[0]) / max(np.linalg.norm(chord), 1e-9)
            if turn <= max_turn and dev <= max_dev:
                del pts[i]
                if len(a) == 3:
                    del a[2]
                changed = True
                break
    return pts


def reconcile(items, min_overlap=2.0):
    """Rooms may touch but not overlap. Items are (priority, polygon-holder dict) with the
    polygon under 'polygon'; lower priority numbers keep their shape, later ones give up any
    part already claimed (the overlap is a sliver along a shared wall from the independent
    line fits, so the loser keeps its fitted shape minus that sliver). A room lying wholly
    inside an open area becomes a hole in it ('holes')."""
    kept = []
    changed = 0
    owners = []  # the item each kept polygon belongs to
    for prio, it in sorted(items, key=lambda t: (t[0], len(t[1]['polygon']), -abs(cv2.contourArea(np.array(_xy(t[1]['polygon']), np.float32))))):
        arcs_in = {(round(p[0], 1), round(p[1], 1)): p[2] for p in it['polygon'] if len(p) == 3 and p[2]}
        poly = Polygon(_xy(it['polygon'])).buffer(0)
        if poly.is_empty:
            continue
        original = poly.area
        poly = poly.simplify(0.3)
        whole = poly
        if prio >= 2:  # open areas: close hairline gaps to every neighbour first
            for other in kept:
                if poly.distance(other) < 4:
                    poly = snap(poly, other, 4).buffer(0)
                    if isinstance(poly, MultiPolygon):
                        poly = max(poly.geoms, key=lambda g: g.area)
        for other in kept:
            if not poly.intersects(other):
                continue
            if poly.intersection(other).area < min_overlap:
                continue
            poly = poly.difference(other)
            if isinstance(poly, MultiPolygon):
                poly = max(poly.geoms, key=lambda g: g.area)
        if poly.is_empty or poly.area < 0.5 * original:
            # it lies inside an earlier shape (an office in a boxed lab): keep it, and punch
            # it out of the shape that contains it
            poly = whole
            for j, other in enumerate(kept):
                # only a labelled room is cut out of its container; an unlabelled pocket
                # inside a boxed lab is its bench block, not a room
                if it.get('id') and other.intersection(poly).area > 0.5 * original and owners[j] is not None:
                    cut = other.difference(poly)
                    if isinstance(cut, MultiPolygon):
                        cut = max(cut.geoms, key=lambda g: g.area)
                    kept[j] = cut
                    owners[j]['polygon'] = [[round(float(x), 1), round(float(y), 1)] for x, y in cut.exterior.coords[:-1]]
                    holes = [[[round(float(x), 1), round(float(y), 1)] for x, y in ring.coords[:-1]] for ring in cut.interiors if Polygon(ring).area >= 20]
                    if holes:
                        owners[j]['holes'] = holes
                    print(f"  overlap: {it.get('id', '?')} lies inside {owners[j].get('id', '?')}, cut out of it")
                    break
            else:
                print(f"  overlap: {it.get('id', 'u%s' % it.get('idx', '?'))} would lose more than half its area, kept as is")
        else:
            pts = [[round(float(x), 1), round(float(y), 1)] for x, y in poly.exterior.coords[:-1]]
            for pt in pts:  # an arc edge whose start survived keeps its bulge
                if (pt[0], pt[1]) in arcs_in:
                    pt.append(arcs_in[(pt[0], pt[1])])
            if pts != it['polygon']:
                changed += 1
            it['polygon'] = pts
            holes = [[[round(float(x), 1), round(float(y), 1)] for x, y in ring.coords[:-1]] for ring in poly.interiors if Polygon(ring).area >= 20]
            if holes:
                it['holes'] = holes
        kept.append(poly)
        owners.append(it)
    return changed


def contour_poly(mask, eps, close=0, smooth=0):
    """Outer polygon of the mask's largest component. `close` seals thin gaps (mullion ticks,
    hatching); `smooth` runs a round close then open, which drops the small jogs where the fill
    crept between the two lines of a wall or a short wall piece pokes into the room."""
    m = mask.copy()
    if close:
        m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((close, close), np.uint8))
    if smooth:
        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (smooth, smooth))
        m = cv2.morphologyEx(cv2.morphologyEx(m, cv2.MORPH_CLOSE, k), cv2.MORPH_OPEN, k)
    cs, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not cs:
        return None
    c = max(cs, key=cv2.contourArea)
    poly = cv2.approxPolyDP(c, eps, True).reshape(-1, 2) / SCALE
    return [[round(float(x), 1), round(float(y), 1)] for x, y in poly]


def run(floor, geom_path, out_prefix, cfg=None, exterior_seed=(30, 30)):
    cfg = cfg or {}
    geom = json.load(open(geom_path))
    arcs = door_arcs(geom)
    cols = columns(geom, raster(geom, min_line=8.0, furniture=False))
    print(f'  {len(cols)} columns at walls')
    img = raster(geom, extra=cfg.get('extra', ()), arcs=arcs, columns=cols)
    walls = raster(geom, extra=cfg.get('extra', ()), furniture=False, arcs=arcs, columns=cols)
    labs = labels(geom, cfg.get('label_sizes', LABEL_SIZES), cfg.get('number_re', NUMBER_RE), cfg.get('skip', ()))
    seeds_cfg = cfg.get('seeds', {})
    # Sheets with bigger label text (the Lower Level) place labels further from their door.
    label_scale = cfg.get('label_sizes', LABEL_SIZES)[1] / LABEL_SIZES[1]
    door_dist = DOOR_DIST * label_scale
    min_room = cfg.get('min_room', MIN_ROOM)
    boxes = cfg.get('box', set())
    quads = cfg.get('quad', set())
    exterior = flood(img, exterior_seed)
    cluster_mask = None
    for sx, sy in cfg.get('exterior', ()):  # e.g. a covered plaza or a paved roof terrace
        m = flood(img, (sx * SCALE, sy * SCALE), tol=3)
        if m is not None and np.count_nonzero(m) < TINY:
            # the seed sits in one cell of a hatch (pavers): take the whole hatched area
            if cluster_mask is None:
                cluster_mask = hatch_clusters(img)
            # tiles touch only at the corners of the grid lines: an 8-connected fill joins them
            m = flood(255 - cluster_mask, (sx * SCALE, sy * SCALE), tol=3, conn=8)
        if m is not None:
            exterior |= m
    h, w = img.shape
    rooms, open_labels = [], []
    enclosed = np.zeros_like(img)
    taken = np.zeros_like(img)  # pixels already owned by an accepted room

    sealed = {}  # label id -> (window, kernel) for rooms whose doorway had to be closed

    def refine(m, seed, lab_id=None):
        """Re-fill the room on the furniture-free raster, confined to a band around the
        furnished fill so a wall gap cannot leak it far, and kept off every pixel that lies
        nearer to another room's fill than to this one (two offices split across a leaky
        partition would otherwise overlap on the furniture between them)."""
        band = cv2.dilate(m, np.ones((41, 41), np.uint8))
        if lab_id in sealed:  # close the same doorway on the wall raster
            win, k = sealed[lab_id]
            walls_here = walls.copy()
            walls_here[win] = cv2.morphologyEx(walls[win], cv2.MORPH_CLOSE, np.ones((k, k), np.uint8))
        else:
            walls_here = walls
        ys, xs = np.nonzero(band)
        y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
        block = np.zeros_like(m)
        others = (taken & ~m)[y0:y1, x0:x1]
        if others.any():
            d_self = cv2.distanceTransform((m[y0:y1, x0:x1] == 0).astype(np.uint8), cv2.DIST_L2, 3)
            d_other = cv2.distanceTransform((others == 0).astype(np.uint8), cv2.DIST_L2, 3)
            block[y0:y1, x0:x1] = (d_other < d_self).astype(np.uint8) * 255
        barrier = walls_here | (band == 0).astype(np.uint8) * 255 | block | claimed
        if seed is None:
            ys, xs = np.nonzero(m)
            seed = (xs[len(xs) // 2] / SCALE, ys[len(ys) // 2] / SCALE)
        r = flood(barrier, (seed[0] * SCALE, seed[1] * SCALE), tol=4)
        if r is None or np.count_nonzero(r) < 0.8 * np.count_nonzero(m):
            return m
        return r
    pts = np.array([[l['x'] * SCALE, l['y'] * SCALE] for l in labs])

    def why(m, lab):
        if m is None:
            return 'no free pixel'
        area = int(np.count_nonzero(m))
        if not (min_room <= area <= MAX_ROOM):
            return f'area {area}'
        if (m & exterior).any():
            return 'touches exterior'
        if (m & taken).any():
            owner = [r['id'] for r in rooms if (m & room_masks[r['id']]).any()]
            return f'taken by {owner}'
        inside = [o['id'] for o, (x, y) in zip(labs, pts) if o is not lab and m[int(y), int(x)]]
        return f'contains {inside[:4]}' if inside else None

    room_masks = {}

    def valid(m, lab):
        reason = why(m, lab)
        if reason and VERBOSE:
            print(f"    {lab['id']}: rejected seed: {reason}")
        return reason is None

    seeds_used = {}

    clean_masks = {}
    claimed = np.zeros_like(img)  # pixels of the cleaned rooms fitted so far

    def room_poly(lab_id, m, seed):
        """Polygon of a room: the fill re-traced without furniture, plus its door swings."""
        if lab_id in sealed:  # a pod or a room with a sealed doorway: its fill is the room
            if VERBOSE:
                ys, xs = np.nonzero(m)
                clean_masks[lab_id] = (int(ys.min()), int(xs.min()), m[ys.min():ys.max() + 1, xs.min():xs.max() + 1].copy())
            claimed[m > 0] = 255
            enclosed[m > 0] = 255
            return box_poly(m)
        clean = with_door_swings(refine(m, seed, lab_id), arcs)
        claimed[clean > 0] = 255
        if VERBOSE:  # keep a crop of the cleaned mask for debugging the fits offline
            ys, xs = np.nonzero(clean)
            clean_masks[lab_id] = (int(ys.min()), int(xs.min()), clean[ys.min():ys.max() + 1, xs.min():xs.max() + 1].copy())
        enclosed[clean > 0] = 255  # the open areas must not spill into the door swings
        if lab_id in boxes:
            return box_poly(clean)
        tidy = _prep(clean, 0, SMOOTH + 2)
        if lab_id in quads:
            return straighten(tidy, ns=(4,), min_iou=0, max_shift=40, max_dev=None, curved_edges=True) or box_poly(clean)
        return straighten(tidy) or straight_runs(tidy, EPS, eps_coarse=6, min_len=20)

    def accept(lab, m, seed=None):
        room_masks[lab['id']] = m
        seeds_used[lab['id']] = seed
        enclosed[m > 0] = 255
        taken[m > 0] = 255
        rooms.append({**lab, 'kind': 'room', 'area': int(np.count_nonzero(m))})

    # Pass 0: hand-placed seeds from the floor config.
    for lab in list(labs):
        if lab['id'] in seeds_cfg:
            sx, sy = seeds_cfg[lab['id']]
            m = flood(img, (sx * SCALE, sy * SCALE), tol=3)
            if valid(m, lab):
                accept(lab, m, (sx, sy))
            else:
                print(f"  manual seed for {lab['id']} rejected")
    # Pass A: labels at a door. Match arcs to labels one-to-one, nearest pairs first, and
    # seed just beyond the arc (door swinging in) or just behind the hinge (swinging out).
    pairs = sorted((float(np.hypot(*(mid - [lab['x'], lab['y']]))), i, j) for i, lab in enumerate(labs) for j, (mid, out, _) in enumerate(arcs))
    label_arc, used_arc = {}, set()
    for d, i, j in pairs:
        if d > door_dist:
            break
        if i in label_arc or j in used_arc:
            continue
        label_arc[i] = j
        used_arc.add(j)
    pending = []
    for i, lab in enumerate(labs):
        if lab['id'] in room_masks:
            continue
        if i not in label_arc:
            pending.append(lab)
            continue
        mid, out, _ = arcs[label_arc[i]]
        found = None
        for sd in (mid + out * 4, mid - out * (DOOR_R + 6)):
            m = flood(img, (sd[0] * SCALE, sd[1] * SCALE), tol=3)
            if valid(m, lab):
                found = (m, sd)
                break
            # Two offices whose shared partition has a gap fill as one region: if the region
            # is exactly the one an earlier door-seeded label owns, split it between the seeds.
            if m is not None and (m & taken).any():
                owners = [r for r in rooms if room_masks[r['id']] is not None and (m & room_masks[r['id']]).any()]
                if len(owners) == 1 and seeds_used.get(owners[0]['id']) is not None and np.array_equal(room_masks[owners[0]['id']] > 0, m > 0):
                    other = owners[0]
                    a, b = split_region(m, seeds_used[other['id']], sd)
                    if a is not None:
                        room_masks[other['id']] = a
                        other['area'] = int(np.count_nonzero(a))
                        found = (b, sd)
                        print(f"  split {other['id']} / {lab['id']}")
                        break
        if found is not None:
            accept(lab, found[0], found[1])
        else:
            pending.append(lab)
    # Pass B: labels inside their room.
    still = []
    for lab in pending:
        m = flood(img, (lab['x'] * SCALE, lab['y'] * SCALE), tol=3)
        if valid(m, lab):
            accept(lab, m, (lab['x'], lab['y']))
        else:
            still.append(lab)
    # Pass C: ring search around the label for an unclaimed enclosed region.
    for lab in still:
        found = None
        for radius in (10, 16, 24, 32):
            for k in range(12):
                a = 2 * np.pi * k / 12
                sd = (lab['x'] + radius * np.cos(a), lab['y'] + radius * np.sin(a))
                m = flood(img, (sd[0] * SCALE, sd[1] * SCALE), tol=2)
                if valid(m, lab):
                    found = m
                    break
            if found is not None:
                break
        if found is not None:
            accept(lab, found, sd)
            continue
        # Pass D: a small room whose door is drawn without a swing (focus rooms, booths) leaks
        # through the opening. Closing the raster around the label bridges the opening (the
        # closing does not thicken lines, it only fills gaps narrower than the kernel). Open
        # plan labels are left alone: they are meant to leak.
        if category(lab['name'], lab['id']) in ('open', 'circulation'):
            print(f"  open: {lab['id']} ({lab['name']})")
            open_labels.append(lab)
            continue
        x, y = int(lab['x'] * SCALE), int(lab['y'] * SCALE)
        win = (slice(max(0, y - 120), y + 120), slice(max(0, x - 120), x + 120))
        for k in (11, 17, 23, 31):
            local = img.copy()
            local[win] = cv2.morphologyEx(img[win], cv2.MORPH_CLOSE, np.ones((k, k), np.uint8))
            for radius in (0, 10, 16, 24, 32):
                for j in range(12 if radius else 1):
                    a = 2 * np.pi * j / 12
                    sd = (lab['x'] + radius * np.cos(a), lab['y'] + radius * np.sin(a))
                    m = flood(local, (sd[0] * SCALE, sd[1] * SCALE), tol=2)
                    if m is not None and POD_ROOM <= np.count_nonzero(m) <= SMALL_ROOM and why(m, lab) in (None, f'area {np.count_nonzero(m)}'):
                        found = m
                        break
                if found is not None:
                    break
            if found is not None:
                sealed[lab['id']] = (win, k)
                print(f"  sealed: {lab['id']} ({lab['name']}) with a {k} px closing")
                accept(lab, found, sd)
                break
        if found is None:
            print(f"  open: {lab['id']} ({lab['name']})")
            open_labels.append(lab)
    # Pass E: phone-booth pods stand with an open front, so no closing seals them; the pod is
    # the box spanned by the medium-length strokes drawn around its label (its three sides).
    # Pods side by side share a side: each stroke counts for the label nearest to it.
    pods = [lab for lab in open_labels if category(lab['name'], lab['id']) == 'focus']
    if pods:
        segs = np.array(geom['segs'])
        length = np.hypot(segs[:, 2] - segs[:, 0], segs[:, 3] - segs[:, 1])
        cand = segs[(segs[:, 5] == 1) & (segs[:, 7] == 0) & (length >= 18) & (length <= 50)]
        mids = (cand[:, :2] + cand[:, 2:4]) / 2
        P = np.array([[lab['x'], lab['y']] for lab in pods])
        dist = np.hypot(mids[:, None, 0] - P[None, :, 0], mids[:, None, 1] - P[None, :, 1])
        owner = dist.argmin(1)
        for j, lab in enumerate(pods):
            mine = cand[(owner == j) & (dist[:, j] <= 40)]
            if len(mine) < 3:
                continue
            pts = np.vstack([mine[:, :2], mine[:, 2:4]]).astype(np.float32)
            (cx, cy), (w, h), ang = cv2.minAreaRect(pts)
            if not (15 <= min(w, h) <= 60 and max(w, h) <= 90):
                continue
            region = np.zeros_like(img)
            cv2.fillPoly(region, [np.round(cv2.boxPoints(((cx, cy), (w, h), ang)) * SCALE).astype(np.int32)], 255)
            region[taken > 0] = 0
            if np.count_nonzero(region) < POD_ROOM:
                continue
            sealed[lab['id']] = None
            accept(lab, region, None)
            open_labels.remove(lab)
            print(f"  pod: {lab['id']} ({lab['name']}) boxed from the strokes around it")
    # Polygons are fitted only now that every room's fill is known, so the furniture-free
    # re-fill of each room is kept off its neighbours whichever was accepted first.
    for r in rooms:
        r['polygon'] = room_poly(r['id'], room_masks[r['id']], seeds_used.get(r['id']))
    # unenclosed free space -> partition between open labels (geodesic Voronoi). Traced on the
    # furniture-free raster so desks and chairs do not carve the open areas.
    free = (walls == 0) & (exterior == 0) & (enclosed == 0)
    furniture = []
    if open_labels:
        markers = np.zeros(img.shape, np.int32)
        for i, lab in enumerate(open_labels, 1):
            x, y = int(lab['x'] * SCALE), int(lab['y'] * SCALE)
            if not free[y, x]:  # the label text may sit on a wall: seed from the nearest free pixel
                ys, xs = np.nonzero(free[max(0, y - 8):y + 9, max(0, x - 8):x + 9])
                if len(xs):
                    k = np.argmin((xs + max(0, x - 8) - x) ** 2 + (ys + max(0, y - 8) - y) ** 2)
                    x, y = xs[k] + max(0, x - 8), ys[k] + max(0, y - 8)
            cv2.circle(markers, (x, y), 3, i, -1)
        markers[~free] = 0
        ws = watershed(np.zeros(img.shape, np.uint8), markers, mask=free)
        for i, lab in enumerate(open_labels, 1):
            m = (ws == i).astype(np.uint8)
            # keep only the component holding the seed
            n, cc = cv2.connectedComponents(m)
            k = cc[int(lab['y'] * SCALE), int(lab['x'] * SCALE)]
            if not k:  # label on a wall pixel: the component nearest to it
                ys, xs = np.nonzero(m)
                if len(xs):
                    k = cc[ys[np.argmin((xs - lab['x'] * SCALE) ** 2 + (ys - lab['y'] * SCALE) ** 2)], xs[np.argmin((xs - lab['x'] * SCALE) ** 2 + (ys - lab['y'] * SCALE) ** 2)]]
            m = (cc == k).astype(np.uint8) if k else m
            if (lab['id'] in cfg.get('smooth', set()) or any(w in lab['name'].upper() for w in SMOOTH_NAMES)) and not (cfg.get('sign') and 'PIAZZA' in lab['name'].upper()):
                # a piazza or porch: a sweeping shape with a gap to the rooms, not a tracing of
                # every notch along them
                k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (SMOOTH_OPEN, SMOOTH_OPEN))
                m = cv2.morphologyEx(m * 255, cv2.MORPH_CLOSE, k)
                m = cv2.erode(m, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * SMOOTH_INSET + 1, 2 * SMOOTH_INSET + 1)))
                m = cv2.morphologyEx(m, cv2.MORPH_OPEN, k)  # after the inset, so no thin tails survive
                poly = straight_runs(m, EPS, eps_coarse=20, min_len=40)
            else:
                poly = straight_runs(m, EPS, eps_coarse=16, min_len=20, close=9, smooth=SMOOTH)
            if poly is None:
                print('  empty open cell for', lab['id'])
                continue
            rooms.append({**lab, 'kind': 'open', 'area': int(np.count_nonzero(m)), 'polygon': poly})
        furniture = desks(geom, (ws > 0).astype(np.uint8))
    # outline(s): components of the non-exterior that hold labels
    # Thin site lines between two exterior areas would join separate blocks; erode them away.
    inside = cv2.erode((exterior == 0).astype(np.uint8), np.ones((5, 5), np.uint8))
    n, cc = cv2.connectedComponents(inside)
    comps = {}
    for lab in labs:
        k = cc[int(lab['y'] * SCALE), int(lab['x'] * SCALE)]
        comps[k] = comps.get(k, 0) + 1
    outlines = []
    for k in sorted(comps, key=lambda k: -comps[k]):
        if k == 0:  # a label standing outside (e.g. on a roof terrace) is not an outline
            continue
        # close the mullion ticks along the curtain walls, then trace
        # the exterior trace carries the mullion ticks, so a curved facade fits a circle less tightly
        outlines.append(straight_runs((cc == k).astype(np.uint8), EPS, eps_coarse=8, min_len=60, close=9, smooth=SMOOTH, curve_res=4.0))
    # unlabelled enclosed regions (stairs, elevators, restrooms, mechanical ...) for hand labelling
    rest = ((img == 0) & (exterior == 0) & (enclosed == 0)).astype(np.uint8)
    if open_labels:
        rest[ws > 0] = 0
    n, cc, stats, cents = cv2.connectedComponentsWithStats(rest, connectivity=4)  # match the 4-connected flood fill
    unl = []
    tiny = np.zeros_like(img)
    for k in range(1, n):
        area = int(stats[k, cv2.CC_STAT_AREA])
        if area < TINY:
            # skip wall cavities (thin slivers), which would bridge unrelated cells
            if area >= 4 and min(stats[k, cv2.CC_STAT_WIDTH], stats[k, cv2.CC_STAT_HEIGHT]) >= 4:
                tiny[cc == k] = 255
            continue
        m = _prep((cc == k).astype(np.uint8) * 255, 0, 5)
        poly = straighten(m) or straight_runs(m, EPS, eps_coarse=4, min_len=25)
        if poly is None or len(poly) < 3:
            continue
        unl.append({'area': area, 'x': round(float(cents[k][0] / SCALE), 1), 'y': round(float(cents[k][1] / SCALE), 1), 'polygon': poly})
    # Hatched floors (restroom tiles), stair treads and elevator X marks chop a room into many
    # tiny cells; adjacent tiny cells are merged back into one region.
    clusters = cv2.dilate(tiny, np.ones((3, 3), np.uint8))
    n2, cc2, stats2, cents2 = cv2.connectedComponentsWithStats(clusters)
    for k in range(1, n2):
        area = int(stats2[k, cv2.CC_STAT_AREA])
        if area < TINY:
            continue
        m = ((cc2 == k) * 255).astype(np.uint8)
        m = _prep(cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8)), 0, 5)
        poly = straighten(m) or straight_runs(m, EPS, eps_coarse=4, min_len=25)
        if poly is None or len(poly) < 3:
            continue
        unl.append({'area': area, 'x': round(float(cents2[k][0] / SCALE), 1), 'y': round(float(cents2[k][1] / SCALE), 1), 'polygon': poly, 'cluster': True})
    unl.sort(key=lambda u: -u['area'])
    for i, u in enumerate(unl):
        u['idx'] = i
    # The piazzas: their shape comes from the wayfinding sign (the white band between the
    # wings, registered onto the outline), split between the piazza labels and cut away from
    # the rooms and cores the CAD knows precisely.
    if cfg.get('sign') and outlines:
        sign_path, hint = cfg['sign']
        band, _, info = sign.shapes(os.path.join(HERE, '..', '..', 'floorplans', sign_path), np.array(_xy(outlines[0])), hint)
        print(f"  sign {sign_path}: outline residual median {info['median']:.1f} px, p90 {info['p90']:.1f} px")
        piazzas = [r for r in rooms if 'PIAZZA' in r['name'].upper() and r.get('polygon')]
        if band is not None and piazzas:
            from shapely.geometry import MultiPoint
            from shapely.ops import unary_union, voronoi_diagram
            B = Polygon(band).buffer(0).intersection(Polygon(_xy(outlines[0])).buffer(0))
            blockers = [Polygon(_xy(r['polygon'])).buffer(4) for r in rooms if r['kind'] == 'room' and r not in piazzas and r.get('polygon')]
            blockers += [Polygon(_xy(u['polygon'])).buffer(4) for u in unl if u['area'] > 800]
            block = unary_union(blockers)
            L = MultiPoint([(r['x'], r['y']) for r in piazzas])
            minx, miny, maxx, maxy = B.bounds
            env = Polygon([(minx - 500, miny - 500), (maxx + 500, miny - 500), (maxx + 500, maxy + 500), (minx - 500, maxy + 500)])
            for cell in voronoi_diagram(L, envelope=env).geoms:
                r = min(piazzas, key=lambda r: cell.distance(Point(r['x'], r['y'])))
                g = B.intersection(cell).difference(block)
                if isinstance(g, MultiPolygon):
                    g = max(g.geoms, key=lambda q: q.area)
                if g.is_empty:
                    continue
                g = g.simplify(1.0)
                r['polygon'] = [[round(float(x), 1), round(float(y), 1)] for x, y in g.exterior.coords[:-1]]
                r['kind'] = 'open'  # the sign's band is circulation around the atrium
                if 'open plan' not in r.get('name', ''):
                    pass
            print(f"  piazzas {[r['id'] for r in piazzas]} drawn from the sign")
    # Rooms may touch but not overlap: enclosed rooms keep their shape, then the unlabelled
    # regions (cores), then the open areas.
    n_fixed = reconcile([(0, r) for r in rooms if r['kind'] == 'room' and r.get('polygon')]
                        + [(1, u) for u in unl] + [(2, r) for r in rooms if r['kind'] == 'open' and r.get('polygon')])
    print(f'  {n_fixed} polygons trimmed to remove overlaps')
    # Curves (the atrium, the piazzas, the curved facades) become circular arcs.
    closed = [r['polygon'] for r in rooms if r['kind'] == 'room' and r.get('polygon')]
    arcify_all(closed + [u['polygon'] for u in unl] + [r['polygon'] for r in rooms if r['kind'] == 'open' and r.get('polygon')] + outlines, n_straight=len(closed))
    # a facade traced as a zigzag of mullion ticks is one straight wall, and a facade bay
    # that came out as two shallow pieces is one arc
    outlines = [merge_collinear(o, flat=0.08, max_dev=8.0) for o in outlines]
    arcify_all(outlines, n_straight=0, refit_small=0.1, tol=3.0, min_run=2, short=250.0)
    for r in rooms:
        if r['kind'] == 'open' and r.get('polygon'):
            r['polygon'] = merge_collinear(r['polygon'])
    # Exterior doors: door arcs whose midpoint lies on the outline -> entrances.
    exits = []
    if cfg.get('exits') and outlines:
        conts = [np.array(o, np.float32) for o in outlines]
        for mid, out, _ in arcs:
            d = min(abs(cv2.pointPolygonTest(c, (float(mid[0]), float(mid[1])), True)) for c in conts)
            if d <= 12 and all(np.hypot(mid[0] - ex, mid[1] - ey) > 40 for ex, ey in exits):
                exits.append([round(float(mid[0]), 1), round(float(mid[1]), 1)])
    json.dump({'floor': floor, 'rooms': rooms, 'outlines': outlines, 'unlabelled': unl, 'exits': exits, 'desks': furniture}, open(out_prefix + '_rooms.json', 'w'))
    if VERBOSE:  # the room masks (bbox crops with their offset) and seeds, for debugging offline
        raw = {}
        for k, m in room_masks.items():
            ys, xs = np.nonzero(m)
            raw[k + '_raw'] = m[ys.min():ys.max() + 1, xs.min():xs.max() + 1].copy()
            raw[k + '_raw_at'] = np.array([ys.min(), xs.min()], np.int32)
        np.savez_compressed(out_prefix + '_masks.npz', **{k: np.array([y0, x0], np.int32) for k, (y0, x0, _) in clean_masks.items()},
                            **{k + '_mask': crop for k, (_, _, crop) in clean_masks.items()}, **raw,
                            **{k + '_seed': np.array(v, float) for k, v in seeds_used.items() if v is not None})
        np.save(out_prefix + '_img.npy', img)
        np.save(out_prefix + '_walls.npy', walls)
    # debug overlay
    dbg = cv2.cvtColor(255 - img, cv2.COLOR_GRAY2BGR)
    dbg[exterior > 0] = (235, 235, 235)
    rng = np.random.default_rng(1)
    for r in rooms:
        col = tuple(int(v) for v in rng.integers(80, 230, 3))
        p = np.round(np.array(_xy(r['polygon'])) * SCALE).astype(np.int32)
        cv2.fillPoly(dbg, [p], col) if r['kind'] == 'room' else cv2.polylines(dbg, [p], True, col, 2)
        cv2.putText(dbg, r['id'], (int(r['x'] * SCALE) - 8, int(r['y'] * SCALE) + 3), cv2.FONT_HERSHEY_SIMPLEX, 0.3, (0, 0, 0), 1)
    for u in unl:
        p = np.round(np.array(_xy(u['polygon'])) * SCALE).astype(np.int32)
        cv2.polylines(dbg, [p], True, (0, 0, 255), 1)
        cv2.putText(dbg, f"u{u['idx']}", (int(u['x'] * SCALE) - 6, int(u['y'] * SCALE) + 3), cv2.FONT_HERSHEY_SIMPLEX, 0.28, (0, 0, 200), 1)
    for o in outlines:
        cv2.polylines(dbg, [np.round(np.array(_xy(o)) * SCALE).astype(np.int32)], True, (200, 0, 200), 2)
    for dsk in furniture:
        cv2.polylines(dbg, [np.round(np.array(dsk) * SCALE).astype(np.int32)], True, (200, 120, 0), 1)
    cv2.imwrite(out_prefix + '_debug.png', dbg)
    print(f'floor {floor}: {sum(r["kind"] == "room" for r in rooms)} enclosed rooms, {len(open_labels)} open areas, {len(furniture)} desks, {len(outlines)} outline(s), {len(unl)} unlabelled regions, {len(exits)} exits')
    return rooms, outlines, unl


if __name__ == '__main__':
    VERBOSE = '-v' in sys.argv
    args = [a for a in sys.argv[1:] if a != '-v']
    run(args[0], args[1], args[2])
