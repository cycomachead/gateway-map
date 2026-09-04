import type { Point } from './types';

/** [x, y] pairs are terser to store in the generated floor data. */
export type XY = [number, number];

export const pts = (xy: XY[]): Point[] => xy.map(([x, y]) => ({ x, y }));
