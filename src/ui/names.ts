import type { Space } from '../data/types';

/** "Michael I. Jordan, Jane Doe" for a shared office; empty when nobody is listed. */
export const occupantNames = (space: Space): string => (space.occupants ?? []).join(', ');

/** The room name with its occupant(s) after it: "Faculty Office 4123 · Michael I. Jordan". */
export const spaceTitle = (space: Space): string => {
  const names = occupantNames(space);
  return names ? `${space.name} · ${names}` : space.name;
};
