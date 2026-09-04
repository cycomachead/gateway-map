"""Pull the vector geometry and positioned text out of one CAD plan PDF.

Usage: python3 extract.py <pdf> <out.json>

Writes segments, bezier curves, rectangles (all in PDF points, y down) and the text lines
with their bounding boxes and font sizes. Everything downstream works from this JSON so the
(large) PDFs only have to be parsed once.
"""
import json
import sys

import pymupdf


def extract(src: str, out: str) -> None:
    doc = pymupdf.open(src)
    page = doc[0]
    segs, curves, rects, polylines = [], [], [], []
    for d in page.get_drawings():
        col = d.get('color')
        width = d.get('width') or 0
        black = 1 if (col is not None and col[0] < 0.1) else 0
        filled = 1 if d.get('fill') else 0
        items = d['items']
        rect = d['rect']
        # Furniture and fixtures are small multi-segment paths; wall pieces are single strokes
        # or long polylines. Used to build a furniture-free raster for the room polygons.
        furn = 1 if (len(items) >= 3 and max(rect.width, rect.height) <= 120) else 0
        # Small chained polylines (door swings are drawn as ~10 short segments on a circle).
        if black and 3 <= len(items) <= 64 and all(it[0] == 'l' for it in items):
            r = d['rect']
            if max(r.width, r.height) <= 80 and all(abs(items[i][2] - items[i + 1][1]) < 0.05 for i in range(len(items) - 1)):
                polylines.append([[items[0][1].x, items[0][1].y]] + [[it[2].x, it[2].y] for it in items])
        for it in items:
            if it[0] == 'l':
                a, b = it[1], it[2]
                segs.append([a.x, a.y, b.x, b.y, width, black, filled, furn])
            elif it[0] == 'c':
                curves.append([[q.x, q.y] for q in it[1:5]] + [width, black])
            elif it[0] == 're':
                r = it[1]
                rects.append([r.x0, r.y0, r.x1, r.y1, width, black, filled])
            elif it[0] == 'qu':
                q = it[1]
                pts = [q.ul, q.ur, q.lr, q.ll]
                for i in range(4):
                    a, b = pts[i], pts[(i + 1) % 4]
                    segs.append([a.x, a.y, b.x, b.y, width, black, filled, furn])
    lines = []
    for block in page.get_text('dict')['blocks']:
        if block['type'] != 0:
            continue
        for line in block['lines']:
            text = ' '.join(s['text'] for s in line['spans']).strip()
            if not text:
                continue
            lines.append({
                'text': text,
                'bbox': list(line['bbox']),
                'size': round(max(s['size'] for s in line['spans']), 2),
                'dir': list(line['dir']),
            })
    json.dump({'page': [page.rect.width, page.rect.height], 'segs': segs, 'curves': curves,
               'rects': rects, 'polylines': polylines, 'lines': lines}, open(out, 'w'))
    print(f'{src}: {len(segs)} segments, {len(curves)} curves, {len(rects)} rects, {len(polylines)} polylines, {len(lines)} text lines')


if __name__ == '__main__':
    extract(sys.argv[1], sys.argv[2])
