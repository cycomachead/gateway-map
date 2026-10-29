"""Vector tracer driver: sheet PDFs -> <pdf>_rooms.json for every floor (or one).

Usage: python3 gen2.py <pdf dir> <workdir> [floor id ...]

Runs extract.py (cached: an existing <pdf>_geom.json is reused), walls.py and faces.py,
then compare.py against the committed level files. emit_ts.py writes the modules:

    python3 gen2.py ../../floorplans/architect-pdfs/floorplans <workdir>
    python3 emit_ts.py <workdir> ../../src/data/gateway
"""
import os
import sys

from compare import report
from extract import extract
from faces import build as build_faces
from floors import FLOORS
from walls import build as build_walls


def main(pdf_dir, workdir, floors):
    os.makedirs(workdir, exist_ok=True)
    for fid in floors or FLOORS:
        cfg = FLOORS[fid]
        geom = os.path.join(workdir, f"{cfg['pdf']}_geom.json")
        if not os.path.exists(geom):
            extract(os.path.join(pdf_dir, cfg['source']), geom)
        build_walls(fid, workdir)
        build_faces(fid, workdir)
        report(workdir, fid)


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2], sys.argv[3:])
