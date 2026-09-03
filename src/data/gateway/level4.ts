import { affineFromPairs, cornerRoom, ellipse, offWall, quad, transformXY, type Affine } from '../helpers';
import type { Point, Poi } from '../types';
import { floorBuilder, type Wing } from './floor';
import { V, walls } from './outline';

/**
 * Level 4, traced by hand from the wayfinding signs photographed on the floor:
 *  - the whole-floor sign ("Level Four") gave the outline, atrium stair and cores;
 *  - the "Level 4 Northeast" and "Level 4 Southwest" signs give room-by-room detail.
 *
 * Two kinds of geometry:
 *  1. Perimeter rooms are defined *relative to the outline*: a span along a named wall
 *     segment plus a depth (see `rowOffWall` / `cornerRoom`). Their outer edge therefore
 *     coincides exactly with the outline, and neighbours share dividing edges.
 *  2. Interior rooms are traced in the pixel space of the detail sign and mapped onto
 *     the floor with an affine transform fitted on the wing's corners (`NE`, `SW`).
 *
 * The outline itself lives in outline.ts and is shared with the other floors.
 */

const { spaces, place, traced, perimeterRow } = floorBuilder('4');

// ---------------------------------------------------------------------------
// Detail-sign → floor transforms, fitted on the wing corners above
// ---------------------------------------------------------------------------
const NE: Affine = affineFromPairs([
  [[45, 235], V.neNW],
  [[985, 40], V.neN],
  [[1962, 1081], V.tip],
  [[1400, 1119], V.tipSW],
]);

const SW: Affine = affineFromPairs([
  [[55, 225], V.swNW],
  [[630, 55], V.swNE],
  [[462, 1308], V.swSW],
  [[1973, 1088], V.swSE],
]);

