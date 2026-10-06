"""Run the whole trace: PDF -> geometry -> rooms -> TypeScript.

Usage: python3 gen.py <pdf dir> <workdir> [floor ids...]
The PDFs use the source filenames in floors.py (floorplan_floor-*_2025-10-02.pdf). Geometry JSON
is cached in <workdir>; delete a <pdf>_geom.json to re-extract it.
"""
import os
import sys

import rooms
from extract import extract
from floors import FLOORS

HERE = os.path.dirname(os.path.abspath(__file__))


def main(pdf_dir, workdir, only=()):
    os.makedirs(workdir, exist_ok=True)
    for fid, cfg in FLOORS.items():
        if only and fid not in only:
            continue
        geom = os.path.join(workdir, f"{cfg['pdf']}_geom.json")
        if not os.path.exists(geom):
            extract(os.path.join(pdf_dir, cfg['source']), geom)
        rooms.run(fid, geom, os.path.join(workdir, cfg['pdf']), cfg)


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2], sys.argv[3:])
