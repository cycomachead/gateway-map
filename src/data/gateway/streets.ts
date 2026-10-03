import type { XY } from '../helpers';

/**
 * Hearst Avenue runs along the north facades (the straight top walls of the plan). Its centre
 * line is a gentle arc following the two north facades (the Southwest wing's and the
 * Northeast block's, which meet at a slight angle), set back from them by the sidewalk.
 * Hand-placed in the shared floor frame; not generated.
 */
export const hearst: { path: XY[]; width: number } = {
  path: [[-120, 484, -0.0348], [3260, -321]],
  width: 110,
};
