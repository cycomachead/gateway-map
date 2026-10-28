import { getRequireShift, setRequireShift } from '../prefs';
import type { Direction } from '../map/navigate';
import { esc } from './html';
import { openDialog } from './dialog';

export interface ShortcutActions {
  focusSearch(): void;
  zoomIn(): void;
  zoomOut(): void;
  /** `floorId` is the data id ('0' for the Lower Level). */
  goToFloor(floorId: string): void;
  moveFocus(dir: Direction): void;
  /** Clear the selected room; returns false when nothing was selected. */
  clearSelection(): boolean;
  toggleHelp(): void;
}

interface Binding {
  /** How the keys are shown in the help dialog; alternatives are joined with "or" unless `sep` says otherwise. */
  show: string[];
  sep?: string;
  action: string;
  /** A single letter: honours the "require Shift" preference. */
  letter?: boolean;
}

interface Group {
  title: string;
  bindings: Binding[];
}

const isMac = /Mac|iPhone|iPad/.test(navigator.platform);
const MOD = isMac ? '⌘' : 'Ctrl';

const GROUPS: Group[] = [
  {
    title: 'Find',
    bindings: [
      { show: [`${MOD} + /`, `${MOD} + F`], action: 'Search rooms and people' },
      { show: ['?'], action: 'Show these keyboard shortcuts' },
    ],
  },
  {
    title: 'Map',
    bindings: [
      { show: ['+'], action: 'Zoom in' },
      { show: ['−'], action: 'Zoom out' },
      { show: ['↑', '↓', '←', '→'], sep: ' ', action: 'Move to the next room in that direction' },
      { show: ['Enter'], action: 'Open the focused room' },
      { show: ['Esc'], action: 'Back to the floor' },
    ],
  },
  {
    title: 'Floors',
    bindings: [
      { show: ['1', '…', '5'], sep: ' ', action: 'Go to floors 1 to 5' },
      { show: ['B'], letter: true, action: 'Go to the Lower Level' },
    ],
  },
];

/** Single-letter shortcuts, the ones the "require Shift" preference applies to. */
const LETTERS: Record<string, (a: ShortcutActions) => void> = {
  b: (a) => a.goToFloor('0'),
};

const ARROWS: Record<string, Direction> = { ArrowUp: 'up', ArrowDown: 'down', ArrowLeft: 'left', ArrowRight: 'right' };

const NON_TEXT_INPUTS = new Set(['checkbox', 'radio', 'button', 'submit', 'reset', 'range', 'color', 'file']);

/** Where plain keys mean typing, not shortcuts. */
function isEditable(el: Element | null): boolean {
  if (!el) return false;
  if (el instanceof HTMLInputElement) return !NON_TEXT_INPUTS.has(el.type);
  if (el instanceof HTMLTextAreaElement || el instanceof HTMLSelectElement) return true;
  return el instanceof HTMLElement && el.isContentEditable;
}

/**
 * The page-wide keyboard shortcuts. Only the search shortcuts work while typing in a field;
 * nothing fires while a dialog is open (the dialog owns Escape and Tab), and arrow keys are
 * left alone inside the side panel, which scrolls with them.
 */
export function mountShortcuts(actions: ShortcutActions) {
  document.addEventListener('keydown', (e) => {
    if (e.defaultPrevented || e.isComposing) return;
    const target = e.target as Element | null;
    const key = e.key.length === 1 ? e.key.toLowerCase() : e.key;

    if ((e.ctrlKey || e.metaKey) && !e.altKey && !e.shiftKey) {
      if (key === '/' || key === 'f') {
        e.preventDefault();
        actions.focusSearch();
      }
      return;
    }
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    if (isEditable(target)) return;

    if (key === '?') {
      e.preventDefault();
      actions.toggleHelp();
      return;
    }
    if (document.querySelector('dialog[open]')) return;

    if (key in ARROWS) {
      if (target?.closest('#panel')) return;
      e.preventDefault();
      actions.moveFocus(ARROWS[key]);
      return;
    }
    if (key === 'Escape') {
      if (actions.clearSelection()) e.preventDefault();
      return;
    }
    if (key === '+' || key === '=') {
      e.preventDefault();
      actions.zoomIn();
      return;
    }
    if (key === '-' || key === '_') {
      e.preventDefault();
      actions.zoomOut();
      return;
    }
    if (/^[0-5]$/.test(key)) {
      e.preventDefault();
      actions.goToFloor(key);
      return;
    }
    if (key in LETTERS) {
      if (getRequireShift() && !e.shiftKey) return;
      e.preventDefault();
      LETTERS[key](actions);
    }
  });
}

const kbd = (k: string) => `<kbd>${esc(k)}</kbd>`;
const keysHtml = (b: Binding) => {
  const shown = b.letter && getRequireShift() ? b.show.map((k) => `Shift + ${k}`) : b.show;
  const joiner = b.sep ?? ' <span class="muted-inline">or</span> ';
  return shown.map((k) => k.split(' + ').map(kbd).join('<span class="kbd-plus">+</span>')).join(joiner);
};

/** Fill the "Keyboard shortcuts" dialog and wire its preference; call once at start-up. */
export function mountShortcutsDialog(dialog: HTMLDialogElement) {
  const render = () => {
    dialog.innerHTML = `
      <h2 id="shortcuts-title" class="dialog__title">Keyboard shortcuts</h2>
      ${GROUPS.map(
        (g) => `
        <h3 class="dialog__group">${esc(g.title)}</h3>
        <dl class="shortcuts">
          ${g.bindings.map((b) => `<dt>${keysHtml(b)}</dt><dd>${esc(b.action)}</dd>`).join('')}
        </dl>`,
      ).join('')}
      <div class="pref">
        <label class="pref__label">
          <input type="checkbox" id="pref-require-shift" ${getRequireShift() ? 'checked' : ''} />
          Require <kbd>Shift</kbd> for single-letter shortcuts
        </label>
        <p class="dialog__hint" id="pref-require-shift-hint">
          Turn this on if your screen reader or browser already uses single letters to move around the
          page: B alone then does nothing, and Shift + B goes to the Lower Level. Saved in this browser.
        </p>
      </div>
      <div class="dialog__actions">
        <button type="button" class="btn" data-close>Close</button>
      </div>
    `;
    const box = dialog.querySelector<HTMLInputElement>('#pref-require-shift')!;
    box.setAttribute('aria-describedby', 'pref-require-shift-hint');
    box.addEventListener('change', () => {
      setRequireShift(box.checked);
      // Re-draw the key list to show the new combination, keeping focus on the checkbox.
      render();
      dialog.querySelector<HTMLInputElement>('#pref-require-shift')!.focus();
    });
  };
  render();
  return {
    toggle() {
      if (dialog.open) dialog.close();
      else openDialog(dialog);
    },
  };
}
