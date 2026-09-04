"""Per-floor configuration for the CAD trace: which PDF, how labels look, hand fixes.

`seeds`      label id -> (x, y) point inside the room, for labels the automatic seeding misses.
`extra`      extra wall strokes [x0, y0, x1, y1] to seal gaps in the drawing.
`skip`       label ids to ignore (duplicates, annotation text that looks like a room number).
`exterior`   extra points that are outside the building although the drawing encloses them.
`named`      (x, y, id, category, name, label, tags): rooms the plan does not number (stairs,
             elevators, restrooms, the atrium ...) identified by a point inside them; x may be
             a list of points whose regions are merged (y is then ignored).
`transform`  similarity (scale, degrees, dx, dy) mapping this sheet onto the shared frame of
             the upper floors (only the Lower Level sheet is drawn at another scale/rotation).
All coordinates are PDF points of that floor's sheet.
`manual`     (id, category, name, label, tags, polygon): rooms drawn by hand.
`exits`      detect exterior doors (door arcs on the outline) and emit them as entrance POIs.
"""

# Named regions shared by the upper floors (the cores are stacked, so the same points work).
_EL = lambda w, W, pts: [(x, y, f'{w}-elevator-{i + 1}', 'circulation', f'{W} Elevator {i + 1}', 'Elev.', ['elevator']) for i, (x, y) in enumerate(pts)]
NE_ELEVATORS = _EL('ne', 'Northeast', [(1431.3, 944.8), (1482.6, 934.0), (1533.9, 923.2)])
SW_ELEVATORS = _EL('sw', 'Southwest', [(1497.6, 1533.5), (1545.6, 1515.0), (1597.9, 1508.6)])
# A stair's treads split it into a cluster per flight, so several points are given and
# their regions are merged (any entry's x/y may be a list of points).
NE_STAIR = ([(1345, 950), (1385, 1010), (1390, 965)], None, 'ne-stair', 'circulation', 'Northeast Stair', 'Stair', ['stairs'])
SW_STAIR = ([(575, 1490), (600, 1480), (610, 1520)], None, 'sw-stair', 'circulation', 'Southwest Stair', 'Stair', ['stairs'])
EAST_STAIR = (2600, 1560, 'east-stair', 'circulation', 'East Stair', 'Stair', ['stairs'])
ATRIUM = (1480, 1230, 'atrium', 'circulation', 'Atrium', 'Atrium', ['atrium', 'stairs', 'open to below'])
NE_RESTROOMS = [(1375, 850, 'ne-restroom', 'service', 'Restroom (NE)', 'WC', ['restroom']),
                ([(1250, 880), (1240, 870), (1262, 892)], None, 'ne-restroom-2', 'service', 'Single-Occupancy Restroom (NE)', 'WC', ['restroom', 'all gender'])]
SW_RESTROOMS = [(1600, 1610, 'sw-restroom', 'service', 'Restroom (SW)', 'WC', ['restroom']),
                (1670, 1515, 'sw-restroom-2', 'service', 'Single-Occupancy Restroom (SW)', 'WC', ['restroom', 'all gender'])]
CORES = NE_ELEVATORS + SW_ELEVATORS + [NE_STAIR, SW_STAIR, EAST_STAIR, ATRIUM]
LL_CORES = (_EL('ne', 'Northeast', [(2406.6, 856.1), (2488.8, 848.9), (2570.9, 841.7)])
            + _EL('sw', 'Southwest', [(2398.4, 1787.8), (2476.8, 1768.0), (2559.7, 1768.0)])
            + [(2295, 875, 'ne-stair', 'circulation', 'Northeast Stair', 'Stair', ['stairs']),
               (2690, 1935, 'sw-restrooms', 'service', 'Restrooms (SW)', 'WC', ['restroom'])])
# The teaching rooms and the atrium landing on the Lower Level open onto the hall without
# doors, so they cannot be traced as enclosed regions and stay unnamed.

