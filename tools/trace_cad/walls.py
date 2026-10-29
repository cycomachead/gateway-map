"""The wall-only drawing of one sheet: walls, column discs and door closures.

Usage: python3 walls.py <floor id> <workdir>

Reads <workdir>/<pdf>_geom.json (from extract.py) and the floor's patch file
(patches/floor-<id>.json, optional) and writes <workdir>/<pdf>_walls.json and
<workdir>/<pdf>_walls.pdf, the simplified drawing: walls black, columns blue, door closures
red, patch lines green, room labels grey. The PDF is the page a person checks and reads
coordinates from when adding a patch line.

See docs/superpowers/specs/2026-10-29-vector-tracer-design.md.
"""
import json
import math
import os
import sys

import numpy as np

from floors import FLOORS
from patches import load_patches

HERE = os.path.dirname(os.path.abspath(__file__))

MIN_LINE = 0.5      # pt; shorter black strokes are text and hatching
BORDER = (72.0, 54.0, 3230.0, 2538.0)   # the plan area of the 48"x36" sheets (title block to the right)
COLUMN_R = (2.5, 9.0)   # pt; structural columns (round tables and chairs are larger)
COLUMN_RES = 0.4        # pt; max deviation of a column's strokes from its circle
COLUMN_TOUCH = 4.0      # pt; a column is only kept when a wall stroke at least this long meets it
DOOR_R = (7.0, 24.0)    # pt; door-leaf radii (2' to 5' doors at 1/16" = 1')
DOOR_RES = 0.6
DOOR_SWEEP = (60.0, 120.0)  # degrees


def fit_circle(pts):
    """Algebraic least-squares circle through the points: ((cx, cy), r, max deviation)."""
    pts = np.asarray(pts, float)
    x, y = pts[:, 0], pts[:, 1]
    A = np.c_[2 * x, 2 * y, np.ones(len(pts))]
    b = x ** 2 + y ** 2
    sol, *_ = np.linalg.lstsq(A, b, rcond=None)
    cx, cy, c = sol
    r = math.sqrt(max(c + cx ** 2 + cy ** 2, 0))
    res = float(np.abs(np.hypot(x - cx, y - cy) - r).max())
    return (float(cx), float(cy)), float(r), res


def scale_of(cfg):
    """Sheets drawn at another scale (the Lower Level) scale every length by their label size."""
    return cfg.get('label_sizes', (3.5, 5.0))[1] / 5.0


def wall_strokes(geom, scale):
    """Black, unfilled, non-furniture strokes of wall length inside the plan border."""
    x0, y0, x1, y1 = BORDER
    x0, y0, x1, y1 = x0 + 3, y0 + 3, x1 - 3, y1 - 3   # the sheet's own frame line runs on the border
    out = []
    for s in geom['segs']:
        ax, ay, bx, by, _w, black, filled, furn = s
        if not black or filled or furn:
            continue
        if math.hypot(bx - ax, by - ay) < MIN_LINE * scale:
            continue
        if not (x0 <= ax <= x1 and y0 <= ay <= y1):
            continue
        out.append([ax, ay, bx, by])
    return out


def circles(geom):
    """Closed circles drawn as a chained polyline or as four béziers: [(cx, cy, r)]."""
    found = []
    for pl in geom.get('polylines', []):
        if len(pl) < 8 or math.dist(pl[0], pl[-1]) > 1.0:
            continue
        (cx, cy), r, res = fit_circle(pl)
        if res <= COLUMN_RES:
            found.append((cx, cy, r))
    curves = [c for c in geom.get('curves', []) if c[5]]
    i = 0
    while i + 3 < len(curves):
        q = curves[i:i + 4]
        if all(math.dist(q[k][3], q[k + 1][0]) < 0.05 for k in range(3)) and math.dist(q[3][3], q[0][0]) < 0.05:
            pts = [pt for c in q for pt in c[:4]]
            (cx, cy), r, res = fit_circle(pts)
            if res <= 0.5:
                found.append((cx, cy, r))
            i += 4
        else:
            i += 1
    return found


def column_discs(geom, walls, scale):
    """Columns: circles of column size whose rim meets a wall stroke."""
    from shapely.geometry import LineString, Point
    from shapely.strtree import STRtree
    lines = [LineString([(a, b), (c, d)]) for a, b, c, d in walls]
    tree = STRtree(lines)
    lo, hi = COLUMN_R[0] * scale, COLUMN_R[1] * scale
    out = []
    for cx, cy, r in circles(geom):
        if not (lo <= r <= hi):
            continue
        disc = Point(cx, cy).buffer(r + 0.5)
        if any(lines[i].length >= COLUMN_TOUCH * scale and lines[i].intersects(disc) for i in tree.query(disc)):
            out.append([round(cx, 2), round(cy, 2), round(r, 2)])
    return out


