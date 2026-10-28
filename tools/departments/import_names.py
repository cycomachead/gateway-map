"""Read who sits in each office off the colour space-assignment sheets.

Usage: python3 tools/departments/import_names.py [<pdf dir>] [<out.ts>]
       npm run names

The sheets carry a layer of annotations in Helvetica (the plan's own labels are Arial): a
person's name written across their office, sometimes with a role ("CS Division Chair"), a note
("+1", "Proposed new hire", "Search #3113") or several people separated by commas, slashes or
line breaks. This script maps every annotation line onto the map's rooms (the same
registration as import_departments.py), gathers the lines written over each office into
stacked blocks, and splits them into names: pieces of one to four capitalised words that
carry no role or note word and no room number. Roles, groups ("PhD/Postdoc", "Masters
Students STAT"), searches and desk numbers are dropped; anything dropped from an office, and
every annotation in a room that is not an office, is printed for review.

Writes src/data/gateway/sheet_occupants.ts: plan room number -> names, which building.ts
merges under the EECS directory's occupants (the directory wins where both name a person).
Requires pymupdf (and numpy/Pillow through import_departments).
"""
import os
import re
import sys

import pymupdf

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from import_departments import PDF_DIR, SHEET, sheet_mapper, ts_str  # noqa: E402
from levels import GATEWAY, LEVELS, flatten, read_origin, read_rooms  # noqa: E402

OUT = os.path.join(GATEWAY, 'sheet_occupants.ts')
ANNOTATION_FONT = 'Helvetica'
MAX_SIZE = 8.6   # the annotations are 5 to 8 pt; the legend and title are 36 pt and up
LINE_GAP = 1.8   # lines closer than this many font sizes, one under the other, are one block

# A piece is not a person's name when any of its words is one of these (roles, groups, notes).
NOT_A_NAME = {
    'dean', "dean's", 'director', 'dir', 'asst', 'assistant', 'associate', 'executive', 'exec',
    'chair', 'staff', 'student', 'students', 'phd', 'phd/postdoc', 'phd/post-doc', 'postdoc',
    'post-doc', 'faculty', 'emeritus', 'emeriti', 'visiting', 'search', 'pending', 'tbd', 'shared',
    'lecturer', 'lecturers', 'advisor', 'analyst', 'coord', 'coordinator', 'manager', 'specialist',
    'printer', 'printers', 'scanner', 'room', 'copy', 'storage', 'office', 'team', 'masters',
    'scholars', 'program', 'comms', 'communications', 'swing', 'hoteling', 'division', 'unit',
    'gsao', 'ccb', 'ccb/bcbi', 'bcbi', 'ccds', 'stat', 'stats', 'cph', 'cdss', 'eecs', 'aiis',
    'maiml', 'bidmap', 'd-lab', 'ap', 'bio', 'chief', 'technical', 'finance', 'hr', 'life', 'data',
    'discovery', 'future', 'higher', 'ed', 'control', 'security', 'planning', 'systems',
    'facilities', 'shipping', 'receiving', 'energy', 'climate', 'environment', 'senior', 'sr',
    'college', 'academic', 'acad', 'conference', 'initiatives', 'interdisciplinary',
    'development', 'cao', 'cp', 'fac', 'space', 'pi', 'available', 'spot', 'work', 'studies',
    'proposed', 'new', 'hire', 'two', 'one', 'and', 'fellow', 'fellows', 'research',
    'researcher', 'researchers', 'intern', 'interns', 'visitor', 'visitors', 'lab', 'group',
    'desk', 'hotel', 'reserved', 'vacant', 'empty', 'open', 'flex', 'huddle', 'admin', 'admin-',
    'berkeley', 'rdi', 'csa', 'managed', 'by', 'etc', 'cs',
}
SEPARATORS = re.compile(r'\s*(?:,|;|/|&|\+\s*\d*|\band\b)\s*')
NOTE = re.compile(r'\([^)]*\)|\[[^\]]*\]|#\S+')  # a note may wrap onto the next line
ROOM_NUMBER = re.compile(r'\b[A-Z]?\d{3,4}[A-Z]?\b|\b\d+-[A-Z]+\b')
# A name word: capitalised, possibly with an initial's dot, a hyphen, an apostrophe or quotes
# ("Javier"); "La", "de" and the like are fine inside a name.
NAME_WORD = re.compile(r'^(?:[A-Z][A-Za-z\'.-]*|"[A-Z][A-Za-z]*"|[a-z]{2,3})$')