FLOORS = {
    # The Lower Level sheet is at 1/8" = 1' and rotated; the transform was fitted on the six
    # elevator shafts (X-marked squares) shared with the upper floors (residual < 0.1 pt).
    '0': dict(pdf='Lower_Level', label='LL', level=0, label_sizes=(7.0, 8.0), number_re=r'^B\d{4}[A-Z]?$',
              transform=(0.63577, -6.9324, -153.26, 589.22), named=LL_CORES, exits=True, min_room=1800),
    # The covered plaza between the Southwest block and the main building is outside.
    '1': dict(pdf='1', label='1', level=1, exterior=[(960, 1600)], named=CORES + SW_RESTROOMS, exits=True,
              # The tiered lecture hall carries no number on this plan (its rows split it into
              # stripes); traced by hand, number from the wayfinding signs.
              manual=[('1210', 'classroom', 'Lecture Hall 1210', '1210', ['lecture hall', 'auditorium'],
                       [(2105, 905), (2440, 862), (2955, 1392), (2455, 1478), (2205, 1290), (2100, 1000)])]),
    '2': dict(pdf='2', label='2', level=2, named=CORES + NE_RESTROOMS + SW_RESTROOMS),
    '3': dict(pdf='3', label='3', level=3, named=CORES + NE_RESTROOMS + SW_RESTROOMS),
    '4': dict(pdf='4', label='4', level=4, named=CORES + NE_RESTROOMS + SW_RESTROOMS),
    # Floor 5 is set back: the paved roof terraces inside the parapet line are outside.
    '5': dict(pdf='5', label='5', level=5, named=[n for n in CORES if n is not EAST_STAIR], exterior=[(1800, 1300), (1800, 600), (800, 1900)]),
}

for f in FLOORS.values():
    f.setdefault('label_sizes', (3.5, 5.0))
    f.setdefault('number_re', r'^(\d{4}[A-Z]?|\dCORR\d{2})$')
    f.setdefault('seeds', {})
    f.setdefault('extra', [])
    f.setdefault('skip', set())
    f.setdefault('exterior', [])
    f.setdefault('named', [])
    f.setdefault('pois', [])
    f.setdefault('transform', None)
    f.setdefault('manual', [])
    f.setdefault('exits', False)


# ---------------------------------------------------------------------------
# Categories and display names from the plan's room names
# ---------------------------------------------------------------------------
def category(name: str, id_: str) -> str:
    words = set(name.upper().replace('/', ' ').replace('-', ' ').split())
    has = lambda *ws: any(w in words for w in ws)
    if has('CIRCULATION', 'CORRIDOR') or 'CORR' in id_.upper():
        return 'circulation'
    if has('PIAZZA', 'COLLAB', 'PORCH', 'FLEXIBLE') or (has('OPEN') and has('OFFICE')):
        return 'open'
    if has('LAB', 'MRI'):
        return 'lab'
    if has('LECTURE', 'CLASSROOM', 'AUDITORIUM'):
        return 'classroom'
    if has('FOCUS', 'BOOTH', 'PHONE'):
        return 'focus'
    if has('HUDDLE', 'MEETING', 'PROJECT', 'CONFERENCE'):
        return 'meeting'
    if has('KITCHEN', 'LOUNGE', 'LACTATION', 'MEDITATION', 'CAFE') or (has('GREEN') and has('ROOM')):
        return 'amenity'
    if has('HELP', 'STORAGE', 'SHIPPING', 'DAS', 'RECEPTION', 'MECH', 'ELEC', 'FACILITY'):
        return 'service'
    if has('STUDY', 'STUDENT', 'HOURS'):
        return 'study'
    return 'office'


TITLE_FIXES = {
    'Social Kitchen/Working Lounge': 'Social Kitchen / Working Lounge',
    'Piazza Informal Collab': 'Piazza – Informal Collab',
    'Project Rm.': 'Project Room',
    'Phone Rm.': 'Phone Room',
    'Group Study Large': 'Large Group Study',
    'General Lab Research': 'General Research Lab',
}
ADD_ROOM = {'Focus', 'Huddle', 'Small Meeting', 'Medium Meeting', 'Large Meeting', 'Extra Large Meeting', 'Meeting', 'Lactation', 'Meditation', 'Green'}


ACRONYMS = {'It': 'IT', 'Hci': 'HCI', 'Das': 'DAS', 'Mri': 'MRI'}


def display_name(name: str, id_: str) -> str:
    """'FACULTY OFFICE' + '3117' -> 'Faculty Office 3117'; 'HUDDLE' -> 'Huddle Room 3189'."""
    import re
    t = re.sub(r'[A-Za-z]+', lambda m: ACRONYMS.get(m.group().capitalize(), m.group().capitalize()), name)
    t = TITLE_FIXES.get(t, t)
    if t in ADD_ROOM:
        t += ' Room'
    if not t:
        t = 'Room'
    return f'{t} {id_}'


def wing(id_: str):
    """Gateway numbers rooms x1xx/x2xx in the Northeast wing and x3xx/x4xx in the Southwest."""
    digits = ''.join(c for c in id_ if c.isdigit())
    if len(digits) < 4 or id_.startswith('B'):
        return None
    hundreds = digits[1]
    return 'Northeast' if hundreds in '12' else 'Southwest' if hundreds in '34' else None
