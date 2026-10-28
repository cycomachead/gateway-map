import { expect, test, type Page } from '@playwright/test';

test.beforeEach(async ({ page }) => {
  await page.goto('/');
  await page.waitForSelector('#map [data-space-id]');
});

const centre = async (page: Page, id: string) => {
  const box = (await page.locator(`#map [data-space-id="${id}"] .space__shape`).boundingBox())!;
  return { x: box.x + box.width / 2, y: box.y + box.height / 2 };
};

test('the About dialog credits the author and the language models', async ({ page }) => {
  const about = page.getByRole('dialog', { name: 'About Gateway Map' });
  await expect(about).toBeHidden();
  await page.getByRole('button', { name: 'About' }).click();
  await expect(about).toBeVisible();
  await expect(about).toContainText('Michael Ball');
  await expect(about).toContainText('a healthy dose of large language models');
  await expect(about.getByRole('link', { name: /GitHub/ })).toHaveAttribute('href', 'https://github.com/cycomachead/gateway-map');

  await about.getByRole('button', { name: 'Close' }).click();
  await expect(about).toBeHidden();
  // Focus returns to the control that opened the dialog.
  await expect(page.getByRole('button', { name: 'About' })).toBeFocused();

  await page.getByRole('button', { name: 'About' }).click();
  await about.getByRole('button', { name: 'Keyboard shortcuts' }).click();
  await expect(about).toBeHidden();
  await expect(page.getByRole('dialog', { name: 'Keyboard shortcuts' })).toBeVisible();
});

test('? and the ? button open the shortcuts dialog, Escape closes it and restores focus', async ({ page }) => {
  const help = page.getByRole('dialog', { name: 'Keyboard shortcuts' });
  await expect(help).toBeHidden();

  await page.locator('#map [data-space-id="1-1171"]').focus();
  await page.keyboard.press('?');
  await expect(help).toBeVisible();
  await expect(help).toBeFocused();
  await expect(help).toContainText('Zoom in');
  await expect(help).toContainText('Go to the Lower Level');
  await expect(help.locator('kbd')).toContainText(['Ctrl', '/']);
  // Shortcuts are off while the dialog is open: pressing 4 must not change floors.
  await page.keyboard.press('4');
  await expect(page.locator('#map [data-floor-id]')).toHaveAttribute('data-floor-id', '1');

  await page.keyboard.press('Escape');
  await expect(help).toBeHidden();
  await expect(page.locator('#map [data-space-id="1-1171"]')).toBeFocused();

  await page.getByRole('button', { name: 'Keyboard shortcuts' }).click();
  await expect(help).toBeVisible();
  await page.keyboard.press('?'); // toggles
  await expect(help).toBeHidden();
});

test('Ctrl+/ and Ctrl+F jump to the search box', async ({ page }) => {
  const input = page.getByRole('searchbox', { name: 'Search spaces' });
  await expect(input).not.toBeFocused();
  await page.keyboard.press('Control+/');
  await expect(input).toBeFocused();

  await input.fill('4161');
  await page.locator('#map [data-space-id="1-1171"]').focus();
  await page.keyboard.press('Control+f');
  await expect(input).toBeFocused();
  // The existing text is selected, ready to be replaced.
  expect(await input.evaluate((el: HTMLInputElement) => el.value.slice(el.selectionStart!, el.selectionEnd!))).toBe('4161');
});

test('+ and - zoom the map and announce the zoom level', async ({ page }) => {
  const map = page.locator('#map');
  const announcer = page.locator('#announcer');
  const start = (await map.getAttribute('viewBox'))!;
  await page.keyboard.press('+');
  const zoomed = (await map.getAttribute('viewBox'))!;
  expect(zoomed).not.toBe(start);
  expect(Number(zoomed.split(' ')[2])).toBeLessThan(Number(start.split(' ')[2]));
  await expect(announcer).toHaveText('Zoom 140%');

  await page.keyboard.press('-');
  await expect(announcer).toHaveText('Zoom 100%');
  const back = (await map.getAttribute('viewBox'))!.split(' ').map(Number);
  start.split(' ').map(Number).forEach((v, i) => expect(back[i]).toBeCloseTo(v, 6));
  await page.keyboard.press('=');
  await expect(announcer).toHaveText('Zoom 140%');
});

test('digits and B switch floors and move focus to the floor button', async ({ page }) => {
  await page.keyboard.press('4');
  await expect(page.locator('#map [data-floor-id]')).toHaveAttribute('data-floor-id', '4');
  await expect(page).toHaveURL('/floor-4');
  await expect(page.getByRole('button', { name: '4', exact: true })).toBeFocused();
  await expect(page.getByRole('button', { name: '4', exact: true })).toHaveAttribute('aria-pressed', 'true');

  await page.keyboard.press('b');
  await expect(page.locator('#map [data-floor-id]')).toHaveAttribute('data-floor-id', '0');
  await expect(page.getByRole('button', { name: 'LL', exact: true })).toBeFocused();

  await page.keyboard.press('Shift+B');
  await expect(page.locator('#map [data-floor-id]')).toHaveAttribute('data-floor-id', '0');
  await page.keyboard.press('2');
  await expect(page.locator('#panel h2')).toHaveText('Floor 2');

  // A selected room is cleared by a floor change, like clicking the floor button.
  await page.locator('[data-space-id="2-2322"] .space__shape').click();
  await expect(page).toHaveURL('/floor-2?room=2-2322');
  await page.keyboard.press('3');
  await expect(page).toHaveURL('/floor-3');
});

