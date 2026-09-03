import { wall, type Wall, type XY } from '../helpers';
import type { Point } from '../types';

/**
 * Gateway building outline, shared by every floor.
 *
 * Coordinates are the floor frame used since Level 4 was traced (roughly the pixel grid of
 * the whole-floor sign, 2000 × 1057). The vertices below were re-fitted from the
 * perspective-corrected whole-floor signs of Levels 2 and 3 (see `tools/trace_signs/`):
 * straight walls are least-squares lines through the drawn walls, corners are their
 * intersections, and curved walls are circular arcs fitted to the drawn curves.
 *
 * Levels 2, 3 and 4 share the same footprint except for the Southwest entrance: Level 2
 * has a deep semicircular notch there, Levels 3 and 4 only a shallow inward bow. Level 1
 * (ground) is different: the Southwest wing is a separate block and the area under the
 * notch is open, so its west wall runs from the Northeast wing's corner down to the
 * south wall.
 */
export const V = {
  swNW: [34.0, 357.6] as XY, // Southwest wing, north-west corner
  swNE: [418.6, 241.3] as XY, // Southwest wing, north-east corner
  notchS: [483.8, 433.3] as XY, // facade notch: south end of the curve (bottom of swEast)
  notchB: [587.3, 517.3] as XY, // facade notch: bottom of the U
  notchE: [664.0, 370.1] as XY, // facade notch: north end of the curve (bottom of neWest)
  neNW: [672.6, 162.1] as XY, // Northeast wing, north-west corner
  neN: [1312.2, 21.4] as XY, // Northeast wing, north corner
  tip: [1978.6, 700.1] as XY, // east tip
  tipSW: [1583.2, 778.5] as XY, // tip, south-west corner
  sBend: [1392.4, 573.6] as XY, // atrium S-curve: start (end of neInner)
  sPeak: [1213.7, 485.2] as XY, // atrium S-curve: top of the hook
  sEnd: [1132.6, 608.5] as XY, // atrium S-curve: end
  eMid: [1144.7, 709.5] as XY, // Southwest wing east wall begins
  swSE: [1189.1, 852.1] as XY, // Southwest wing, south-east corner
  bumpE: [715.2, 914.1] as XY, // Level 3/4 entrance bow: east end
  bumpW: [533.5, 938.3] as XY, // Level 3/4 entrance bow: west end
  swSW: [262.2, 973.7] as XY, // Southwest wing, south-west corner
  swW: [182.2, 710.6] as XY, // bend in the Southwest wing west wall
  notchE2: [734.8, 911.5] as XY, // Level 2 entrance notch: east end
  n2a: [670.4, 827.9] as XY, // Level 2 entrance notch: east flank
  notchB2: [601.7, 786.6] as XY, // Level 2 entrance notch: top
  n2b: [547.6, 842.9] as XY, // Level 2 entrance notch: west flank
  notchW2: [516.3, 940.6] as XY, // Level 2 entrance notch: west end
  L1nw: [690.1, 158.1] as XY, // Level 1: north-west corner of the ground floor (on the north wall line)
  L1w: [607.2, 585.2] as XY, // Level 1: bend in the west wall
  L1sw: [663.0, 921.2] as XY, // Level 1: south-west corner (on the south wall line)
} satisfies Record<string, XY>;

const xy = ([x, y]: XY, bulge?: number): Point => (bulge === undefined ? { x, y } : { x, y, bulge });

/** Levels 3 and 4 (clockwise on screen). A bulge makes the edge to the next vertex a circular arc. */
export const outline34: Point[] = [
  xy(V.swNW),
  xy(V.swNE),
  xy(V.notchS, 0.315),
  xy(V.notchB, 0.208),
  xy(V.notchE),
  xy(V.neNW),
  xy(V.neN),
  xy(V.tip),
  xy(V.tipSW),
  xy(V.sBend, 0.163),
  xy(V.sPeak, 0.373),
  xy(V.sEnd),
  xy(V.eMid),
  xy(V.swSE),
  xy(V.bumpE, 0.188),
  xy(V.bumpW),
  xy(V.swSW),
  xy(V.swW),
];

/** Level 2: same footprint with the deep Southwest entrance notch. */
export const outline2: Point[] = [
  xy(V.swNW),
  xy(V.swNE),
  xy(V.notchS, 0.34),
  xy(V.notchB, 0.225),
  xy(V.notchE),
  xy(V.neNW),
  xy(V.neN),
  xy(V.tip),
  xy(V.tipSW),
  xy(V.sBend, 0.155),
  xy(V.sPeak, 0.34),
  xy(V.sEnd),
  xy(V.eMid),
  xy(V.swSE),
  xy(V.notchE2, -0.21),
  xy(V.n2a, 0.315),
  xy(V.notchB2, 0.325),
  xy(V.n2b, -0.22),
  xy(V.notchW2),
  xy(V.swSW),
  xy(V.swW),
];

/** Level 1 main footprint: Northeast wing, atrium and the south core. */
export const outline1: Point[] = [
  xy(V.L1w),
  xy(V.L1nw),
  xy(V.neN),
  xy(V.tip),
  xy(V.tipSW),
  xy(V.sBend, 0.163),
  xy(V.sPeak, 0.373),
  xy(V.sEnd),
  xy(V.eMid),
  xy(V.swSE),
  xy(V.L1sw),
];

/**
 * Level 1 Southwest block: a separate ground-floor building under the west part of the
 * Southwest wing (traced from the Level One whole-floor sign). It shares the wing's north,
 * west and south walls exactly; only its east edge is its own.
 */
const lerp = (a: XY, b: XY, t: number): XY => [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t];
export const L1_SW_NE: XY = lerp(V.swNW, V.swNE, 0.76);
export const L1_SW_SE: XY = lerp(V.swSE, V.swSW, 0.74);
export const outline1sw: Point[] = [xy(V.swNW), xy(L1_SW_NE), xy(L1_SW_SE), xy(V.swSW), xy(V.swW)];

/** Named straight wall segments (clockwise), used to define perimeter rooms relative to the outline. */
export const walls = {
  swNorth: wall(V.swNW, V.swNE),
  swEast: wall(V.swNE, V.notchS),
  neWest: wall(V.notchE, V.neNW),
  neNorth: wall(V.neNW, V.neN),
  neDiagonal: wall(V.neN, V.tip),
  neTip: wall(V.tip, V.tipSW),
  neInner: wall(V.tipSW, V.sBend),
  sSide: wall(V.sEnd, V.eMid),
  swEastLower: wall(V.eMid, V.swSE),
  swSouth: wall(V.swSE, V.swSW),
  swWestS: wall(V.swSW, V.swW),
  swWestN: wall(V.swW, V.swNW),
} satisfies Record<string, Wall>;

/** Nominal frame size (the Level 4 sign's pixel grid); floors use it as their width/height. */
export const FRAME = { width: 2000, height: 1057 };
