"""Read the generated floor modules (src/data/gateway/level*.ts) back into Python.

The modules are machine-written by tools/trace_cad/emit_ts.py in a fixed one-room-per-line
format, so each room line can be turned into JSON with a few substitutions. Coordinates are
the shared floor frame; `to_sheet` maps them back onto the upper-floor sheets' PDF points
(see tools/trace_cad/README.md) using the origin recorded in frame.ts.
"""
import json
import math
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
GATEWAY = os.path.normpath(os.path.join(HERE, '..', '..', 'src', 'data', 'gateway'))
LEVELS = ['0', '1', '2', '3', '4', '5']

_STR = re.compile(r"'((?:[^'\\]|\\.)*)'")
_KEY = re.compile(r'(?<=[{,] )(\w+):')
_ID_SEP = re.compile(r"[\s’']+")


def _ts_to_json(line: str) -> str:
    line = line.strip().rstrip(',')
    line = _STR.sub(lambda m: json.dumps(m.group(1).replace("\\'", "'").replace('\\\\', '\\')), line)
    line = _KEY.sub(r'"\1":', line)
    return line.replace('undefined', 'null')


def read_origin():
    src = open(os.path.join(GATEWAY, 'frame.ts')).read()
    m = re.search(r'ORIGIN = \{ x: ([\d.-]+), y: ([\d.-]+) \}', src)
    return float(m.group(1)), float(m.group(2))


def read_rooms(level: str):
    """[{'wing', 'id', 'category', 'polygon', 'extra', 'space_id'}] for one level, in frame coordinates."""
    src = open(os.path.join(GATEWAY, f'level{level}.ts')).read()
    body = src.split('export const rooms: RoomSpec[] = [', 1)[1].split('\n];', 1)[0]
    rooms = []
    for line in body.strip().splitlines():
        if not line.strip().startswith('['):
            continue
        wing, rid, cat, poly, *extra = json.loads(_ts_to_json(line))
        rooms.append({
            'wing': wing, 'id': rid, 'category': cat, 'polygon': poly, 'extra': extra[0] if extra else {},
            'space_id': f'{level}-{_ID_SEP.sub("-", rid.lower())}',
        })
    return rooms


def flatten(poly, max_angle=math.pi / 12):
    """Polygon vertices with every bulged edge replaced by points along its arc (the same
    construction as src/map/geometry.ts: positive bulge bows to the right of travel, y down)."""
    out = []
    n = len(poly)
    for i in range(n):
        p, q = poly[i], poly[(i + 1) % n]
        ax, ay, bx, by = p[0], p[1], q[0], q[1]
        bulge = p[2] if len(p) > 2 else 0
        out.append((ax, ay))
        if not bulge:
            continue
        dx, dy = bx - ax, by - ay
        chord = math.hypot(dx, dy)
        if chord < 1e-9:
            continue
        theta = 4 * math.atan(abs(bulge))
        r = chord / (2 * math.sin(theta / 2))
        sagitta = abs(bulge) * chord / 2
        sign = 1 if bulge > 0 else -1
        nx, ny = (-dy / chord) * sign, (dx / chord) * sign
        mx, my = (ax + bx) / 2, (ay + by) / 2
        cx, cy = mx - nx * (r - sagitta), my - ny * (r - sagitta)
        a0 = math.atan2(ay - cy, ax - cx)
        a_mid = math.atan2(my + ny * sagitta - cy, mx + nx * sagitta - cx)
        d = a_mid - a0
        while d <= -math.pi:
            d += 2 * math.pi
        while d > math.pi:
            d -= 2 * math.pi
        sweep = math.copysign(theta, d) if d else theta
        steps = max(1, math.ceil(abs(sweep) / max_angle))
        for k in range(1, steps):
            ang = a0 + sweep * k / steps
            out.append((cx + r * math.cos(ang), cy + r * math.sin(ang)))
    return out


def to_sheet(points, origin):
    ox, oy = origin
    return [(x + ox, y + oy) for x, y in points]
