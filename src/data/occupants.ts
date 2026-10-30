import type { Space } from './types';

/** The plan room number of a generated space id such as `4-4123` or `0-b1342`; undefined for named rooms. */
export function roomNumber(space: Space): string | undefined {
  const m = /^[^-]+-([a-z]?\d+[a-z]?)$/.exec(space.id);
  return m ? m[1].toUpperCase() : undefined;
}

/**
 * Attach occupants (keyed by plan room number) to the matching spaces. Returns the room
 * numbers that matched no space, so stale directory entries can be reported.
 */
export function assignOccupants(
  spaces: Space[],
  occupants: Record<string, string[]>,
): { spaces: Space[]; unmatched: string[] } {
  const seen = new Set<string>();
  const out = spaces.map((space) => {
    const number = roomNumber(space);
    const people = number ? occupants[number] : undefined;
    if (!number || !people?.length) return space;
    seen.add(number);
    return { ...space, occupants: [...people] };
  });
  const unmatched = Object.keys(occupants).filter((number) => occupants[number].length && !seen.has(number));
  return { spaces: out, unmatched };
}

/** "Krste Asanović" and "krste asanovic" compare equal: letters only, accents stripped, lower case. */
function nameKey(name: string): string {
  return name.normalize('NFKD').replace(/[^a-z]/gi, '').toLowerCase();
}

/** Within one typo (a letter added, dropped or changed) of each other. */
function almostSame(a: string, b: string): boolean {
  if (a === b) return true;
  if (Math.abs(a.length - b.length) > 1) return false;
  let i = 0;
  while (i < a.length && i < b.length && a[i] === b[i]) i++;
  const tailA = a.slice(a.length > b.length ? i + 1 : i);
  const tailB = b.slice(b.length > a.length ? i + 1 : i);
  return a.length === b.length ? tailA.slice(1) === tailB.slice(1) : tailA === tailB;
}

/**
 * The same person written twice: equal keys, a one-letter typo, the same surname with the
 * same first initial ("Venkat" for "Venkatesan"), or the same first name with surnames that
 * agree for six letters ("Parameswararan" for "Parameswaran").
 */
function samePerson(a: string, b: string): boolean {
  const ka = nameKey(a);
  const kb = nameKey(b);
  if (almostSame(ka, kb)) return true;
  const wa = a.trim().split(/\s+/);
  const wb = b.trim().split(/\s+/);
  if (wa.length < 2 || wb.length < 2) return false;
  const [firstA, lastA] = [nameKey(wa[0]), nameKey(wa[wa.length - 1])];
  const [firstB, lastB] = [nameKey(wb[0]), nameKey(wb[wb.length - 1])];
  if (lastA === lastB && firstA[0] === firstB[0]) return true;
  return firstA === firstB && lastA.length >= 6 && lastA.slice(0, 6) === lastB.slice(0, 6);
}

/**
 * Occupants from two sources merged room by room. The primary source's names come first
 * and are kept as spelled; a secondary name is added only when it names nobody already
 * there (allowing for a missing hyphen, a typo, or "Venkat" for "Venkatesan").
 */
export function mergeOccupants(
  primary: Record<string, string[]>,
  secondary: Record<string, string[]>,
): Record<string, string[]> {
  const out: Record<string, string[]> = {};
  for (const [room, names] of Object.entries(primary)) out[room] = [...names];
  for (const [room, names] of Object.entries(secondary)) {
    const list = (out[room] ??= []);
    for (const name of names) if (!list.some((have) => samePerson(have, name))) list.push(name);
  }
  return out;
}

/** "Michael I. Jordan" → ["Michael I.", "Jordan"], so a name can wrap onto two short map lines. */
export function nameLines(name: string): string[] {
  const at = name.trim().lastIndexOf(' ');
  return at > 0 ? [name.slice(0, at).trim(), name.slice(at + 1).trim()] : [name.trim()];
}
