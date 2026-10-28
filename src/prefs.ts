/** User preferences kept in localStorage (which may be unavailable or full; both are fine to ignore). */

const KEY_REQUIRE_SHIFT = 'gateway-map.shortcuts.requireShift';

function read(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function write(key: string, value: string) {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    /* private mode or storage disabled: the preference lasts for this page view only */
  }
}

let requireShift = read(KEY_REQUIRE_SHIFT) === '1';

/** Whether single-letter shortcuts (such as B for the Lower Level) need Shift held as well. */
export const getRequireShift = () => requireShift;

export function setRequireShift(on: boolean) {
  requireShift = on;
  write(KEY_REQUIRE_SHIFT, on ? '1' : '0');
}
