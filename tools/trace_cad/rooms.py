"""Segment rooms from the extracted CAD geometry of one floor.

Usage: python3 rooms.py <floor> <geom.json> <out_prefix>

1. Rasterise the "architectural" line work: black strokes longer than MIN_LINE points and
   black bezier arcs with a chord longer than MIN_CURVE (door swings; they seal doorways so
   rooms become closed regions). Short strokes are furniture, hatching and text outlines.
2. Read the room labels (a 4-digit number plus the name lines next to it). Labels usually sit
   in the corridor just outside the room's door, so flood-fill first from the label itself and,
   if that leaks into the corridor network, from just beyond the nearest door swing arc (the
   arc bulges into the room). An enclosed region becomes the room polygon.
3. Labels whose fill leaks into the corridor network are "open" areas: the unenclosed free
   space is partitioned between them by geodesic distance (watershed on the free-space mask).
4. The exterior is the fill from the sheet corner; the building outline is the outer contour
   of the components (containing labels) that are not exterior.
Writes <out_prefix>_rooms.json and a debug overlay <out_prefix>_debug.png.
"""
import json
import re
import sys

import cv2
import numpy as np
from skimage.segmentation import watershed

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


def raster(geom, scale=SCALE, min_line=MIN_LINE, min_curve=MIN_CURVE, extra=(), furniture=True, arcs=()):
    """Line-work raster (255 = stroke). With furniture=False only walls (single strokes and
    long paths) plus the given door arcs are drawn; room polygons are traced on that one so
    desks against a wall do not notch them."""
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


def door_seeds(lab, arcs, radius=45.0):
    """Candidate seeds just beyond the door arcs near a label, nearest first."""
    c = np.array([lab['x'], lab['y']])
    near = sorted(((np.hypot(*(mid - c)), mid, out) for mid, out, _ in arcs), key=lambda t: t[0])
    return [mid + out * 4 for d, mid, out in near if d <= radius][:3]


MAX_ROOM = 150000  # px; anything bigger is the corridor network, not a room
MIN_ROOM = 700     # px; smaller pockets are wall cavities or furniture
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