// ---------------------------------------------------------------------------
// Northeast wing (rooms 4100–4299)
// ---------------------------------------------------------------------------
{
  const w: Wing = 'Northeast';
  const { neWest, neNorth, neDiagonal, neTip } = walls;

  // West wall (bottom → top): stair, all-gender restroom, 4112, corridor, 4111 (corner).
  place(w, 'NE Stair', offWall(neWest, 0.08, 0.34, 92), {
    cat: 'circulation',
    name: 'Northeast Stair',
    label: 'Stair',
    tags: ['stairs'],
  });
  place(w, 'NE All-Gender Restroom', offWall(neWest, 0.34, 0.56, 52), {
    cat: 'service',
    name: 'All-Gender Restroom (NE)',
    label: 'All-gender WC',
    tags: ['restroom', 'all gender'],
  });
  place(w, '4112', offWall(neWest, 0.56, 0.75, 52), { cat: 'office' });
  place(w, '4111', cornerRoom(neWest, 0.8, neNorth, 0.061), { cat: 'office' });

  // North wall: 4113–4125, the social-kitchen frontage, 4139–4147, then 4161 on the corner.
  perimeterRow(w, neNorth, 0.061, 0.484, 65, ['4113', '4115', '4117', '4119', '4121', '4123', '4125']);
  perimeterRow(w, neNorth, 0.654, 0.941, 48, ['4139', '4141', '4143', '4145', '4147']);
  place(w, '4161', cornerRoom(neNorth, 0.941, neDiagonal, 0.085), { cat: 'meeting' });

  // Diagonal (north-east) wall, from 4161 down to the tip.
  perimeterRow(w, neDiagonal, 0.085, 0.322, 57, ['4163', '4165', '4167', '4169', '4171', '4173']);
  place(w, '4190', offWall(neDiagonal, 0.322, 0.436, 100), { cat: 'open' });
  perimeterRow(w, neDiagonal, 0.436, 0.628, 57, ['4191', '4193', '4195', '4197', '4199']);
  place(w, '4210', offWall(neDiagonal, 0.628, 0.73, 100), { cat: 'open' });
  perimeterRow(w, neDiagonal, 0.73, 0.9, 57, ['4211', '4213', '4215', '4217'], { weights: [1, 1, 1.1, 1.4] });
  place(w, '4219', cornerRoom(neDiagonal, 0.9, neTip, 0.288), { cat: 'meeting' });

  // Tip's south wall, from the tip back towards the atrium.
  place(w, '4220', offWall(neTip, 0.356, 0.7, 75), { cat: 'open' });
  place(w, '4228', offWall(neTip, 0.75, 0.91, 40), { cat: 'office' });

  // Core beside the west wall (interior, traced)
  traced(w, NE, 'NE Men’s Restroom', quad([150, 335], [350, 320], [355, 480], [150, 490]), {
    cat: 'service',
    name: 'Men’s Restroom (NE)',
    label: 'Men’s WC',
    tags: ['restroom', 'men'],
  });
  traced(w, NE, 'NE Elevator', quad([230, 485], [350, 480], [350, 570], [230, 580]), {
    cat: 'circulation',
    name: 'Northeast Elevator',
    label: 'Elevator',
    tags: ['elevator'],
  });

  // Interior rooms (traced)
  traced(w, NE, '4114', quad([140, 340], [210, 330], [215, 395], [145, 405]), { cat: 'office' });
  traced(w, NE, '4116', quad([210, 330], [280, 320], [285, 385], [215, 395]), { cat: 'office' });
  traced(w, NE, '4118', quad([280, 320], [350, 305], [355, 370], [285, 385]), { cat: 'office' });
  traced(w, NE, '4126', quad([400, 300], [455, 292], [460, 365], [405, 372]), { cat: 'office' });
  traced(w, NE, '4128', quad([455, 292], [510, 284], [515, 357], [460, 365]), { cat: 'office' });
  traced(w, NE, '4131', quad([395, 440], [560, 425], [565, 555], [400, 570]), { cat: 'lab' });
  traced(w, NE, '4136', quad([690, 235], [730, 230], [733, 280], [693, 285]), { cat: 'focus' });
  traced(w, NE, '4138', quad([730, 230], [770, 225], [773, 275], [733, 280]), { cat: 'focus' });
  traced(w, NE, '4144', quad([690, 285], [770, 275], [775, 335], [695, 345]), { cat: 'office' });
  traced(w, NE, '4146', quad([700, 345], [780, 335], [785, 400], [705, 410]), { cat: 'office' });
  traced(w, NE, '4148', quad([710, 410], [790, 400], [795, 465], [715, 475]), { cat: 'office' });
  traced(w, NE, '4151', quad([838, 193], [883, 238], [838, 283], [793, 238]), {
    cat: 'meeting',
    description: 'The diamond-shaped meeting room beside the social kitchen.',
  });
  traced(w, NE, '4160', quad([800, 290], [940, 200], [1010, 300], [870, 400]), { cat: 'open' });
  traced(w, NE, '4158', quad([1000, 320], [1080, 345], [1040, 400], [960, 375]), { cat: 'office' });
  traced(w, NE, '4156', quad([960, 375], [1040, 400], [1000, 455], [920, 430]), { cat: 'office' });
  traced(w, NE, '4154', quad([920, 430], [1000, 455], [960, 510], [880, 485]), { cat: 'office' });
  traced(w, NE, '4152', quad([880, 485], [960, 510], [920, 565], [840, 540]), { cat: 'office' });
  traced(w, NE, '4189', quad([1085, 405], [1175, 430], [1150, 500], [1060, 475]), { cat: 'meeting' });
  traced(w, NE, '4187', quad([1060, 478], [1150, 502], [1130, 550], [1030, 525]), { cat: 'office' });
  traced(w, NE, '4185', quad([1030, 525], [1130, 550], [1110, 590], [1000, 570]), { cat: 'office' });
  traced(w, NE, '4181', quad([970, 540], [1020, 555], [1000, 600], [950, 585]), { cat: 'focus' });
  traced(w, NE, '4183', quad([1000, 590], [1050, 605], [1035, 640], [985, 625]), { cat: 'focus' });
  traced(w, NE, '4180', quad([1000, 610], [1170, 470], [1310, 585], [1140, 730]), { cat: 'open' });
  traced(w, NE, '4192', quad([1260, 640], [1340, 585], [1440, 715], [1360, 770]), { cat: 'lab' });
  traced(w, NE, '4184', quad([1140, 740], [1260, 640], [1360, 770], [1240, 860]), { cat: 'lab' });
  traced(w, NE, '4196', quad([1395, 745], [1445, 725], [1470, 770], [1420, 790]), { cat: 'focus' });
  traced(w, NE, '4198', quad([1420, 790], [1470, 770], [1495, 815], [1445, 835]), { cat: 'focus' });
  traced(w, NE, '4205', quad([1345, 800], [1420, 790], [1445, 835], [1370, 850]), { cat: 'office' });
  traced(w, NE, '4203', quad([1300, 835], [1370, 850], [1395, 895], [1325, 905]), { cat: 'office' });
  traced(w, NE, '4201', quad([1250, 870], [1325, 905], [1350, 945], [1275, 955]), { cat: 'office' });
  traced(w, NE, '4200', quad([1300, 880], [1480, 760], [1560, 880], [1390, 1000]), { cat: 'open' });
  traced(w, NE, '4208', quad([1560, 905], [1610, 935], [1570, 985], [1520, 955]), { cat: 'office' });
  traced(w, NE, '4206', quad([1520, 955], [1570, 985], [1530, 1030], [1480, 1000]), { cat: 'office' });
  traced(w, NE, '4204', quad([1480, 1000], [1530, 1030], [1490, 1075], [1440, 1045]), { cat: 'office' });
  traced(w, NE, '4202', quad([1440, 1045], [1490, 1075], [1455, 1110], [1405, 1080]), { cat: 'office' });
  traced(w, NE, '4222', quad([1610, 950], [1665, 985], [1625, 1035], [1570, 1000]), { cat: 'meeting' });
  traced(w, NE, '4224', quad([1570, 1000], [1625, 1035], [1585, 1080], [1530, 1045]), { cat: 'office' });
  traced(w, NE, '4226', quad([1530, 1045], [1585, 1080], [1545, 1120], [1490, 1085]), { cat: 'office' });
}

