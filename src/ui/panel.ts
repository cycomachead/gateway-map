import { CATEGORY_LABELS, type Building, type Floor, type Space } from '../data/types';
import type { AppState, Store } from '../state';
import { esc } from './html';
import { occupantNames } from './names';

function spaceDetails(space: Space, floorLabel: string): string {
  const facts: string[] = [`<dt>Floor</dt><dd>${esc(floorLabel)}</dd>`];
  if (space.wing) facts.push(`<dt>Wing</dt><dd>${esc(space.wing)}</dd>`);
  facts.push(`<dt>Type</dt><dd>${CATEGORY_LABELS[space.category]}</dd>`);
  if (space.department) facts.push(`<dt>Department</dt><dd class="department">${esc(space.department)}</dd>`);
  if (space.occupants?.length) {
    facts.push(`<dt>${space.occupants.length === 1 ? 'Occupant' : 'Occupants'}</dt><dd class="occupants">${space.occupants.map(esc).join('<br>')}</dd>`);
  }
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

/** Rooms worth listing: not the corridors and cores, and not the plan's unnumbered "Room"s. */
const listable = (s: Space) => s.category !== 'circulation' && s.name !== 'Room';

function listItems(spaces: Space[]): string {
  return spaces
    .map((s) => {
      const sub = [occupantNames(s), s.department].filter(Boolean).join(' · ');
      return `<li><button type="button" class="list-btn" data-space-id="${esc(s.id)}">
          <span class="swatch swatch--${s.category}"></span><span class="list-btn__text">${esc(s.name)}${
            sub ? `<small class="list-btn__who">${esc(sub)}</small>` : ''
          }</span>
        </button></li>`;
    })
    .join('');
}

const allFloorsToggle = (on: boolean) =>
  `<button type="button" class="btn btn--toggle" data-action="all-floors" aria-pressed="${on}">All floors</button>`;

function floorSummary(building: Building, state: AppState): string {
  const { floorId, categories, allFloors } = state;
  const matches = (s: Space) => listable(s) && (categories.size === 0 || categories.has(s.category));
  const filtered = categories.size ? ' matching filters' : '';
  const empty = '<li class="muted">Nothing matches the current filters.</li>';
  if (allFloors) {
    const floors = [...building.floors].sort((a, b) => b.level - a.level);
    const groups = floors.map((f: Floor) => {
      const spaces = building.spaces.filter((s) => s.floorId === f.id && matches(s));
      return { floor: f, spaces };
    });
    const total = groups.reduce((n, g) => n + g.spaces.length, 0);
    const sections = groups
      .filter((g) => g.spaces.length)
      .map(
        (g) => `<li class="space-list__floor${g.floor.id === floorId ? ' is-current' : ''}">
          <h3 class="space-list__heading">Floor ${esc(g.floor.label)}</h3>
          <ul class="space-list">${listItems(g.spaces)}</ul>
        </li>`,
      )
      .join('');
    return `
      <div class="panel__eyebrow">${esc(building.name)}</div>
      <div class="panel__head"><h2 class="panel__title">All floors</h2>${allFloorsToggle(true)}</div>
      <p class="panel__desc">${total} space${total === 1 ? '' : 's'}${filtered} on ${floors.length} floors. Click a room to open its floor.</p>
      <ul class="space-list space-list--floors">${sections || empty}</ul>
    `;
  }
  const floor = building.floors.find((f) => f.id === floorId)!;
  const spaces = building.spaces.filter((s) => s.floorId === floorId && matches(s));
  return `
    <div class="panel__eyebrow">${esc(building.name)}</div>
    <div class="panel__head"><h2 class="panel__title">Floor ${esc(floor.label)}</h2>${allFloorsToggle(false)}</div>
    <p class="panel__desc">${spaces.length} space${spaces.length === 1 ? '' : 's'}${filtered}. Click a room on the map or in the list.</p>
    <ul class="space-list">${listItems(spaces) || empty}</ul>
  `;
}

export function mountPanel(root: HTMLElement, building: Building, store: Store) {
  root.addEventListener('click', (e) => {
    const t = (e.target as HTMLElement).closest<HTMLElement>('[data-space-id],[data-action]');
    if (!t) return;
    if (t.dataset.action === 'clear') store.set({ selectedSpaceId: null });
    else if (t.dataset.action === 'all-floors') store.set({ allFloors: !store.get().allFloors });
    else if (t.dataset.spaceId) {
      const space = building.spaces.find((s) => s.id === t.dataset.spaceId);
      if (space) store.set({ floorId: space.floorId, selectedSpaceId: space.id });
    }
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
      root.dataset.mode === 'floor' &&
      prev.floorId === s.floorId &&
      prev.categories === s.categories &&
      prev.allFloors === s.allFloors;
    if (unchanged) return;
    root.dataset.mode = 'floor';
    root.innerHTML = floorSummary(building, s);
  });
}
