let region: HTMLElement | null = null;
let pending = 0;

/**
 * Speak a short message through the page's polite live region, for keyboard actions whose
 * effect would otherwise be silent to a screen reader (zooming, hitting the edge of a floor).
 * Actions that move focus do not need this: the newly focused control announces itself.
 */
export function announce(message: string) {
  region ??= document.getElementById('announcer');
  if (!region) return;
  // Clear first so repeating the same message (zooming twice) is spoken again.
  region.textContent = '';
  window.clearTimeout(pending);
  pending = window.setTimeout(() => {
    region!.textContent = message;
  }, 40);
}
