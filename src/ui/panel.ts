import { CATEGORY_LABELS, type Building, type Space } from '../data/types';
import type { Store } from '../state';

function esc(s: string): string {
  return s.replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]!);
}

function spaceDetails(space: Space, floorLabel: string): string {
  const facts: string[] = [`<dt>Floor</dt><dd>${esc(floorLabel)}</dd>`];
  if (space.wing) facts.push(`<dt>Wing</dt><dd>${esc(space.wing)}</dd>`);
  facts.push(`<dt>Type</dt><dd>${CATEGORY_LABELS[space.category]}</dd>`);
  if (space.capacity) facts.push(`<dt>Capacity</dt><dd>${space.capacity}</dd>`);
  if (space.tags?.length) {
    facts.push(`<dt>Tags</dt><dd>${space.tags.map((t) => `<span class="tag">${esc(t)}</span>`).join(' ')}</dd>`);
  }
  return `
    <div class="panel__eyebrow">${esc(space.id.toUpperCase())}</div>
    <h2 class="panel__title">${esc(space.name)}</h2>
    ${space.description ? `<p class="panel__desc">${esc(space.description)}</p>` : ''}
    <dl class="facts">${facts.join('')}</dl>
    <button type="button" class="btn" data-action="clear">Back to floor</button>
  `;
}

function floorSummary(building: Building, floorId: string, categories: Set<string>): string {
  const floor = building.floors.find((f) => f.id === floorId)!;
  const spaces = building.spaces.filter(
    (s) => s.floorId === floorId && s.category !== 'circulation' && (categories.size === 0 || categories.has(s.category)),
  );
  const items = spaces
    .map(
      (s) =>
        `<li><button type="button" class="list-btn" data-space-id="${esc(s.id)}">
          <span class="swatch swatch--${s.category}"></span>${esc(s.name)}
        </button></li>`,
    )
    .join('');
  return `
    <div class="panel__eyebrow">${esc(building.name)}</div>
    <h2 class="panel__title">Floor ${esc(floor.label)}</h2>
    <p class="panel__desc">${spaces.length} space${spaces.length === 1 ? '' : 's'}${categories.size ? ' matching filters' : ''}. Click a room on the map or in the list.</p>
    <ul class="space-list">${items || '<li class="muted">Nothing matches the current filters.</li>'}</ul>
  `;
}

export function mountPanel(root: HTMLElement, building: Building, store: Store) {
  root.addEventListener('click', (e) => {
    const t = (e.target as HTMLElement).closest<HTMLElement>('[data-space-id],[data-action]');
    if (!t) return;
    if (t.dataset.action === 'clear') store.set({ selectedSpaceId: null });
    else if (t.dataset.spaceId) store.set({ selectedSpaceId: t.dataset.spaceId });
  });

  store.subscribe((s, prev) => {
    const selected = s.selectedSpaceId ? building.spaces.find((sp) => sp.id === s.selectedSpaceId) : null;
    if (selected) {
      if (root.dataset.mode === 'space' && prev.selectedSpaceId === selected.id) return;
      const floor = building.floors.find((f) => f.id === selected.floorId)!;
      root.dataset.mode = 'space';
      root.innerHTML = spaceDetails(selected, floor.label);
      return;
    }
    // Floor summary: only re-render when something it displays has changed
    // (hover updates flow through the store too and must not blow away the list).
    const unchanged =
      root.dataset.mode === 'floor' && prev.floorId === s.floorId && prev.categories === s.categories;
    if (unchanged) return;
    root.dataset.mode = 'floor';
    root.innerHTML = floorSummary(building, s.floorId, s.categories);
  });
}
