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
`atrium`     (cx, cy, a, b, degrees): the ellipse of the atrium's rail, for floors where stairs
             wind down inside it (so the opening never closes as one region).
`unnamed`    minimum area (px): unlabelled enclosed regions at least this big are emitted as
             unnamed rooms (for plans that number only the furnished rooms).
`terrace`    seed points on a roof terrace's pavers or walkways: the deck becomes one open area.
`exits`      detect exterior doors (door arcs on the outline) and emit them as entrance POIs.
`blank`      points inside unlabelled regions that are left off the map (closets between rooms).
`rename`     label id -> room name used instead of the plan's (for rooms whose use has changed
             since the furniture plan was drawn); the number stays the label.
"""
import math


def _ellipse(cx, cy, a, b, deg, n=72):
    """Polygon of an ellipse: centre, semi-axes and the rotation of the `a` axis in degrees."""
    r = math.radians(deg)
    return [(cx + a * math.cos(t) * math.cos(r) - b * math.sin(t) * math.sin(r),
             cy + a * math.cos(t) * math.sin(r) + b * math.sin(t) * math.cos(r))
            for t in (2 * math.pi * i / n for i in range(n))]


def _on_ellipse(e, ox, oy, deg):
    """Where the ray from (ox, oy) at `deg` degrees leaves the ellipse e = (cx, cy, a, b, rotation)."""
    cx, cy, a, b, rot = e
    r, t = math.radians(rot), math.radians(deg)
    c, s = math.cos(r), math.sin(r)
    px, py = (ox - cx) * c + (oy - cy) * s, -(ox - cx) * s + (oy - cy) * c
    ux, uy = math.cos(t) * c + math.sin(t) * s, -math.cos(t) * s + math.sin(t) * c
    A = ux * ux / a / a + uy * uy / b / b
    B = 2 * (px * ux / a / a + py * uy / b / b)
    C = px * px / a / a + py * py / b / b - 1
    k = (-B + math.sqrt(B * B - 4 * A * C)) / (2 * A)
    return (ox + k * math.cos(t), oy + k * math.sin(t))


def _band(inner, outer, deg0, deg1, n=40):
    """The curved band between two ellipses, from `deg0` to `deg1` as seen from the inner centre."""
    degs = [deg0 + (deg1 - deg0) * i / n for i in range(n + 1)]
    ox, oy = inner[:2]
    return [_on_ellipse(outer, ox, oy, d) for d in degs] + [_on_ellipse(inner, ox, oy, d) for d in reversed(degs)]


# Named regions shared by the upper floors (the cores are stacked, so the same points work).
_EL = lambda w, W, pts: [(x, y, f'{w}-elevator-{i + 1}', 'circulation', f'{W} Elevator {i + 1}', 'Elev.', ['elevator']) for i, (x, y) in enumerate(pts)]
NE_ELEVATORS = _EL('ne', 'Northeast', [(1431.3, 944.8), (1482.6, 934.0), (1533.9, 923.2)])
SW_ELEVATORS = _EL('sw', 'Southwest', [(1497.6, 1533.5), (1545.6, 1515.0), (1597.9, 1508.6)])
# A stair's treads split it into a cluster per flight, so several points are given and
# their regions are merged (any entry's x/y may be a list of points).
NE_STAIR = ([(1345, 950), (1390, 965)], None, 'ne-stair', 'circulation', 'Northeast Stair', 'Stair', ['stairs'])
SW_STAIR = ([(575, 1490), (600, 1480), (610, 1520)], None, 'sw-stair', 'circulation', 'Southwest Stair', 'Stair', ['stairs'])
# The East Stair runs down along the inner facade of the Northeast wing's tail. Its traced
# region spills into the corridor along the facade, so it is drawn by hand (a `manual` entry):
# the four corners of its flight and the opening beside it, stacked on Floors 1-4.
EAST_STAIR = ('east-stair', 'circulation', 'East Stair', 'Stair', ['stairs'],
              [(2493.7, 1516.0), (2532.2, 1481.8), (2642.0, 1602.4), (2579.0, 1633.0)])
ATRIUM = (1480, 1230, 'atrium', 'circulation', 'Atrium', 'Atrium', ['atrium', 'stairs', 'open to below'])
# Restrooms: the plans do not label them (except on the Lower Level). The multi-stall rooms of
# the Northeast core are the men's and those of the Southwest core the women's; the small
# single-occupancy rooms beside them are gender neutral. The map draws a pictogram above the
# label from the tags ('men', 'women', 'all gender'; see emit_ts.ICONS), and a label's lines
# after the first are wrapped small under it so it fits a small room.
MENS = ("Men's Restroom", "Men's Restroom", ['restroom', 'men'])
WOMENS = ("Women's Restroom", "Women's Restroom", ['restroom', 'women'])
NEUTRAL = ('Gender Neutral Restroom', 'Gender\nNeutral', ['restroom', 'all gender', 'gender neutral'])
NE_RESTROOMS = [(1375, 850, 'ne-restroom', 'service', *MENS),
                ([(1250, 880), (1240, 870), (1262, 892), (1278, 870)], None, 'ne-restroom-2', 'service', *NEUTRAL)]
SW_RESTROOMS = [(1600, 1610, 'sw-restroom', 'service', *WOMENS),
                (1670, 1515, 'sw-restroom-2', 'service', *NEUTRAL)]
# The Southwest core is the same on floors 2–4, but its restrooms trace differently on each
# (the stall row of the women's room is a region of its own, the vestibule beside it joins
# the room on floor 3, the single-user room takes the closet above it on floor 4), so both
# are drawn once from the walls (a 162 × 100 pt rectangle with its stalls, and the 38 × 52
# single-user room above it, in the wing's 7° frame) and used on all three floors.
SW_CORE_RESTROOMS = [
    ('sw-restroom', 'service', *WOMENS, [[1532.0, 1558.0], [1544.3, 1656.7], [1705.1, 1636.7], [1692.8, 1538.0]]),
    ('sw-restroom-2', 'service', *NEUTRAL, [[1649.0, 1492.0], [1655.4, 1543.6], [1693.1, 1538.9], [1686.7, 1487.3]]),
]
CORES = NE_ELEVATORS + SW_ELEVATORS + [NE_STAIR, SW_STAIR, ATRIUM]
# the copy room beside the consultation rooms X403/X405 carries no number on the plans
COPY_ROOM = lambda n: (658, 1376, f'{n}401', 'copy', f'Copy Room {n}401', f'{n}401', ['copy', 'printer'])
LL_CORES = (_EL('ne', 'Northeast', [(2406.6, 856.1), (2488.8, 848.9), (2570.9, 841.7)])
            + _EL('sw', 'Southwest', [(2398.4, 1787.8), (2476.8, 1768.0), (2559.7, 1768.0)])
            + [(2295, 875, 'ne-stair', 'circulation', 'Northeast Stair', 'Stair', ['stairs']),
               # the gender inclusive restroom B1309 (its label sits in the upper half, the
               # lower row of stalls traces as a separate region) and the single-user B1307
               ([(2749, 1720), (2690, 1935)], None, 'B1309', 'service', 'Gender Inclusive Restroom B1309', 'Gender\nInclusive', ['restroom', 'all gender', 'gender inclusive']),
               (2846, 1653, 'B1307', 'service', 'Single-User Restroom B1307', 'Single\nUser', ['restroom', 'all gender', 'single user']),
               ])
# Floor 5's restrooms stand in the south bar: two multi-stall rooms (the western one has the
# urinals) and, by the elevators, two single-occupancy rooms drawn by hand from their walls.
F5_RESTROOMS = [(1305, 1700, 'men-restroom', 'service', "Men's Restroom", "Men's\nRestroom", ['restroom', 'men']),
                (1390, 1690, 'women-restroom', 'service', "Women's Restroom", "Women's\nRestroom", ['restroom', 'women'])]
# The Southwest block's restrooms on floor 1 are one hatched region (the floor pattern crosses
# their walls), so the three rooms are drawn by hand in a frame along the block (7° off the
# sheet): the women's upper band with its stalls, the single-user room in the middle and the
# men's below. Which multi-stall room is the men's is not legible on the plan.
# The second Northeast stair stands east of the elevators, south of the men's restroom (floor 1)
# and of 2133 (floor 2), in the wing's 12° frame; its treads trace as slivers, so it is drawn by
# hand from its walls on both floors (floor 1's flight starts further west, with its landing)
NE_STAIR_EAST = lambda poly: ('ne-stair-east', 'circulation', 'Northeast Stair', 'Stair', ['stairs'], poly)
NE_STAIR_EAST_F1 = NE_STAIR_EAST([[1574.1, 912.4], [1734.5, 878.3], [1749.4, 948.7], [1589.0, 982.8]])
NE_STAIR_EAST_F2 = NE_STAIR_EAST([[1613.2, 904.1], [1731.6, 878.9], [1746.5, 949.3], [1628.1, 974.5]])
SW_BLOCK_RESTROOMS = [
    ('sw-block-womens', 'service', *WOMENS, [[410.4, 1312.8], [576.2, 1292.5], [584.7, 1361.9], [504.3, 1371.8], [500.4, 1340.0], [415.0, 1350.5]]),
    ('sw-block-neutral', 'service', *NEUTRAL, [[450.5, 1352.2], [498.1, 1346.4], [504.2, 1396.0], [456.6, 1401.8]]),
    ('sw-block-mens', 'service', *MENS, [[422.1, 1408.1], [507.5, 1397.6], [505.9, 1384.7], [586.3, 1374.8], [593.2, 1431.4], [427.5, 1451.8]]),
]
F5_SINGLE_RESTROOMS = [('single-restroom-1', 'service', *NEUTRAL, [(1264.0, 1530.0), (1310.0, 1524.5), (1317.0, 1586.0), (1271.5, 1591.5)]),
                       ('single-restroom-2', 'service', *NEUTRAL, [(1358.0, 1518.6), (1404.0, 1513.0), (1411.2, 1572.8), (1364.5, 1572.1)])]

# Lower-level teaching room numbers: Teaching Spaces PDF, pages 4 and 10.
# Wall geometry: October 2025 CAD sheet; door swings and furniture are omitted. The storage
# closets wedged between neighbouring classrooms are left out: each pair of classrooms meets
# where their exterior walls cross.
LL_TEACHING = {
    'B1026': ('CLASSROOM', [
        (1163.9, 811.9), (928.0, 904.1), (932.0, 919.2), (936.5, 934.2), (941.5, 949.0),
        (947.0, 963.6), (953.0, 978.0), (959.6, 992.2), (966.6, 1006.2), (974.1, 1019.9),
        (982.1, 1033.3), (990.6, 1046.5), (999.5, 1059.3), (1008.9, 1071.8), (1018.7, 1084.0),
        (1028.9, 1095.8), (1039.5, 1107.3), (1050.5, 1118.4), (1062.0, 1129.1), (1249.0, 934.5),
    ]),
    'B1022': ('CLASSROOM', [
        (1062.0, 1129.1), (1081.5, 1144.3), (1101.7, 1158.7), (1122.3, 1172.4), (1143.6, 1185.2),
        (1165.3, 1197.2), (1187.4, 1208.3), (1210.0, 1218.6), (1232.9, 1228.0), (1265.0, 1238.6),
        (1297.5, 1248.0), (1330.3, 1256.2), (1363.4, 1263.0), (1396.8, 1268.6), (1430.3, 1272.8),
        (1464.0, 1275.7), (1539.0, 1278.0), (1534.6, 988.0), (1249.0, 934.5),
    ]),
    'B1016': ('CLASSROOM', [
        (1548.3, 988.7), (1544.1, 1278.0), (1564.6, 1278.5), (1585.2, 1278.4), (1605.7, 1277.5),
        (1626.2, 1275.8), (1646.7, 1273.4), (1667.0, 1270.3), (1701.1, 1265.3), (1735.0, 1259.0),
        (1768.6, 1251.6), (1802.0, 1243.0), (1835.8, 1233.0), (1869.2, 1221.8), (1902.1, 1209.4),
        (1934.6, 1195.8), (1966.6, 1181.0), (1998.0, 1165.1), (1858.4, 915.4),
    ]),
    'B1012': ('CLASSROOM', [
        (2004.3, 812.8), (1858.4, 915.4), (1998.0, 1165.1), (2033.5, 1144.4), (2068.1, 1122.4),
        (2101.8, 1099.0), (2134.6, 1074.3), (2166.4, 1048.3), (2197.1, 1021.0),
    ]),
    'B1019': ('ACTIVE LEARNING CLASSROOM', [
        (1269.6, 1455.7), (1280.5, 1453.2), (1327.4, 1444.4), (1374.6, 1437.3), (1422.0, 1432.0),
        (1469.6, 1428.3), (1517.3, 1426.4), (1565.0, 1426.2), (1612.7, 1427.8), (1660.3, 1431.1),
        (1707.8, 1436.0), (1755.0, 1442.8), (1797.9, 1451.0), (1797.9, 1730.0), (1812.0, 1730.0),
        (1811.7, 1765.6), (1269.6, 1765.6),
    ]),
    'B1023': ('CLASSROOM', [
        (1026.0, 1922.2), (1025.7, 1631.0), (1256.5, 1631.0), (1256.6, 1922.0),
    ]),
    'B1015': ('CLASSROOM', [
        (1825.6, 1458.9), (1858.6, 1466.8), (1891.2, 1475.8), (1923.5, 1485.9), (1955.4, 1497.2),
        (1986.9, 1509.6), (2018.0, 1523.1), (2019.0, 1756.7), (1829.7, 1756.7),
    ]),
    'B1013': ('GROUP STUDY', [
        (2027.1, 1529.1), (2068.2, 1548.1), (2108.6, 1568.7), (2148.2, 1590.7), (2187.0, 1614.1),
        (2225.0, 1638.9), (2262.0, 1665.1), (2261.9, 1755.4), (2027.0, 1755.2),
    ]),
    'B1008': ('CLASSROOM', [
        (2616.3, 1024.8), (2619.9, 1046.0), (2633.0, 1057.0), (2635.4, 1057.1), (2637.7, 1057.2),
        (2640.1, 1057.4), (2642.4, 1057.6), (2644.7, 1058.0), (2647.0, 1058.4), (2649.3, 1059.0),
        (2651.6, 1059.6), (2653.9, 1060.2), (2656.1, 1061.0), (2658.3, 1061.8), (2660.5, 1062.8),
        (2662.6, 1063.7), (2664.7, 1064.8), (2666.7, 1066.0), (2668.8, 1067.2), (2670.7, 1068.5),
        (2672.7, 1069.8), (2674.5, 1071.2), (2676.4, 1072.7), (2678.1, 1074.3), (2679.8, 1075.9),
        (2681.5, 1077.6), (2683.1, 1079.3), (2684.6, 1081.1), (2686.1, 1082.9), (2687.5, 1084.8),
        (2688.8, 1086.7), (2690.1, 1088.7), (2691.3, 1090.7), (2692.4, 1092.8), (2693.5, 1094.9),
        (2694.5, 1097.1), (2695.3, 1099.2), (2696.2, 1101.4), (2696.9, 1103.7), (2697.6, 1105.9),
        (2704.5, 1118.1), (2711.0, 1130.5), (2717.0, 1143.2), (2722.6, 1156.0), (2727.8, 1169.0),
        (2732.8, 1184.3), (2737.2, 1199.7), (2741.1, 1215.3), (2744.3, 1231.1), (2747.0, 1246.9),
        (2782.0, 1270.1), (2888.8, 1260.9), (2866.9, 1007.5),
    ]),
    'B1009': ('CLASSROOM', [
        (2856.1, 1337.1), (2748.1, 1337.1), (2746.2, 1347.2), (2744.0, 1357.3), (2741.5, 1367.2),
        (2738.6, 1377.1), (2735.3, 1386.9), (2731.7, 1396.6), (2727.8, 1406.1), (2723.5, 1415.5),
        (2719.0, 1424.7), (2714.0, 1433.7), (2708.8, 1442.6), (2703.3, 1451.3), (2697.5, 1459.8),
        (2691.3, 1468.1), (2684.9, 1476.1), (2678.2, 1484.0), (2671.3, 1491.6), (2664.0, 1498.9),
        (2656.6, 1506.0), (2648.8, 1512.8), (2640.9, 1519.3), (2632.7, 1525.6), (2624.3, 1531.6),
        (2615.7, 1537.2), (2606.9, 1542.6), (2597.9, 1547.6), (2588.8, 1552.4), (2577.5, 1595.4),
        (2891.8, 1589.2), (2890.9, 1362.1),
    ]),
}

# The two rounded open-study areas (Teaching Spaces PDF, page 3): ellipses fitted to the
# curved walls and stair around them on the CAD sheet, as (cx, cy, a, b, rotation).
# B1030 sits in the curve on the west side; B1010 inside the main stair, which curves around
# its north and east sides between B1012 and B1009.
LL_STUDY_WEST = (980.6, 1308.1, 125.9, 224.0, 106.4)
LL_STUDY_EAST = (2445.4, 1337.1, 167.9, 220.5, 81.0)
LL_STAIR_OUTER = (2456.6, 1309.4, 231.0, 286.4, 81.9)
LL_MAIN_STAIR = ('main-stair', 'circulation', 'Main Stair', 'Stair', ['stairs'],
                 _band(LL_STUDY_EAST, LL_STAIR_OUTER, -135, 68))

# Floor 1's lecture halls: the red outlines on pages 21 (1210) and 18 (1220) of the Teaching
# Spaces PDF, registered onto the CAD sheet by a similarity fitted on the structural columns
# along the halls (residual under 2 pt). 1220 gives way to 1210 where the two outlines cross.
F1_HALL_1210 = [
    (2053.3, 978.2), (2178.6, 1064.1), (2369.3, 1277.2), (2387.7, 1286.0), (2403.3, 1290.0), (2416.5, 1290.1),
    (2427.4, 1287.2), (2436.6, 1282.1), (2444.2, 1275.8), (2456.2, 1262.6), (2532.9, 1023.6), (2531.6, 994.1),
    (2419.7, 878.4), (2406.4, 880.1), (2398.9, 850.1), (2411.0, 848.6), (2403.8, 818.7), (2236.3, 854.2),
    (2242.9, 886.2), (2175.6, 900.2), (2121.2, 919.3),
]
F1_HALL_1220 = [
    (2559.1, 1475.6), (2833.7, 1418.2), (2880.9, 1374.8), (2816.7, 1305.0), (2588.6, 1052.8), (2573.1, 1049.8),
    (2564.9, 1049.5), (2556.6, 1050.5), (2548.2, 1053.2), (2539.9, 1058.0), (2531.8, 1065.4), (2524.0, 1075.8),
    (2480.6, 1234.1), (2415.9, 1315.8),
]
FLOORS = {
    # The Lower Level sheet is at 1/8" = 1' and rotated; the transform was fitted on the six
    # elevator shafts (X-marked squares) shared with the upper floors (residual < 0.1 pt).
    '0': dict(pdf='Lower_Level', label='LL', level=0, label_sizes=(7.0, 8.0), number_re=r'^B\d{4}[A-Z]?$',
              transform=(0.63577, -6.9324, -153.26, 589.22), named=LL_CORES, exits=True, min_room=1800,
              # The service rooms carry no number on this plan (the sheet is
              # drawn larger, so the size limits are too); B1335's label sits in its doorway
              unnamed=4000, unnamed_max=90000,
              # The labels sit at the rooms' doors: the rooms are drawn by hand from the walls.
              hand={**LL_TEACHING,
                    'B1335': [(1456, 2002), (1596, 2002), (1596, 2214), (1456, 2214)],
                    'B1342': [(1362, 1769), (1548, 1769), (1548, 1925), (1362, 1925)],
                    'B1346': [(1262, 1769), (1356, 1769), (1356, 1925), (1262, 1925)],
                    'B1336': [(1556, 1769), (1737, 1769), (1737, 1926), (1556, 1926)],
                    'B1040C': [(433, 716), (543, 697), (561, 808), (451, 827)],
                    'B1040D': [(549, 696), (632, 683), (650, 794), (567, 807)],
                    'B1040E': [(638, 682), (718, 668), (736, 779), (656, 793)],
                    'B1040F': [(724, 667), (810, 653), (828, 763), (742, 778)],
                    'B1040G': [(816, 652), (894, 639), (912, 749), (834, 762)],
                    # five walls: the doors face B1026 on a straight wall cutting the corner
                    'B1040': [(400, 836), (912, 752), (957, 1016), (887, 1068), (457, 1139)],
                    'B1030': ('OPEN STUDY', _ellipse(*LL_STUDY_WEST)),
                    'B1010': ('OPEN STUDY', _ellipse(*LL_STUDY_EAST))},
              # the north-east corner is a recording studio: its rooms sit in one suite, drawn
              # with straight lines around the cores, and take the suite's name
              # the storage room east of the hall's partition is not closed on the sheet
              manual=[LL_MAIN_STAIR, ('storage-ne', 'service', 'Storage Room', 'Storage', ['storage'], [[2505, 630], [2608, 630], [2608, 795], [2505, 795]]),
                      ('recording-studio', 'lab', 'Recording Studio', '', ['recording', 'studio'], [[2159.3, 574.4], [2174.7, 779.0], [2157.5, 780.3], [2256.6, 898.9], [2169.2, 972.0], [2371.7, 980.8], [2264.8, 929.8], [2255.5, 821.6], [2302.5, 817.5], [2501.5, 810.7], [2485.7, 626.8], [2607.7, 616.3], [2623.3, 799.0], [2614.6, 799.7], [2620.5, 868.6], [2623.1, 959.2], [2705.3, 943.0], [2669.9, 534.3], [2346.8, 563.5], [2240.0, 571.8], [2239.7, 568.3]])],
              suites={'recording-studio': ('lab', 'Recording Studio', ['recording', 'studio'], [(2759.7, 668.5), (2703.5, 463.3), (2107.3, 670.1), (2776.4, 857.7), (2137.5, 854.3), (2287.6, 499.5), (2523.2, 478.8), (2405.7, 489.0), (2175.8, 508.1)])},
              # room-12's tip and room-10's walls: plain boxes
              square=[(2105, 881), (2095, 688)],
              # the closet between classrooms B1008 and B1009, the pits and closets by the
              # Southwest stair and the elevators, and the cell at the Northeast stair's foot
              blank=[(2860, 1315), (780, 1184), (888, 1524), (956, 1531), (693, 1559), (2283, 802)],
              # the step-free route from the Lower Level is by the Southwest elevators
              pois=[('accessible-elevators', 'Accessible elevators', 'accessible', (2480, 1716), 'Step-free route to the floors above')],
              quad={'B1040H'}),
    # The covered plaza between the Southwest block and the main building is outside.
    '1': dict(pdf='1', label='1', level=1, exterior=[(960, 1600)], exits=True, unnamed=2500, atrium=(1499, 1219, 128, 185, 80.5),
              # a sliver on the stair landing by the Northeast elevators, a closet by the Northeast core
              blank=[(1610, 959), (2266, 826)],
              manual=[EAST_STAIR, NE_STAIR_EAST_F1, *SW_BLOCK_RESTROOMS],
              # the plan's "Project Rm." 1456 is the TA printer room; 1110 (an "open office" on
              # the plan) is a four-walled reservable meeting room like 1110A/B beside it
              rename={'1456': 'TA PRINTER ROOM', '1110': 'MEETING'},
              # The two lecture halls carry no number on this plan (their tiers split them into
              # stripes) and the drone lab's label sits at its door: drawn by hand. The halls are
              # the red outlines of the Teaching Spaces PDF (1210 on page 21, 1220 on page 18),
              # without the storage rooms along their backs; 1230 is the drone lab's walls below 1220.
              hand={  # 1420 as six walls: the hall below the kitchen counter and the wing under room-12 (the
                    # entry nook on the facade and the strip behind room-9 are left out)
                    '1420': [[367.1, 1623.8], [608.0, 1594.4], [626.0, 1735.0], [711.1, 1697.6], [737.2, 1902.4], [467.7, 1935.0]],'1210': ('LECTURE HALL', F1_HALL_1210),
                    '1220': ('LECTURE HALL', F1_HALL_1220),
                    '1110': [(1195, 882), (1241, 874), (1274, 1050), (1143, 1078)],
                    '1120': [(1240, 712), (1324, 700), (1401, 818), (1206, 862)],
                    '1230': [(2532.0, 1476.7), (2559.1, 1475.6), (2833.7, 1418.2), (2880.9, 1374.8), (2893.3, 1380.0),
                             (3036.7, 1543.3), (2650.0, 1620.0)]},
              # the Southwest wing's stair of the upper floors is the Southwest block's stair here
              # named rooms without a room number take their wing from here
              wings={'fare-gates': 'Northeast'},
              named=[n for n in CORES if n is not SW_STAIR] + SW_RESTROOMS + [
                  # the Northeast core's multi-stall restroom is east of the elevators here
                  (1640, 840, 'ne-restroom', 'service', *MENS),
                  # the transit-style fare gates between the Northeast elevators and the lobby
                  (1497, 982, 'fare-gates', 'service', '🚨 Fare Gates (Turnstiles)', '🚨 Fare Gates', ['fare gates', 'turnstiles', 'entry', 'access']),
                  (575, 1478, 'sw-stair', 'circulation', 'Southwest Stair', 'Stair', ['stairs']),
                  (1261.6, 1700.3, 'cafe', 'amenity', 'Cafe', 'Cafe', ['cafe', 'food']),
                  (1608.3, 1732.7, 'cafe-seating', 'amenity', 'Cafe Seating', 'Seating', ['cafe', 'seating']),
                  ([(559.3, 995.8), (612.9, 991.7), (551.2, 916.2)], None, 'sw-block-stair', 'circulation', 'Southwest Block Stair', 'Stair', ['stairs']),
              ]),
    # Floors 2 and 3 follow floor 4 (below): the research labs are boxes, the kitchens and
    # meeting rooms with a pilaster or a curved wall are four-cornered. Stairs wind down inside
    # the atrium's rail on these floors, so the rail's ellipse is given.
    '2': dict(pdf='2', label='2', level=2, named=CORES + NE_RESTROOMS + [COPY_ROOM('2')], manual=[EAST_STAIR, NE_STAIR_EAST_F2] + SW_CORE_RESTROOMS,
              box={'2184', '2190', '2192', '2322', '2360', '2404', '2408'},
              quad={'2130', '2133', '2219', '2228', '2345', '2355', '2361', '2389', '2431', '2445'},
              hand={  # 2405's front wall on the line of 2403's, its sides parallel (as 3405 above it)
                    '2405': [[519.1, 1388.4], [562.9, 1373.7], [569.8, 1431.8], [525.0, 1437.3]],'2310': [[1651.4, 1658.6], [1767.9, 1644.0], [1814.6, 1820.8], [1673.9, 1838.4]],
                    '2161': [(2128, 469), (2203, 452), (2255, 514), (2168, 594), (2132, 545)]},
              atrium=(1460, 1260, 252, 152, -14),
              atrium_stairs=[dict(side='west', goes='up', to=3, top='south')]),
    '3': dict(pdf='3', label='3', level=3, named=CORES + NE_RESTROOMS + [COPY_ROOM('3')], manual=[EAST_STAIR] + SW_CORE_RESTROOMS,
              box={'3131', '3184', '3192', '3322', '3406'}, asis={'3190'}, desk_box={'3340', '3360'},
              rename={'3397': 'ERSO IT HELP DESK'},  # the plan says IT Help Desk; it is ERSO's
              quad={'3130', '3161', '3219', '3350', '3355', '3375', '3431', '3447'},
              # the labs 3184/3192 are split by benches drawn as walls; 3310 opens onto 3340
              hand={  # 3112 reaches to 3114's wall; the partition between is casework
                    '3112': [[1306.9, 755.0], [1233.3, 771.0], [1237.7, 824.7], [1318.2, 808.2]],  # 3405's front wall on the line of 3403's, its sides parallel; the sheet's own wall bends
                    '3405': [[517.8, 1387.1], [563.5, 1372.1], [570.9, 1432.8], [524.1, 1438.6]],'3184': [(2424, 1100), (2560, 1240), (2474, 1320), (2340, 1175)],
                    '3192': [(2428, 1098), (2525, 1047), (2620, 1152), (2563, 1236)],
                    '3310': [[1650.0, 1650.0], [1770.0, 1650.0], [1818.0, 1824.0], [1670.6, 1827.1]]},
              atrium=(1459.3, 1241.6, 186.6, 291.5, 73.1),
              atrium_stairs=[dict(side='west', goes='down', to=2, top='south'), dict(side='east', goes='up', to=4, top='north')]),
    # The labs 4131/4184/4192/4408/4322 are plain boxes on the plan (their internal lines are
    # benches); the social kitchens 4130 and 4350 are boxes with one curved wall, and the
    # meeting rooms 4355/4375 and the study room 4310 are rectangles with a pilaster, a
    # cabinet or a closet in a corner.
    '4': dict(pdf='4', label='4', level=4, named=CORES + NE_RESTROOMS + [COPY_ROOM('4')], hand={  # 4382's west wall on 4384's
                    '4382': [[500.0, 1711.1], [461.1, 1715.9], [463.7, 1736.1], [502.4, 1731.4]],  # 4112 reaches to 4114; the partition the sheet draws between them is casework
                    '4112': [[1305.6, 753.4], [1232.2, 771.1], [1237.0, 826.5], [1317.3, 809.5]]},
              manual=[EAST_STAIR] + SW_CORE_RESTROOMS,
              box={'4131', '4184', '4192', '4322', '4360', '4408'}, desk_box={'4340'}, quad={'4130', '4350', '4355', '4375', '4310'},
              # the atrium is traced from its opening here; the east stair (down to 3) is found
              # in floor 3's rail ellipse, which the stairs share
              stair_frame=(1459.3, 1241.6, 186.6, 291.5, 73.1),
              atrium_stairs=[dict(side='east', goes='down', to=3, top='north')]),
    # Floor 5 is set back: the indoor blocks stand on a paved roof terrace inside the parapet
    # (seeded on its pavers and walkways). The passage between the restroom blocks of the south
    # bar is sealed so the terrace does not run into the building. The oval is the atrium's
    # skylight.
    '5': dict(pdf='5', label='5', level=5, unnamed=2500, unnamed_max=120000,
              named=[n for n in CORES if n is not ATRIUM] + F5_RESTROOMS + [
                  (1458, 1236, 'skylight', 'circulation', 'Atrium Skylight', 'Skylight', ['atrium', 'skylight']),
                  # the plan numbers only the furnished rooms: the oval event space, the social
                  # kitchen (its kitchen and its lounge are two faces) and the straight-run
                  # stair at the west end are named here
                  (618, 1682, '5300', 'amenity', 'Event Space 5300', '5300', ['event space', 'events', 'oval']),
                  ([(1902, 688), (1934, 815)], None, 'social-kitchen', 'amenity', 'Social Kitchen / Working Lounge', 'Social\nKitchen', ['social', 'kitchen', 'working', 'lounge']),
                  (689, 975, 'west-stair', 'circulation', 'West Stair', 'Stair', ['stairs'])],
              # 5113's east wall carries a closet, 5320's a row of cabinets: four walls
              quad={'5113', '5320'},
              # a planter strip and an electrical closet are not rooms
              blank=[(323, 1413), (1636, 1649), (860, 1665), (766, 1562), (882, 1612)],  # closets and shafts of the south bar
              manual=F5_SINGLE_RESTROOMS,
              terrace=[(1800, 1300), (1100, 1350), (1210, 1290), (1300, 1475), (1400, 1420), (1700, 1000)],  # the deck around the skylight; the bands behind the blocks are walled off
              extra=[[1310, 1522, 1342, 1515]],
              # 5370's label sits in the corridor below it, and 5310's fill leaks along the
              # curtain wall: both drawn by hand
              hand={  # 5360 and 5370 square to the facade, their front walls on one line
                    '5360': [[413.8, 938.4], [578.1, 891.3], [611.8, 1008.9], [447.4, 1055.9]],'5370': [[169.1, 1008.5], [394.2, 944.0], [439.8, 1103.4], [214.8, 1167.9]],
                    '5310': [(1113, 1587), (1243, 1575), (1255, 1783), (1118, 1795)]},
              atrium=(1458, 1236, 126, 226, 71.7)),
}

for f in FLOORS.values():
    sheet = 'lower-level' if f['level'] == 0 else str(f['level'])
    f['source'] = f'floorplan_floor-{sheet}_2025-10-02.pdf'
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
    f.setdefault('atrium', None)
    f.setdefault('hand', {})
    f.setdefault('unnamed', 0)
    f.setdefault('unnamed_max', 40000)
    f.setdefault('terrace', [])
    f.setdefault('wings', {})
    f.setdefault('square', [])
    f.setdefault('suites', {})
    f.setdefault('asis', set())
    f.setdefault('desk_box', set())
    f.setdefault('atrium_stairs', [])
    f.setdefault('stair_frame', None)
    f.setdefault('blank', [])
    f.setdefault('rename', {})


# ---------------------------------------------------------------------------
# Categories and display names from the plan's room names
# ---------------------------------------------------------------------------
def category(name: str, id_: str) -> str:
    words = set(name.upper().replace('/', ' ').replace('-', ' ').split())
    has = lambda *ws: any(w in words for w in ws)
    if has('CIRCULATION', 'CORRIDOR') or 'CORR' in id_.upper():
        return 'circulation'
    if has('PIAZZA'):
        return 'study'  # the piazzas are open study space (the lobbies, x000, were caught above)
    if has('COLLAB', 'PORCH', 'FLEXIBLE', 'TERRACE') or (has('OPEN') and has('OFFICE')):
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
    if has('PRINTER', 'COPY'):
        return 'copy'
    if has('HELP', 'STORAGE', 'SHIPPING', 'DAS', 'RECEPTION', 'MECH', 'ELEC', 'FACILITY'):
        return 'service'
    if has('STUDY', 'STUDENT', 'HOURS'):
        return 'study'
    return 'office'


TITLE_FIXES = {
    # every office is just an "Office" on the map (the plan distinguishes faculty offices)
    'Faculty Office': 'Office',
    'Social Kitchen/Working Lounge': 'Social Kitchen / Working Lounge',
    'Piazza Informal Collab': 'Piazza – Informal Collab',
    'Project Rm.': 'Project Room',
    'Phone Rm.': 'Phone Room',
    'Group Study Large': 'Large Group Study',
    'General Lab Research': 'General Research Lab',
}
ADD_ROOM = {'Focus', 'Huddle', 'Small Meeting', 'Medium Meeting', 'Large Meeting', 'Extra Large Meeting', 'Meeting', 'Lactation', 'Meditation', 'Green'}


ACRONYMS = {'It': 'IT', 'Hci': 'HCI', 'Das': 'DAS', 'Mri': 'MRI', 'Ta': 'TA', 'Erso': 'ERSO'}


def display_name(name: str, id_: str) -> str:
    """'FACULTY OFFICE' + '3117' -> 'Office 3117'; 'HUDDLE' -> 'Huddle Room 3189'."""
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
