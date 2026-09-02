import type { Floor } from '../data/types';
import type { Store } from '../state';

export function mountFloorSwitcher(root: HTMLElement, floors: Floor[], store: Store) {
  root.innerHTML = '';
  root.setAttribute('role', 'group');
  root.setAttribute('aria-label', 'Floor');

  const buttons = new Map<string, HTMLButtonElement>();
  for (const f of [...floors].sort((a, b) => b.level - a.level)) {
    const b = document.createElement('button');
    b.type = 'button';
    b.className = 'floor-btn';
    b.textContent = f.label;
    b.title = `Floor ${f.label}`;
    b.addEventListener('click', () => store.set({ floorId: f.id, selectedSpaceId: null }));
    buttons.set(f.id, b);
    root.appendChild(b);
  }

  store.subscribe((s) => {
    for (const [id, b] of buttons) b.setAttribute('aria-pressed', String(id === s.floorId));
  });
}
