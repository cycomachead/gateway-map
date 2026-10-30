import type { Building } from '../data/types';
import type { Store } from '../state';
import { spaceIdFromEvent } from '../map/render';
import { announce } from './announce';

/** One note for the people maintaining the map: a room or a point on a floor, and what should change. */
export interface Correction {
  id: string;
  floorId: string;
  spaceId?: string;
  /** Map (frame) coordinates of a marked point. */
  at?: { x: number; y: number };
  /** A name or occupant the correction is about. */
  name: string;
  text: string;
}

type Mode = 'room' | 'point' | null;
const KEY = 'gateway-map:corrections';
const SVG_NS = 'http://www.w3.org/2000/svg';

function load(): Correction[] {
  try {
    const raw = localStorage.getItem(KEY);
    const list = raw ? (JSON.parse(raw) as Correction[]) : [];
    return Array.isArray(list) ? list.filter((c) => c && typeof c.id === 'string') : [];
  } catch {
    return [];
  }
}

function save(list: Correction[]) {
  try {
    localStorage.setItem(KEY, JSON.stringify(list));
  } catch {
    /* private window or storage blocked: the list lives for the session only */
  }
}

const esc = (s: string) => s.replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]!);

/**
 * The corrections panel: pick rooms or mark points on the map, write what should change, and
 * copy the list as text to paste into an issue or hand to an LLM. Kept in localStorage.
 */
