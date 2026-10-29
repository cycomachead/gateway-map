"""Per-floor hand patches for the vector tracer: extra wall lines and open-area polygons.

`patches/floor-<label>.json` (label as on the floor buttons: ll, 1 ... 5), in the sheet's PDF
points, read off the simplified drawing (`<pdf>_walls.pdf`):

    { "lines": [[x0, y0, x1, y1, "3353: door drawn without a swing"], ...],
      "areas": { "3150": [[x, y], [x, y], ...], ... } }

`lines` are walls the sheet does not draw (a doorway without a swing, a gap at a glass
front). `areas` are the open-plan rooms, whose label sits in the corridor network; the
polygon is clipped to the free space when the rooms are built. A room that is not open-plan
(a booth, a room the walls do not trace well) is drawn exactly as given, bulges included.
Missing file: no patches.
"""
import json
import os

from floors import FLOORS

HERE = os.path.dirname(os.path.abspath(__file__))
DIR = os.path.join(HERE, 'patches')


def path_for(fid):
    return os.path.join(DIR, f"floor-{FLOORS[fid]['label'].lower()}.json")


def load_patches(fid):
    path = path_for(fid)
    if not os.path.exists(path):
        return {'lines': [], 'areas': {}}
    data = json.load(open(path))
    lines = []
    for ln in data.get('lines', []):
        if len(ln) < 4:
            raise SystemExit(f'{path}: a line needs x0, y0, x1, y1: {ln}')
        lines.append([float(v) for v in ln[:4]] + [str(ln[4]) if len(ln) > 4 else ''])
    # a vertex may carry a third value, the bulge of the edge starting there (an arc)
    areas = {str(k): [[float(c) for c in pt] for pt in v] for k, v in data.get('areas', {}).items()}
    return {'lines': lines, 'areas': areas}