def read_lines(path):
    """Every annotation line on a sheet: (down, along0, along1, size, centre, text), where
    down/along are the line's distance in the text's own directions (the sheet's text is
    rotated with the building, so reading order is not plain y then x)."""
    page = pymupdf.open(path)[0]
    out = []
    for block in page.get_text('dict')['blocks']:
        if block['type'] != 0:
            continue
        for line in block['lines']:
            spans = [s for s in line['spans'] if s['text'].strip()]
            if not spans:
                continue
            font, size = spans[0]['font'], max(s['size'] for s in spans)
            if not font.startswith(ANNOTATION_FONT) or size > MAX_SIZE:
                continue
            dx, dy = line['dir']
            x0, y0, x1, y1 = line['bbox']
            corners = [(x0, y0), (x1, y0), (x0, y1), (x1, y1)]
            along = [x * dx + y * dy for x, y in corners]
            down = [x * -dy + y * dx for x, y in corners]
            text = ' '.join(s['text'] for s in spans).strip()
            out.append(((min(down) + max(down)) / 2, min(along), max(along), size, ((x0 + x1) / 2, (y0 + y1) / 2), text))
    return out


def stack(lines):
    """Lines of one room gathered into blocks: a line joins the block above it when it sits
    just under it and overlaps it along the text direction; blocks and lines in reading order."""
    blocks = []
    for line in sorted(lines):
        down, a0, a1, size, _, _ = line
        for block in blocks:
            last = block[-1]
            if 0 <= down - last[0] <= LINE_GAP * max(size, last[3]) and a0 <= last[2] + 2 and a1 >= last[1] - 2:
                block.append(line)
                break
        else:
            blocks.append([line])
    blocks.sort(key=lambda b: (b[0][0], b[0][1]))
    return [[l[5] for l in b] for b in blocks]


def contains(poly, pt):
    x, y = pt
    inside = False
    n = len(poly)
    for i in range(n):
        (x0, y0), (x1, y1) = poly[i], poly[(i + 1) % n]
        if (y0 > y) != (y1 > y) and x < (x1 - x0) * (y - y0) / (y1 - y0) + x0:
            inside = not inside
    return inside


def is_role_word(w):
    return w.lower().strip('.,') in NOT_A_NAME


def is_name(words):
    if not 1 <= len(words) <= 4:
        return False
    if any(is_role_word(w) for w in words):
        return False
    if not any(w[0].isupper() or w[0] == '"' for w in words):
        return False
    return all(NAME_WORD.match(w) for w in words)


def without_role(line):
    """A line with a role beside a name ("Initiatives  Adrian Hill", "Admin- Adriana") keeps
    what follows or precedes the role words when they all come first or all come last; None
    when the line is nothing but roles or the roles sit among the other words."""
    words = line.split()
    flags = [is_role_word(w) for w in words]
    if not any(flags):
        return line
    if all(flags):
        return None
    first = flags.index(False)
    last = len(flags) - 1 - flags[::-1].index(False)
    if any(flags[first:last + 1]):
        return None
    if first == last and last < len(words) - 1:
        return None  # "CS" of "CS Division Chair" is part of the role, not a first name
    return ' '.join(words[first:last + 1])


def group_lines(lines):
    """Lines of one piece gathered into names: a name is two to four words, so a line joins
    the one before while that has fewer than two words, or is a single word joining a name
    that has fewer than three."""
    groups = []
    for line in lines:
        words = line.split()
        if not words:
            continue
        if groups and (len(groups[-1]) < 2 or (len(words) == 1 and len(groups[-1]) < 3)):
            groups[-1].extend(words)
        else:
            groups.append(words)
    return groups