def door_arcs(geom, scale):
    """Door swings: [(hinge, radius, arc start, arc end)] for every polyline or bézier lying
    on a circle of door-leaf radius and sweeping roughly a quarter turn."""
    cands = list(geom.get('polylines', []))
    for c in geom.get('curves', []):
        if not c[5]:
            continue
        p0, p1, p2, p3 = (np.array(p, float) for p in c[:4])
        if np.linalg.norm(p3 - p0) < 10 * scale:
            continue
        cands.append([((1 - t) ** 3 * p0 + 3 * (1 - t) ** 2 * t * p1 + 3 * (1 - t) * t ** 2 * p2 + t ** 3 * p3).tolist()
                      for t in np.linspace(0, 1, 7)])
    lo, hi = DOOR_R[0] * scale, DOOR_R[1] * scale
    doors = []
    for pts in cands:
        if len(pts) < 4:
            continue
        (cx, cy), r, res = fit_circle(pts)
        if not (lo <= r <= hi) or res > DOOR_RES * scale:
            continue
        a0 = math.atan2(pts[0][1] - cy, pts[0][0] - cx)
        a1 = math.atan2(pts[-1][1] - cy, pts[-1][0] - cx)
        sweep = math.degrees(abs((a1 - a0 + math.pi) % (2 * math.pi) - math.pi))
        if not (DOOR_SWEEP[0] <= sweep <= DOOR_SWEEP[1]):
            continue
        doors.append(((cx, cy), r, tuple(pts[0]), tuple(pts[-1])))
    return doors


def closures_of(doors):
    """Both chords of every swing, hinge to each arc end: one lies across the doorway and
    seals the room, the other along the open leaf and only costs a thin notch."""
    out = []
    for (cx, cy), _r, p0, p1 in doors:
        out.append([round(cx, 2), round(cy, 2), round(p0[0], 2), round(p0[1], 2)])
        out.append([round(cx, 2), round(cy, 2), round(p1[0], 2), round(p1[1], 2)])
    return out


def build(fid, workdir):
    cfg = FLOORS[fid]
    geom = json.load(open(os.path.join(workdir, f"{cfg['pdf']}_geom.json")))
    scale = scale_of(cfg)
    patches = load_patches(fid)
    walls = wall_strokes(geom, scale)
    cols = column_discs(geom, walls, scale)
    doors = door_arcs(geom, scale)
    closures = closures_of(doors)
    out = {
        'floor': fid,
        'scale': scale,
        'page': geom['page'],
        'walls': [[round(v, 2) for v in w] for w in walls],
        'columns': cols,
        'closures': closures,
        'doors': [[round(c[0], 2), round(c[1], 2), round(r, 2), [round(v, 2) for v in p0], [round(v, 2) for v in p1]] for c, r, p0, p1 in doors],
        'patch_lines': patches['lines'],
    }
    prefix = os.path.join(workdir, cfg['pdf'])
    json.dump(out, open(prefix + '_walls.json', 'w'))
    draw(out, geom, prefix + '_walls.pdf')
    print(f"floor {fid}: {len(walls)} wall strokes, {len(cols)} columns, {len(doors)} doors, {len(patches['lines'])} patch lines -> {prefix}_walls.pdf")
    return out


def draw(w, geom, path):
    """The simplified drawing as a PDF the size of the sheet."""
    import pymupdf
    doc = pymupdf.open()
    page = doc.new_page(width=w['page'][0], height=w['page'][1])
    shape = page.new_shape()
    for a, b, c, d in w['walls']:
        shape.draw_line((a, b), (c, d))
    shape.finish(color=(0, 0, 0), width=0.5)
    for a, b, c, d in w['closures']:
        shape.draw_line((a, b), (c, d))
    shape.finish(color=(0.85, 0, 0), width=0.6)
    for a, b, c, d, *_ in w['patch_lines']:
        shape.draw_line((a, b), (c, d))
    shape.finish(color=(0, 0.6, 0), width=0.8)
    for cx, cy, r in w['columns']:
        shape.draw_circle((cx, cy), r)
    shape.finish(color=(0, 0, 0.8), fill=(0.3, 0.3, 0.9), width=0.3)
    shape.commit()
    for ln in geom['lines']:
        x0, y0, x1, y1 = ln['bbox']
        if x1 > BORDER[2] or ln['size'] > 9:
            continue
        page.insert_text((x0, y1), ln['text'], fontsize=min(ln['size'], 6), color=(0.45, 0.45, 0.45))
    doc.save(path)


if __name__ == '__main__':
    build(sys.argv[1], sys.argv[2])