// ---------------------------------------------------------------------------
// Southwest wing (rooms 4300–4499)
// ---------------------------------------------------------------------------
{
  const w: Wing = 'Southwest';
  const { swNorth, swEast, swSouth, swWestS, swWestN, swEastLower } = walls;

  // North wall: 4431 (corner, meeting) … 4447 (corner, meeting)
  place(w, '4431', cornerRoom(swWestN, 0.866, swNorth, 0.14), { cat: 'meeting' });
  perimeterRow(w, swNorth, 0.14, 0.9, 62, ['4435', '4437', '4439', '4441', '4443', '4445']);
  place(w, '4447', cornerRoom(swNorth, 0.9, swEast, 0.3), { cat: 'meeting' });

  // East wall down into the notch: the big open area, then two focus rooms.
  place(w, '4430', offWall(swEast, 0.3, 0.6, 240), { cat: 'open' });
  place(w, '4446', offWall(swEast, 0.6, 0.8, 45), { cat: 'focus' });
  place(w, '4448', offWall(swEast, 0.8, 1.0, 45), { cat: 'focus' });

  // West wall (top → bottom). It bends at V.swW, so it is two walls; both run south→north and
  // parameters count from their southern end. 4389 starts right at the bend.
  place(w, '4420', offWall(swWestN, 0.68, 0.866, 98), { cat: 'open' });
  perimeterRow(w, swWestN, 0.155, 0.644, 72, ['4411', '4413', '4415', '4417', '4419']);
  place(w, '4389', offWall(swWestN, 0.015, 0.131, 65), { cat: 'meeting' });
  perimeterRow(w, swWestS, 0.565, 0.985, 62, ['4383', '4385', '4387']);
  place(w, '4380', offWall(swWestS, 0.338, 0.553, 85), { cat: 'open' });

  // South wall (east → west, since the outline is clockwise). t = 0 at the SE corner.
  place(w, '4310', cornerRoom(swEastLower, 0.0, swSouth, 0.105), { cat: 'office' });
  perimeterRow(w, swSouth, 0.105, 0.494, 65, ['4329', '4331', '4333', '4335', '4337', '4339', '4341', '4343', '4345'], {
    weights: [1, 1, 1, 1, 1, 1, 1, 1, 1.5],
  });
  perimeterRow(w, swSouth, 0.67, 0.925, 65, ['4361', '4363', '4365', '4367', '4369', '4371'], {
    overrides: { '4361': 'meeting' },
  });
  place(w, '4375', cornerRoom(swSouth, 0.925, swWestS, 0.269), { cat: 'meeting' });

  // Interior rooms (traced)
  traced(w, SW, '4432', quad([310, 410], [380, 390], [395, 470], [330, 490]), { cat: 'office' });
  traced(w, SW, '4434', quad([380, 390], [440, 375], [455, 455], [395, 470]), { cat: 'office' });
  traced(w, SW, '4436', quad([440, 375], [500, 360], [515, 440], [455, 455]), { cat: 'office' });
  traced(w, SW, '4438', quad([500, 360], [560, 345], [575, 425], [515, 440]), { cat: 'office' });
  traced(w, SW, '4442', quad([560, 345], [625, 330], [640, 410], [575, 425]), { cat: 'office' });
  traced(w, SW, '4418', quad([340, 490], [410, 475], [430, 570], [360, 590]), { cat: 'office' });
  traced(w, SW, '4414', quad([360, 590], [430, 570], [450, 660], [380, 680]), { cat: 'meeting' });
  traced(w, SW, '4408', quad([410, 470], [560, 440], [590, 600], [440, 630]), { cat: 'lab' });
  traced(w, SW, '4404', quad([560, 440], [720, 400], [750, 560], [590, 600]), { cat: 'lab' });
  traced(w, SW, 'Meditation Room', quad([560, 660], [630, 645], [640, 700], [570, 715]), {
    cat: 'amenity',
    name: 'Meditation Room',
    label: 'Meditation',
    tags: ['wellness', 'quiet'],
  });
  traced(w, SW, 'Lactation Room', quad([630, 645], [700, 630], [710, 690], [640, 700]), {
    cat: 'amenity',
    name: 'Lactation Room',
    label: 'Lactation',
    tags: ['wellness'],
  });
  traced(w, SW, 'SW Stair', quad([680, 700], [770, 680], [780, 760], [700, 780]), {
    cat: 'circulation',
    name: 'Southwest Stair',
    label: 'Stair',
    tags: ['stairs'],
  });
  traced(w, SW, '4399', quad([480, 870], [550, 860], [560, 930], [490, 945]), { cat: 'meeting' });
  traced(w, SW, '4397', quad([550, 860], [610, 850], [620, 925], [560, 930]), { cat: 'office' });
  traced(w, SW, '4395', quad([610, 850], [680, 840], [690, 915], [620, 925]), { cat: 'office' });
  traced(w, SW, '4384', quad([510, 955], [560, 945], [565, 990], [515, 1000]), { cat: 'focus' });
  traced(w, SW, '4382', quad([515, 1000], [565, 990], [575, 1035], [525, 1045]), { cat: 'focus' });
  traced(w, SW, '4376', quad([565, 940], [625, 930], [635, 1020], [575, 1030]), { cat: 'office' });
  traced(w, SW, '4374', quad([625, 930], [690, 920], [700, 1010], [635, 1020]), { cat: 'office' });
  traced(w, SW, '4355', quad([760, 840], [930, 815], [945, 1040], [770, 1060]), {
    cat: 'meeting',
    description: 'Large meeting room across from the social kitchen.',
  });
  traced(w, SW, '4370', quad([548, 1050], [770, 1030], [775, 1125], [555, 1145]), { cat: 'open' });
  traced(w, SW, '4360', quad([770, 1050], [935, 1030], [940, 1125], [775, 1140]), { cat: 'open' });
  traced(w, SW, '4322', quad([1160, 800], [1340, 790], [1345, 900], [1180, 905]), { cat: 'lab' });
  traced(w, SW, '4324', quad([1340, 790], [1410, 785], [1415, 890], [1345, 900]), { cat: 'office' });
  traced(w, SW, '4348', quad([1180, 905], [1230, 900], [1235, 985], [1185, 990]), { cat: 'office' });
  traced(w, SW, '4346', quad([1230, 900], [1290, 895], [1295, 980], [1235, 985]), { cat: 'office' });
  traced(w, SW, '4344', quad([1290, 895], [1350, 890], [1355, 975], [1295, 980]), { cat: 'office' });
  traced(w, SW, '4342', quad([1350, 890], [1415, 890], [1420, 975], [1355, 975]), { cat: 'office' });
  traced(w, SW, '4330', quad([1420, 745], [1580, 735], [1590, 1050], [1440, 1055]), { cat: 'open' });
  traced(w, SW, '4340', quad([1200, 995], [1440, 985], [1445, 1070], [1205, 1080]), { cat: 'open' });
  traced(w, SW, '4325', quad([1610, 955], [1665, 950], [1670, 990], [1615, 995]), { cat: 'focus' });
  traced(w, SW, '4327', quad([1615, 995], [1670, 990], [1675, 1030], [1620, 1035]), { cat: 'focus' });
  traced(w, SW, '4332', quad([1665, 945], [1750, 940], [1760, 1020], [1675, 1025]), { cat: 'meeting' });
  traced(w, SW, 'SW Elevator', quad([1600, 700], [1760, 695], [1770, 810], [1610, 815]), {
    cat: 'circulation',
    name: 'Southwest Elevator',
    label: 'Elevator',
    tags: ['elevator'],
  });
  traced(w, SW, 'SW All-Gender Restroom', quad([1760, 695], [1875, 690], [1880, 800], [1770, 810]), {
    cat: 'service',
    name: 'All-Gender Restroom (SW)',
    label: 'All-gender WC',
    tags: ['restroom', 'all gender'],
  });
  traced(w, SW, 'SW Women’s Restroom', quad([1610, 815], [1880, 800], [1890, 930], [1620, 940]), {
    cat: 'service',
    name: 'Women’s Restroom (SW)',
    label: 'Women’s WC',
    tags: ['restroom', 'women'],
  });
}