def names_in(lines):
    """(names, dropped) parsed from the lines of one annotation block."""
    text = NOTE.sub(' ', '\n'.join(lines)).replace('’', "'")
    names, dropped = [], []
    for piece in SEPARATORS.split(text):
        piece_lines = [re.sub(r'\s+', ' ', l).strip(' ,;:') for l in piece.split('\n')]
        piece_lines = [l for l in piece_lines if l]
        if not piece_lines:
            continue
        if ROOM_NUMBER.search(' '.join(piece_lines)):
            dropped.append(' '.join(piece_lines))
            continue
        kept = []
        for l in piece_lines:
            name = without_role(l)
            if name is None:
                dropped.append(l)
            else:
                kept.append(name)
        lost_role = len(kept) < len(piece_lines)
        for words in group_lines(kept):
            # a lone surname next to a dropped role ("Neyman" / "Scholars") is part of the role
            if is_name(words) and not (lost_role and len(words) == 1):
                names.append(' '.join(words))
            else:
                dropped.append(' '.join(words))
    return names, dropped


def is_office(room):
    """Offices by category, plus the service rooms the plan calls an office (the facilities
    manager's); the open offices are desk clusters with desk numbers, not names."""
    name = room['extra'].get('name', '')
    return room['category'] == 'office' or (bool(re.search(r'\bOffice\b', name)) and not name.startswith('Open Office'))


def room_number(room):
    rid = room['id']
    return rid.upper() if re.fullmatch(r'[a-z]?\d{3,4}[a-z]?', rid, re.I) else None


def main(pdf_dir=PDF_DIR, out=OUT):
    origin = read_origin()
    occupants = {}   # room number -> [names]
    review = []
    stray = 0
    for level in LEVELS:
        name = 'lower-level' if level == '0' else level
        path = os.path.join(pdf_dir, SHEET.format(name))
        if not os.path.exists(path):
            raise SystemExit(f'missing {path}')
        to_sheet = sheet_mapper(level, origin)
        rooms = []
        for room in read_rooms(level):
            if room['category'] == 'circulation':
                continue
            rooms.append((room, [to_sheet(x, y) for x, y in flatten(room['polygon'])]))
        by_room = {}
        for line in read_lines(path):
            if re.fullmatch(r'[\d\s]+', line[5]):
                continue  # desk numbers in the open offices
            hit = next((room for room, poly in rooms if contains(poly, line[4])), None)
            if hit is None:
                stray += 1
                continue
            by_room.setdefault(hit['id'], (hit, []))[1].append(line)
        found = 0
        for hit, lines in by_room.values():
            label = hit['extra'].get('name', hit['id'])
            number = room_number(hit)
            blocks = stack(lines)
            if not is_office(hit) or not number:
                review.append(f'  level {level}: {label} (not an office): {" | ".join(" / ".join(b) for b in blocks)}')
                continue
            for block in blocks:
                names, dropped = names_in(block)
                if dropped:
                    review.append(f'  level {level}: {label}: dropped {", ".join(repr(d) for d in dropped)}'
                                  + (f'; kept {", ".join(names)}' if names else ''))
                for n in names:
                    if n not in occupants.setdefault(number, []):
                        occupants[number].append(n)
                        found += 1
        print(f'level {level}: {found} names in offices')
    if review:
        print('for review:')
        print('\n'.join(review))
    if stray:
        print(f'{stray} annotations outside every room (notes in corridors): ignored')
    lines = [
        '// GENERATED by tools/departments/import_names.py (`npm run names`) from the colour',
        '// space-assignment sheets — do not edit by hand; the next import overwrites the file.',
        '/**',
        ' * Who the space-assignment sheets write in each office: plan room number → names, as',
        " * annotated on the sheets (so spellings are the sheets'). building.ts merges these under",
        " * the EECS directory's occupants; a person named by both is listed once, as the directory",
        ' * spells it.',
        ' */',
        'export const SHEET_OCCUPANTS: Record<string, string[]> = {',
        *(f'  {ts_str(k)}: [{", ".join(ts_str(n) for n in v)}],' for k, v in sorted(occupants.items())),
        '};',
        '',
    ]
    open(out, 'w').write('\n'.join(lines))
    print(f'{out}: {sum(len(v) for v in occupants.values())} names in {len(occupants)} offices')


if __name__ == '__main__':
    main(*sys.argv[1:3])
