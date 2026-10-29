"""A PNG of one traced floor over its simplified drawing, coloured by parity with the level file.

Usage: python3 preview.py <workdir> <floor id> <out.png> [scale]

Rooms are filled green (IoU >= 0.9 with the committed level file), yellow (>= 0.8), red
(below) or blue (not in the level file / not scored); unlabelled regions grey; the level
file's rooms the tracer missed are outlined magenta. Walls black, door closures red, patch
lines green, columns blue.
"""
import json
import os
import sys

from PIL import Image, ImageDraw
from shapely.geometry import Polygon

from compare import report
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'departments'))
from levels import flatten  # noqa: E402
from floors import FLOORS


def render(workdir, fid, out, scale=0.5):
    cfg = FLOORS[fid]
    prefix = os.path.join(workdir, cfg['pdf'])
    w = json.load(open(prefix + '_walls.json'))
    rooms = json.load(open(prefix + '_rooms.json'))
    rows = {r[0]: r for r in report(workdir, fid)}
    W, H = int(w['page'][0] * scale), int(w['page'][1] * scale)
    im = Image.new('RGB', (W, H), 'white')
    dr = ImageDraw.Draw(im)
    S = lambda pts: [(x * scale, y * scale) for x, y in pts]
    for u in rooms['unlabelled']:
        dr.polygon(S(flatten(u['polygon'])), fill=(225, 225, 225))
    for r in rooms['rooms']:
        row = rows.get(r['id'])
        v = row[3] if row else None
        col = (190, 215, 245) if v is None else (180, 240, 180) if v >= 0.9 else (250, 230, 150) if v >= 0.8 else (250, 170, 170)
        dr.polygon(S(flatten(r['polygon'])), fill=col)
        for h in r.get('holes', []):
            dr.polygon(S(flatten(h)), fill='white')
    for o in rooms['outlines']:
        dr.polygon(S(flatten(o)), outline=(90, 90, 90))
    for a, b, c, d in w['walls']:
        dr.line([(a * scale, b * scale), (c * scale, d * scale)], fill=(0, 0, 0))
    for a, b, c, d in w['closures']:
        dr.line([(a * scale, b * scale), (c * scale, d * scale)], fill=(220, 0, 0), width=2)
    for a, b, c, d, *_ in w['patch_lines']:
        dr.line([(a * scale, b * scale), (c * scale, d * scale)], fill=(0, 160, 0), width=2)
    for cx, cy, r in w['columns']:
        dr.ellipse([(cx - r) * scale, (cy - r) * scale, (cx + r) * scale, (cy + r) * scale], fill=(80, 80, 230))
    for x, y in rooms['exits']:
        dr.ellipse([x * scale - 4, y * scale - 4, x * scale + 4, y * scale + 4], outline=(0, 120, 0), width=2)
    # the level file's rooms the tracer has no polygon for
    from compare import frame_to_sheet
    from levels import read_rooms
    to_sheet = frame_to_sheet(fid)
    for r in read_rooms(fid):
        row = rows.get(r['id'].upper())
        if row and row[2] == 'missing':
            pts = [to_sheet(x, y) for x, y in flatten(r['polygon'])]
            dr.polygon(S(pts), outline=(200, 0, 200), width=2)
    # crop to the plan
    xs = [x for o in rooms['outlines'] for x, _ in o]
    ys = [y for o in rooms['outlines'] for _, y in o]
    pad = 20
    im = im.crop((int(min(xs) * scale) - pad, int(min(ys) * scale) - pad, int(max(xs) * scale) + pad, int(max(ys) * scale) + pad))
    im.save(out, optimize=True)
    print('wrote', out, im.size)


if __name__ == '__main__':
    render(sys.argv[1], sys.argv[2], sys.argv[3], float(sys.argv[4]) if len(sys.argv) > 4 else 0.5)
