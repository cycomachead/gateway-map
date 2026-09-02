import type { Space } from '../data/types';

export interface SearchHit {
  space: Space;
  score: number;
}

/** Cheap ranked search over name, id, tags, and description. */
export function searchSpaces(spaces: Space[], query: string, limit = 8): SearchHit[] {
  const q = query.trim().toLowerCase();
  if (!q) return [];
  const terms = q.split(/\s+/);
  const hits: SearchHit[] = [];

  for (const space of spaces) {
    const name = space.name.toLowerCase();
    const id = space.id.toLowerCase();
    const tags = (space.tags ?? []).map((t) => t.toLowerCase());
    const desc = (space.description ?? '').toLowerCase();

    let score = 0;
    for (const term of terms) {
      if (name === term || id === term) score += 100;
      else if (name.startsWith(term)) score += 40;
      else if (name.includes(term)) score += 25;
      else if (id.includes(term)) score += 20;
      else if (tags.some((t) => t.includes(term))) score += 15;
      else if (desc.includes(term)) score += 5;
      else {
        score = 0;
        break; // every term must match something
      }
    }
    if (score > 0) hits.push({ space, score });
  }

  return hits.sort((a, b) => b.score - a.score || a.space.name.localeCompare(b.space.name)).slice(0, limit);
}

export interface SearchBoxOptions {
  spaces: Space[];
  floorLabel: (floorId: string) => string;
  onPick: (space: Space) => void;
}

export function mountSearchBox(root: HTMLElement, opts: SearchBoxOptions) {
  root.innerHTML = `
    <label class="search">
      <span class="visually-hidden">Search spaces</span>
      <input type="search" class="search__input" placeholder="Search rooms, labs, tags…" autocomplete="off" />
    </label>
    <ul class="search__results" role="listbox" aria-label="Search results" hidden></ul>
  `;
  const input = root.querySelector<HTMLInputElement>('.search__input')!;
  const list = root.querySelector<HTMLUListElement>('.search__results')!;
  let hits: SearchHit[] = [];
  let active = -1;

  const render = () => {
    list.innerHTML = '';
    list.hidden = hits.length === 0;
    hits.forEach((hit, i) => {
      const li = document.createElement('li');
      li.className = 'search__hit' + (i === active ? ' is-active' : '');
      li.setAttribute('role', 'option');
      li.innerHTML = `<span>${hit.space.name}</span><small>Floor ${opts.floorLabel(hit.space.floorId)}</small>`;
      li.addEventListener('mousedown', (e) => {
        e.preventDefault(); // keep focus in the input
        pick(hit.space);
      });
      list.appendChild(li);
    });
  };

  const pick = (space: Space) => {
    opts.onPick(space);
    input.value = space.name;
    hits = [];
    active = -1;
    render();
  };

  input.addEventListener('input', () => {
    hits = searchSpaces(opts.spaces, input.value);
    active = hits.length ? 0 : -1;
    render();
  });
  input.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowDown' && hits.length) {
      active = (active + 1) % hits.length;
      render();
      e.preventDefault();
    } else if (e.key === 'ArrowUp' && hits.length) {
      active = (active - 1 + hits.length) % hits.length;
      render();
      e.preventDefault();
    } else if (e.key === 'Enter' && active >= 0) {
      pick(hits[active].space);
      e.preventDefault();
    } else if (e.key === 'Escape') {
      hits = [];
      render();
    }
  });
  input.addEventListener('blur', () => {
    hits = [];
    render();
  });
}