test('typing in the search box never triggers shortcuts', async ({ page }) => {
  const input = page.getByRole('searchbox', { name: 'Search spaces' });
  await input.focus();
  await page.keyboard.type('4b+-?');
  await expect(input).toHaveValue('4b+-?');
  await expect(page.locator('#map [data-floor-id]')).toHaveAttribute('data-floor-id', '1');
  await expect(page.getByRole('dialog', { name: 'Keyboard shortcuts' })).toBeHidden();
});

test('arrow keys walk between neighbouring rooms, panning to keep them in view', async ({ page }) => {
  await page.goto('/floor-4?room=4-4161');
  await page.waitForSelector('#map [data-floor-id="4"]');
  const from = await centre(page, '4-4161');

  await page.keyboard.press('ArrowRight');
  const focused = page.locator('#map [data-space-id]:focus');
  await expect(focused).toHaveCount(1);
  const rightId = (await focused.getAttribute('data-space-id'))!;
  expect(rightId).not.toBe('4-4161');
  expect((await centre(page, rightId)).x).toBeGreaterThan(from.x);
  // Only rooms: corridors are never a stop.
  await expect(focused).not.toHaveClass(/space--circulation/);

  await page.keyboard.press('ArrowLeft');
  await expect(page.locator('#map [data-space-id="4-4161"]')).toBeFocused();

  // Enter opens the focused room, as it does when tabbing.
  await page.keyboard.press('ArrowDown');
  const belowId = (await focused.getAttribute('data-space-id'))!;
  expect((await centre(page, belowId)).y).toBeGreaterThan(from.y);
  await page.keyboard.press('Enter');
  await expect(page).toHaveURL(`/floor-4?room=${belowId}`);

  // Keep going in one direction and the view follows the focused room.
  const map = page.locator('#map');
  const viewBefore = (await map.getAttribute('viewBox'))!;
  for (let i = 0; i < 6; i++) await page.keyboard.press('ArrowDown');
  const id = (await focused.getAttribute('data-space-id'))!;
  const box = (await page.locator(`#map [data-space-id="${id}"] .space__shape`).boundingBox())!;
  const stage = (await map.boundingBox())!;
  expect(box.x + box.width / 2).toBeGreaterThan(stage.x);
  expect(box.x + box.width / 2).toBeLessThan(stage.x + stage.width);
  expect(box.y + box.height / 2).toBeGreaterThan(stage.y);
  expect(box.y + box.height / 2).toBeLessThan(stage.y + stage.height);
  expect(await map.getAttribute('viewBox')).not.toBe(viewBefore);

  // At the edge of the floor the position is announced instead of moving.
  for (let i = 0; i < 30; i++) await page.keyboard.press('ArrowDown');
  await expect(page.locator('#announcer')).toContainText('No rooms further down');
});

test('arrow keys start from the middle of the view and skip filtered-out rooms', async ({ page }) => {
  await page.keyboard.press('4');
  await page.getByRole('button', { name: 'Labs' }).click();
  await page.keyboard.press('ArrowUp');
  const focused = page.locator('#map [data-space-id]:focus');
  await expect(focused).toHaveCount(1);
  await expect(focused).toHaveClass(/space--lab/);
  for (let i = 0; i < 4; i++) {
    await page.keyboard.press('ArrowLeft');
    await expect(focused).toHaveClass(/space--lab/);
  }
});

test('Escape goes back to the floor and puts focus on the room', async ({ page }) => {
  await page.goto('/floor-4?room=4-4161');
  await page.waitForSelector('#map [data-floor-id="4"]');
  await page.getByRole('button', { name: 'Back to floor' }).focus();
  await page.keyboard.press('Escape');
  await expect(page).toHaveURL('/floor-4');
  await expect(page.locator('#panel h2')).toHaveText('Floor 4');
  await expect(page.locator('#map [data-space-id="4-4161"]')).toBeFocused();
});

test('the Shift preference gates single-letter shortcuts and survives a reload', async ({ page }) => {
  await page.keyboard.press('?');
  const help = page.getByRole('dialog', { name: 'Keyboard shortcuts' });
  const pref = help.getByRole('checkbox', { name: /Require Shift/ });
  await expect(pref).not.toBeChecked();
  const lowerLevelKeys = help.locator('.shortcuts dt').filter({ has: page.locator('kbd', { hasText: 'B' }) });
  await expect(lowerLevelKeys).toHaveText('B');
  await pref.check();
  await expect(pref).toBeChecked();
  await expect(pref).toBeFocused();
  await expect(lowerLevelKeys).toHaveText('Shift+B');
  await page.keyboard.press('Escape');

  await page.keyboard.press('b');
  await expect(page.locator('#map [data-floor-id]')).toHaveAttribute('data-floor-id', '1');
  await page.keyboard.press('Shift+B');
  await expect(page.locator('#map [data-floor-id]')).toHaveAttribute('data-floor-id', '0');
  // Digits and symbols are unaffected.
  await page.keyboard.press('3');
  await expect(page.locator('#map [data-floor-id]')).toHaveAttribute('data-floor-id', '3');

  await page.reload();
  await page.waitForSelector('#map [data-space-id]');
  await page.keyboard.press('b');
  await expect(page.locator('#map [data-floor-id]')).toHaveAttribute('data-floor-id', '3');
  await page.keyboard.press('?');
  await expect(help.getByRole('checkbox', { name: /Require Shift/ })).toBeChecked();
  await help.getByRole('checkbox', { name: /Require Shift/ }).uncheck();
  await page.keyboard.press('Escape');
  await page.keyboard.press('b');
  await expect(page.locator('#map [data-floor-id]')).toHaveAttribute('data-floor-id', '0');
});