def contour_poly(mask, eps, close=0):
    m = mask.copy()
    if close:
        m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((close, close), np.uint8))
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
    img = raster(geom, extra=cfg.get('extra', ()), arcs=arcs)
    walls = raster(geom, extra=cfg.get('extra', ()), furniture=False, arcs=arcs)
    labs = labels(geom, cfg.get('label_sizes', LABEL_SIZES), cfg.get('number_re', NUMBER_RE), cfg.get('skip', ()))
    seeds_cfg = cfg.get('seeds', {})
    # Sheets with bigger label text (the Lower Level) place labels further from their door.
    label_scale = cfg.get('label_sizes', LABEL_SIZES)[1] / LABEL_SIZES[1]
    door_dist = DOOR_DIST * label_scale
    min_room = cfg.get('min_room', MIN_ROOM)
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

    def refine(m, seed):
        """Re-fill the room on the furniture-free raster, confined to a band around the
        furnished fill so a wall gap cannot leak it far."""
        band = cv2.dilate(m, np.ones((41, 41), np.uint8))
        barrier = walls | (band == 0).astype(np.uint8) * 255
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

    def accept(lab, m, seed=None):
        room_masks[lab['id']] = m
        seeds_used[lab['id']] = seed
        enclosed[m > 0] = 255
        taken[m > 0] = 255
        clean = refine(m, seed)
        rooms.append({**lab, 'kind': 'room', 'area': int(np.count_nonzero(m)), 'polygon': contour_poly(clean, 1.2)})

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
                        other['polygon'] = contour_poly(refine(a, seeds_used[other['id']]), 1.2)
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
        else:
            print(f"  open: {lab['id']} ({lab['name']})")
            open_labels.append(lab)
    # unenclosed free space -> partition between open labels (geodesic Voronoi)
    free = (img == 0) & (exterior == 0) & (enclosed == 0)
    if open_labels:
        markers = np.zeros(img.shape, np.int32)
        for i, lab in enumerate(open_labels, 1):
            x, y = int(lab['x'] * SCALE), int(lab['y'] * SCALE)
            cv2.circle(markers, (x, y), 3, i, -1)
        markers[~free] = 0
        ws = watershed(np.zeros(img.shape, np.uint8), markers, mask=free)
        for i, lab in enumerate(open_labels, 1):
            m = (ws == i).astype(np.uint8)
            # keep only the component holding the seed
            n, cc = cv2.connectedComponents(m)
            k = cc[int(lab['y'] * SCALE), int(lab['x'] * SCALE)]
            m = (cc == k).astype(np.uint8) if k else m
            poly = contour_poly(m, 2.5, close=9)
            if poly is None:
                print('  empty open cell for', lab['id'])
                continue
            rooms.append({**lab, 'kind': 'open', 'area': int(np.count_nonzero(m)), 'polygon': poly})
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
        outlines.append(contour_poly((cc == k).astype(np.uint8), 1.5, close=9))
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
        m = (cc == k).astype(np.uint8)
        poly = contour_poly(m, 1.2)
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
        m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
        poly = contour_poly(m, 1.5)
        if poly is None or len(poly) < 3:
            continue
        unl.append({'area': area, 'x': round(float(cents2[k][0] / SCALE), 1), 'y': round(float(cents2[k][1] / SCALE), 1), 'polygon': poly, 'cluster': True})
    unl.sort(key=lambda u: -u['area'])
    for i, u in enumerate(unl):
        u['idx'] = i
    # Exterior doors: door arcs whose midpoint lies on the outline -> entrances.
    exits = []
    if cfg.get('exits') and outlines:
        conts = [np.array(o, np.float32) for o in outlines]
        for mid, out, _ in arcs:
            d = min(abs(cv2.pointPolygonTest(c, (float(mid[0]), float(mid[1])), True)) for c in conts)
            if d <= 12 and all(np.hypot(mid[0] - ex, mid[1] - ey) > 40 for ex, ey in exits):
                exits.append([round(float(mid[0]), 1), round(float(mid[1]), 1)])
    json.dump({'floor': floor, 'rooms': rooms, 'outlines': outlines, 'unlabelled': unl, 'exits': exits}, open(out_prefix + '_rooms.json', 'w'))
    # debug overlay
    dbg = cv2.cvtColor(255 - img, cv2.COLOR_GRAY2BGR)
    dbg[exterior > 0] = (235, 235, 235)
    rng = np.random.default_rng(1)
    for r in rooms:
        col = tuple(int(v) for v in rng.integers(80, 230, 3))
        p = np.round(np.array(r['polygon']) * SCALE).astype(np.int32)
        cv2.fillPoly(dbg, [p], col) if r['kind'] == 'room' else cv2.polylines(dbg, [p], True, col, 2)
        cv2.putText(dbg, r['id'], (int(r['x'] * SCALE) - 8, int(r['y'] * SCALE) + 3), cv2.FONT_HERSHEY_SIMPLEX, 0.3, (0, 0, 0), 1)
    for u in unl:
        p = np.round(np.array(u['polygon']) * SCALE).astype(np.int32)
        cv2.polylines(dbg, [p], True, (0, 0, 255), 1)
        cv2.putText(dbg, f"u{u['idx']}", (int(u['x'] * SCALE) - 6, int(u['y'] * SCALE) + 3), cv2.FONT_HERSHEY_SIMPLEX, 0.28, (0, 0, 200), 1)
    for o in outlines:
        cv2.polylines(dbg, [np.round(np.array(o) * SCALE).astype(np.int32)], True, (200, 0, 200), 2)
    cv2.imwrite(out_prefix + '_debug.png', dbg)
    print(f'floor {floor}: {sum(r["kind"] == "room" for r in rooms)} enclosed rooms, {len(open_labels)} open areas, {len(outlines)} outline(s), {len(unl)} unlabelled regions, {len(exits)} exits')
    return rooms, outlines, unl


if __name__ == '__main__':
    VERBOSE = '-v' in sys.argv
    args = [a for a in sys.argv[1:] if a != '-v']
    run(args[0], args[1], args[2])
