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
`hand`       label id -> polygon: rooms drawn by hand, replacing the traced shape.
`box`        label ids drawn as their bounding rectangle: labs whose internal lines (benches,
             raised floors) are not walls and would otherwise notch or split the room.
`quad`       label ids forced to their best four-corner fit (walls line-fitted, jogs and
             folding partitions ignored) even where that covers the traced region loosely.
`smooth`     open-area label ids drawn as sweeping shapes standing clear of the rooms (the
             piazzas and porches get this by name).
`sign`       (photo in floorplans/, (x, y) fraction of the map where the atrium oval is): the
             wayfinding sign whose simplified map gives the piazzas their shape.
`atrium`     (cx, cy, a, b, degrees): the ellipse of the atrium's rail, for floors where stairs
             wind down inside it (so the opening never closes as one region).
`unnamed`    minimum area (px): unlabelled enclosed regions at least this big are emitted as
             unnamed rooms (for plans that number only the furnished rooms).
`terrace`    seed points on a roof terrace's pavers or walkways: the deck becomes one open area.
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
               (2690, 1935, 'sw-restrooms', 'service', 'Restrooms (SW)', 'WC', ['restroom'])]
            # the tiered teaching rooms along the curved band and the flat one in the middle
            # carry no number on this plan
            + [(x, y, f'classroom-{i}', 'classroom', f'Classroom {i} (Lower Level)', 'Classroom', ['classroom', 'teaching'])
               for i, (x, y) in enumerate([(1073.7, 954.1), (1352.1, 1119.3), (1729.6, 1110.9), (2030.1, 987.0), (1539.4, 1594.2)], 1)])
# The teaching rooms and the atrium landing on the Lower Level open onto the hall without
# doors, so they cannot be traced as enclosed regions and stay unnamed.