export function mountCorrections(
  root: HTMLElement,
  opts: { button: HTMLButtonElement; store: Store; building: Building; svg: SVGSVGElement; floorLabel: (id: string) => string },
) {
  const { button, store, building, svg, floorLabel } = opts;
  let entries = load();
  let open = false;
  let mode: Mode = null;
  let focusId: string | null = null;

  const space = (id: string) => building.spaces.find((s) => s.id === id);
  const where = (c: Correction) => {
    if (c.spaceId) {
      const s = space(c.spaceId);
      return s ? `${s.name} (${s.id})` : c.spaceId;
    }
    return c.at ? `point (${c.at.x}, ${c.at.y})` : 'floor';
  };

  /** The list as text: one line per correction, floor first, coordinates in map units. */
  function asText(): string {
    const lines = entries.map((c) => {
      const parts = [`Floor ${floorLabel(c.floorId)} · ${where(c)}`];
      if (c.name.trim()) parts.push(`name/occupant: ${c.name.trim()}`);
      parts.push(c.text.trim() || '(no note)');
      return `- ${parts.join(' · ')}`;
    });
    return [`Gateway map corrections (${entries.length})`, ...lines].join('\n');
  }

  function setMode(next: Mode) {
    mode = mode === next ? null : next;
    svg.classList.toggle('is-picking', mode !== null);
    render();
    announce(mode === 'room' ? 'Click a room on the map to add a correction' : mode === 'point' ? 'Click the map to mark a point' : 'Picking off');
  }

  function add(c: Omit<Correction, 'id' | 'name' | 'text'>) {
    const entry: Correction = { id: `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`, name: '', text: '', ...c };
    entries = [...entries, entry];
    focusId = entry.id;
    save(entries);
    render();
    drawMarks();
  }

  function render() {
    root.hidden = !open;
    button.setAttribute('aria-pressed', String(open));
    if (!open) return;
    const items = entries
      .map(
        (c) => `
      <li class="correction" data-id="${esc(c.id)}">
        <div class="correction__where">Floor ${esc(floorLabel(c.floorId))} · ${esc(where(c))}
          <button type="button" class="correction__remove" data-remove aria-label="Remove this correction">×</button></div>
        <input class="correction__name" data-field="name" placeholder="Name / occupant (optional)" value="${esc(c.name)}" />
        <textarea class="correction__text" data-field="text" rows="2" placeholder="What should change?">${esc(c.text)}</textarea>
      </li>`,
      )
      .join('');
    root.innerHTML = `
      <div class="corrections__head">
        <h2 class="corrections__title">Corrections</h2>
        <button type="button" class="ctl ctl--round" data-close aria-label="Close corrections">×</button>
      </div>
      <div class="corrections__tools">
        <button type="button" class="btn" data-mode="room" aria-pressed="${mode === 'room'}">Pick a room</button>
        <button type="button" class="btn" data-mode="point" aria-pressed="${mode === 'point'}" title="Mark a point on the map">✎ Mark a point</button>
      </div>
      <p class="corrections__hint">${
        mode === 'room' ? 'Click a room on the map.' : mode === 'point' ? 'Click the map where something is.' : 'Pick rooms or mark points, write what should change, then copy the list.'
      }</p>
      <ol class="corrections__list">${items || '<li class="corrections__empty">Nothing yet.</li>'}</ol>
      <div class="corrections__tools">
        <button type="button" class="btn" data-copy ${entries.length ? '' : 'disabled'}>Copy all</button>
        <button type="button" class="btn" data-clear ${entries.length ? '' : 'disabled'}>Clear</button>
      </div>
      <textarea class="corrections__out" readonly rows="4" aria-label="Corrections as text" hidden></textarea>`;
    if (focusId) {
      root.querySelector<HTMLTextAreaElement>(`[data-id="${CSS.escape(focusId)}"] textarea`)?.focus();
      focusId = null;
    }
  }

  root.addEventListener('click', (e) => {
    const t = e.target as HTMLElement;
    const modeBtn = t.closest<HTMLButtonElement>('[data-mode]');
    if (modeBtn) return setMode(modeBtn.dataset.mode as Mode);
    if (t.closest('[data-close]')) return toggle(false);
    if (t.closest('[data-remove]')) {
      const id = t.closest<HTMLElement>('[data-id]')!.dataset.id!;
      entries = entries.filter((c) => c.id !== id);
      save(entries);
      render();
      drawMarks();
      return;
    }
    if (t.closest('[data-clear]')) {
      entries = [];
      save(entries);
      render();
      drawMarks();
      return;
    }
    if (t.closest('[data-copy]')) {
      const text = asText();
      const out = root.querySelector<HTMLTextAreaElement>('.corrections__out')!;
      out.hidden = false;
      out.value = text;
      out.select();
      navigator.clipboard?.writeText(text).then(
        () => announce(`Copied ${entries.length} corrections`),
        () => announce('Select the text below and copy it'),
      );
    }
  });
  root.addEventListener('input', (e) => {
    const t = e.target as HTMLInputElement | HTMLTextAreaElement;
    const field = t.dataset.field as 'name' | 'text' | undefined;
    const id = t.closest<HTMLElement>('[data-id]')?.dataset.id;
    if (!field || !id) return;
    entries = entries.map((c) => (c.id === id ? { ...c, [field]: t.value } : c));
    save(entries);
  });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && mode) setMode(mode);
  });

  function toggle(next = !open) {
    open = next;
    if (!open && mode) setMode(mode);
    render();
  }
  button.addEventListener('click', () => toggle());

  /** Marks for the points of the current floor, drawn over the map; called after each floor is mounted. */
  function drawMarks() {
    svg.querySelector('.marks')?.remove();
    const floorId = store.get().floorId;
    const marked = entries.filter((c) => c.at && c.floorId === floorId);
    if (!marked.length) return;
    const g = document.createElementNS(SVG_NS, 'g');
    g.setAttribute('class', 'marks');
    g.setAttribute('aria-hidden', 'true');
    marked.forEach((c, i) => {
      const dot = document.createElementNS(SVG_NS, 'circle');
      dot.setAttribute('cx', String(c.at!.x));
      dot.setAttribute('cy', String(c.at!.y));
      dot.setAttribute('r', '9');
      dot.setAttribute('class', 'mark__dot');
      const n = document.createElementNS(SVG_NS, 'text');
      n.setAttribute('x', String(c.at!.x));
      n.setAttribute('y', String(c.at!.y));
      n.setAttribute('class', 'mark__n');
      n.setAttribute('text-anchor', 'middle');
      n.setAttribute('dominant-baseline', 'central');
      n.textContent = String(i + 1);
      g.append(dot, n);
    });
    svg.appendChild(g);
  }

  /** A click on the map while picking: adds a correction and reports that the click is taken. */
  function handleMapClick(e: MouseEvent): boolean {
    if (!mode) return false;
    const floorId = store.get().floorId;
    if (mode === 'room') {
      const id = spaceIdFromEvent(e);
      if (!id) return true;
      add({ floorId, spaceId: id });
      return true;
    }
    const pt = svg.createSVGPoint();
    pt.x = e.clientX;
    pt.y = e.clientY;
    const ctm = svg.getScreenCTM();
    if (!ctm) return true;
    const p = pt.matrixTransform(ctm.inverse());
    add({ floorId, at: { x: Math.round(p.x * 10) / 10, y: Math.round(p.y * 10) / 10 } });
    return true;
  }

  render();
  return { handleMapClick, drawMarks, isPicking: () => mode !== null };
}
