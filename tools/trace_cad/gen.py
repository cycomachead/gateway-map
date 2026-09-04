"""Run the whole trace: PDF -> geometry -> rooms -> TypeScript.

Usage: python3 gen.py <pdf dir> <workdir> [floor ids...]
The PDFs are `Gateway_Plan_View_10_2_2025-Floor_<pdf>.pdf` (see floors.py). Geometry JSON
is cached in <workdir>; delete a <pdf>_geom.json to re-extract it.
"""
import os
import sys

import rooms
from extract import extract
from floors import FLOORS

HERE = os.path.dirname(os.path.abspath(__file__))


def main(pdf_dir, workdir, only=()):
    for fid, cfg in FLOORS.items():
        if only and fid not in only:
            continue
        geom = os.path.join(workdir, f"{cfg['pdf']}_geom.json")
        if not os.path.exists(geom):
            extract(os.path.join(pdf_dir, f"Gateway_Plan_View_10_2_2025-Floor_{cfg['pdf']}.pdf"), geom)
        rooms.run(fid, geom, os.path.join(workdir, cfg['pdf']), cfg)


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2], sys.argv[3:])