// ---------------------------------------------------------------------------
// Shared circulation (floor frame)
// ---------------------------------------------------------------------------
spaces.push({
  id: '4-atrium-stair',
  name: 'Atrium Stair',
  label: 'Atrium Stair',
  floorId: '4',
  category: 'circulation',
  polygon: ellipse(893, 520.5, 139.8, 82.2),
  description: 'The open stair through the central atrium connecting all levels.',
  tags: ['stairs', 'atrium'],
});

// ---------------------------------------------------------------------------
// Points of interest
// ---------------------------------------------------------------------------
const poi = (id: string, name: string, kind: Poi['kind'], at: Point, description?: string): Poi => ({
  id: `4-${id}`,
  name,
  floorId: '4',
  kind,
  at,
  description,
});

const pois: Poi[] = [
  poi('ne-entrance', 'Northeast entrance', 'exit', { x: 1107.4, y: 67.8 }),
  poi('sw-entrance', 'Southwest entrance', 'exit', { x: 638.6, y: 910.6 }),
  poi(
    'ne-porch',
    'Northeast front porch',
    'porch',
    transformXY(NE, [860, 490]),
    'Berkeley Artificial Intelligence Research Lab · College of Computing, Data Science, and Society · Data Science Undergraduate Studies · Department of Electrical Engineering and Computer Sciences',
  ),
  poi('sw-porch', 'Southwest front porch', 'porch', transformXY(SW, [810, 720]), 'Berkeley Artificial Intelligence Research Lab'),
  poi('ne-kitchen', 'Northeast social kitchen', 'cafe', transformXY(NE, [610, 330])),
  poi('sw-kitchen', 'Southwest social kitchen', 'cafe', transformXY(SW, [1070, 1000])),
  poi('nw-stair', 'Northwest stair', 'stairs', { x: 427.7, y: 365.6 }),
  poi('east-stair', 'East stair', 'stairs', { x: 1541.9, y: 672.2 }),
];

export const level4 = { spaces, pois };
