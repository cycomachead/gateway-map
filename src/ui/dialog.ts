/** Native <dialog> helpers: modal open with focus on the dialog, close on Escape/backdrop/[data-close]. */

export function openDialog(dialog: HTMLDialogElement) {
  if (dialog.open) return;
  dialog.showModal();
  // Focus the dialog itself so screen readers read it from its title; close() later returns
  // focus to whatever had it before (the room, the search box, the "?" button).
  dialog.focus();
}

export function setupDialog(dialog: HTMLDialogElement) {
  dialog.tabIndex = -1;
  dialog.addEventListener('click', (e) => {
    const t = e.target as HTMLElement;
    if (t.closest('[data-close]')) dialog.close();
    else if (t === dialog) dialog.close(); // the backdrop: clicks on content hit a child
  });
}