FLOORS = {
    # The Lower Level sheet is at 1/8" = 1' and rotated; the transform was fitted on the six
    # elevator shafts (X-marked squares) shared with the upper floors (residual < 0.1 pt).
    '0': dict(pdf='Lower_Level', label='LL', level=0, label_sizes=(7.0, 8.0), number_re=r'^B\d{4}[A-Z]?$',
              transform=(0.63577, -6.9324, -153.26, 589.22), named=LL_CORES, exits=True, min_room=1800,
              # the teaching rooms and service rooms carry no number on this plan (the sheet is
              # drawn larger, so the size limits are too); B1335's label sits in its doorway
              unnamed=4000, unnamed_max=90000,
              # The labels sit at the rooms' doors: the rooms are drawn by hand from the walls.
              hand={'B1335': [(1456, 2002), (1596, 2002), (1596, 2214), (1456, 2214)],
                    'B1342': [(1362, 1769), (1548, 1769), (1548, 1925), (1362, 1925)],
                    'B1346': [(1262, 1769), (1356, 1769), (1356, 1925), (1262, 1925)],
                    'B1336': [(1556, 1769), (1737, 1769), (1737, 1926), (1556, 1926)],
                    'B1040C': [(433, 716), (543, 697), (561, 808), (451, 827)],
                    'B1040D': [(549, 696), (632, 683), (650, 794), (567, 807)],
                    'B1040E': [(638, 682), (718, 668), (736, 779), (656, 793)],
                    'B1040F': [(724, 667), (810, 653), (828, 763), (742, 778)],
                    'B1040G': [(816, 652), (894, 639), (912, 749), (834, 762)],
                    'B1040': [(400, 836), (912, 752), (934, 878), (916, 901), (957, 1016), (856, 1090), (800, 1050), (794, 1132), (457, 1139)]},
              quad={'B1040H'}),
    # The covered plaza between the Southwest block and the main building is outside.
    '1': dict(pdf='1', label='1', level=1, exterior=[(960, 1600)], exits=True, unnamed=2500, atrium=(1499, 1219, 128, 185, 80.5),
              # 1420's label sits on its tables: it is named below
              skip={'1420'},
              # The two lecture halls carry no number on this plan (their tiers split them into
              # stripes) and the drone lab's label sits at its door: traced by hand, the hall
              # numbers from the wayfinding sign.
              hand={'1210': ('LECTURE HALL', [(2105, 945), (2172, 895), (2250, 880), (2244, 853), (2340, 830), (2405, 818), (2527, 987), (2533, 1013),
                                              (2473, 1247), (2445, 1295), (2413, 1313), (2300, 1213), (2187, 1080), (2125, 1015)]),
                    '1220': ('LECTURE HALL', [(2541, 1050), (2614, 1052), (2873, 1332), (2891, 1370), (2550, 1468), (2418, 1309), (2455, 1264)]),
                    '1110': [(1195, 882), (1241, 874), (1274, 1050), (1143, 1078)],
                    '1120': [(1240, 712), (1324, 700), (1401, 818), (1206, 862)],
                    '1230': [(2560, 1470), (2885, 1380), (2945, 1450), (2960, 1545), (2664, 1615), (2600, 1530)]},
              # the Southwest wing's stair of the upper floors is the Southwest block's stair here
              named=[n for n in CORES if n is not SW_STAIR] + SW_RESTROOMS + [
                  (575, 1478, 'sw-stair', 'circulation', 'Southwest Stair', 'Stair', ['stairs']),
                  (1261.6, 1700.3, 'cafe', 'amenity', 'Cafe', 'Cafe', ['cafe', 'food']),
                  (1608.3, 1732.7, 'cafe-seating', 'amenity', 'Cafe Seating', 'Seating', ['cafe', 'seating']),
                  ([(420, 1760), (571.7, 1780.2)], None, '1420', 'amenity', 'Social Kitchen / Working Lounge 1420', '1420', ['social', 'kitchen', 'working', 'lounge']),
                  ([(559.3, 995.8), (612.9, 991.7), (551.2, 916.2)], None, 'sw-block-stair', 'circulation', 'Southwest Block Stair', 'Stair', ['stairs']),
                  ([(500, 1320), (487, 1369), (444, 1369), (531, 1412), (534, 1437)], None, 'sw-block-restrooms', 'service', 'Restrooms (Southwest Block)', 'WC', ['restroom']),
              ]),
    # Floors 2 and 3 follow floor 4 (below): the research labs are boxes, the kitchens and
    # meeting rooms with a pilaster or a curved wall are four-cornered. Stairs wind down inside
    # the atrium's rail on these floors, so the rail's ellipse is given.
    '2': dict(pdf='2', label='2', level=2, named=CORES + NE_RESTROOMS + SW_RESTROOMS, sign=('level2-whole-floor.jpg', (0.44, 0.52)),
              box={'2184', '2192', '2322', '2404', '2408'},
              quad={'2130', '2133', '2219', '2228', '2345', '2355', '2361', '2389', '2431', '2445'},
              hand={'2310': [(1655, 1652), (1770, 1648), (1816, 1822), (1666, 1827)],
                    '2161': [(2128, 469), (2203, 452), (2255, 514), (2168, 594), (2132, 545)]},
              atrium=(1460, 1260, 252, 152, -14)),
    '3': dict(pdf='3', label='3', level=3, named=CORES + NE_RESTROOMS + SW_RESTROOMS, sign=('level3-whole-floor.jpg', (0.44, 0.52)),
              box={'3131', '3184', '3192', '3322', '3406'},
              quad={'3130', '3161', '3219', '3350', '3355', '3375', '3431', '3447'},
              # the labs 3184/3192 are split by benches drawn as walls; 3310 opens onto 3340
              hand={'3184': [(2424, 1100), (2560, 1240), (2474, 1320), (2340, 1175)],
                    '3192': [(2428, 1098), (2525, 1047), (2620, 1152), (2563, 1236)],
                    '3310': [(1723, 1650), (1770, 1650), (1818, 1824), (1723, 1826)]},
              atrium=(1459.3, 1241.6, 186.6, 291.5, 73.1)),
    # The labs 4131/4184/4192/4408/4322 are plain boxes on the plan (their internal lines are
    # benches); the social kitchens 4130 and 4350 are boxes with one curved wall, and the
    # meeting rooms 4355/4375 and the study room 4310 are rectangles with a pilaster, a
    # cabinet or a closet in a corner.
    # Floors 2-4 share the plan around the atrium, and there is no level 4 sign photo.
    '4': dict(pdf='4', label='4', level=4, named=CORES + NE_RESTROOMS + SW_RESTROOMS,
              box={'4131', '4184', '4192', '4408', '4322'}, quad={'4130', '4350', '4355', '4375', '4310'},
              sign=('level3-whole-floor.jpg', (0.44, 0.52))),
    # Floor 5 is set back: the indoor blocks stand on a paved roof terrace inside the parapet
    # (seeded on its pavers and walkways). The passage between the restroom blocks of the south
    # bar is sealed so the terrace does not run into the building. The oval is the atrium's
    # skylight.
    '5': dict(pdf='5', label='5', level=5, unnamed=2500, unnamed_max=120000,
              named=[n for n in CORES if n not in (EAST_STAIR, ATRIUM)] + [
                  (1458, 1236, 'skylight', 'circulation', 'Atrium Skylight', 'Skylight', ['atrium', 'skylight'])],
              terrace=[(1800, 1300), (800, 1900), (1100, 1350), (1210, 1290), (800, 1250), (1300, 1475), (1200, 960), (1400, 1420), (1700, 1000)],
              extra=[[1310, 1522, 1342, 1515]],
              # 5370's label sits in the corridor below it, and 5310's fill leaks along the
              # curtain wall: both drawn by hand
              hand={'5370': [(160, 1000), (428, 935), (478, 1100), (218, 1163)],
                    '5310': [(1113, 1587), (1243, 1575), (1255, 1783), (1118, 1795)]},
              atrium=(1458, 1236, 126, 226, 71.7)),
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
    f.setdefault('box', set())
    f.setdefault('quad', set())
    f.setdefault('smooth', set())
    f.setdefault('sign', None)
    f.setdefault('atrium', None)
    f.setdefault('hand', {})
    f.setdefault('unnamed', 0)
    f.setdefault('unnamed_max', 40000)
    f.setdefault('terrace', [])


# ---------------------------------------------------------------------------
# Categories and display names from the plan's room names
# ---------------------------------------------------------------------------
def category(name: str, id_: str) -> str:
    words = set(name.upper().replace('/', ' ').replace('-', ' ').split())
    has = lambda *ws: any(w in words for w in ws)
    if has('CIRCULATION', 'CORRIDOR') or 'CORR' in id_.upper():
        return 'circulation'
    if has('PIAZZA', 'COLLAB', 'PORCH', 'FLEXIBLE', 'TERRACE') or (has('OPEN') and has('OFFICE')):
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
