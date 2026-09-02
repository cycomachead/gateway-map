import { CATEGORY_LABELS, SPACE_CATEGORIES, type SpaceCategory } from '../data/types';
import type { Store } from '../state';

export function mountFilters(root: HTMLElement, store: Store) {
  root.innerHTML = '';
  root.setAttribute('role', 'group');
  root.setAttribute('aria-label', 'Filter by category');

  const buttons = new Map<SpaceCategory, HTMLButtonElement>();
  for (const cat of SPACE_CATEGORIES) {
    if (cat === 'circulation') continue; // never worth filtering on
    const b = document.createElement('button');
    b.type = 'button';
    b.className = `chip chip--${cat}`;
    b.textContent = CATEGORY_LABELS[cat];
    b.setAttribute('aria-pressed', 'false');
    b.addEventListener('click', () => {
      const next = new Set(store.get().categories);
      if (next.has(cat)) next.delete(cat);
      else next.add(cat);
      store.set({ categories: next });
    });
    buttons.set(cat, b);
    root.appendChild(b);
  }

  store.subscribe((s) => {
    for (const [cat, b] of buttons) b.setAttribute('aria-pressed', String(s.categories.has(cat)));
  });
}
