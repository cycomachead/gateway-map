import type { Point } from './types';

/** [x, y] pairs are terser to store in the generated floor data; a third value is the edge's bulge (see Point). */
export type XY = [number, number] | [number, number, number];

export const pts = (xy: XY[]): Point[] => xy.map(([x, y, bulge]) => (bulge ? { x, y, bulge } : { x, y }));
