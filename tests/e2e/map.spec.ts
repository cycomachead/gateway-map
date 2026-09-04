import { expect, test } from '@playwright/test';

test.beforeEach(async ({ page }) => {
  await page.goto('/');
  await page.waitForSelector('#map [data-space-id]');
});

test('opens on the ground floor and can switch to every level', async ({ page }) => {
  await expect(page.locator('#map [data-floor-id]')).toHaveAttribute('data-floor-id', '1');
  await expect(page.locator('#panel h2')).toHaveText('Floor 1');
  // Level 1's detached Southwest block is a second outline path.
  expect(await page.locator('#map .floor__outline').count()).toBe(2);

  const expected: Record<string, number> = { LL: 10, '1': 50, '2': 150, '3': 150, '4': 150, '5': 25 };
  for (const [label, minRooms] of Object.entries(expected)) {
    await page.getByRole('button', { name: label, exact: true }).click();
    await expect(page.locator('#panel h2')).toHaveText(`Floor ${label}`);
    expect(await page.locator('#map [data-space-id]').count()).toBeGreaterThan(minRooms);
  }
});

test('clicking a room selects it and shows details', async ({ page }) => {
  await page.getByRole('button', { name: '4', exact: true }).click();
  await page.locator('[data-space-id="4-4161"] .space__shape').click();
  await expect(page.locator('#panel h2')).toHaveText('Small Meeting Room 4161');
  await expect(page.locator('#map [data-space-id="4-4161"]')).toHaveClass(/is-selected/);
  await expect(page.locator('#panel .facts')).toContainText('Northeast');

  await page.getByRole('button', { name: 'Back to floor' }).click();
  await expect(page.locator('#panel h2')).toHaveText('Floor 4');
});

test('rooms are addressable by their plan number on every floor', async ({ page }) => {
  await page.getByRole('button', { name: '3', exact: true }).click();
  await page.locator('[data-space-id="3-3161"] .space__shape').click();
  await expect(page.locator('#panel h2')).toHaveText('Small Meeting Room 3161');
  await expect(page.locator('#panel .facts')).toContainText('Northeast');

  await page.getByRole('button', { name: '1', exact: true }).click();
  await page.locator('[data-space-id="1-1210"] .space__shape').click();
  await expect(page.locator('#panel h2')).toHaveText('Lecture Hall 1210');

  await page.getByRole('button', { name: 'LL', exact: true }).click();
  await page.locator('[data-space-id="0-b1342"] .space__shape').click();
  await expect(page.locator('#panel h2')).toHaveText('Shipping & Receiving B1342');
});

test('keyboard users can select a room with Enter', async ({ page }) => {
  await page.getByRole('button', { name: '4', exact: true }).click();
  await page.locator('#map [data-space-id="4-4131"]').focus();
  await page.keyboard.press('Enter');
  await expect(page.locator('#panel h2')).toHaveText('General Research Lab 4131');
});

test('search finds rooms by number and by feature, across floors', async ({ page }) => {
  const input = page.getByRole('searchbox', { name: 'Search spaces' });
  await input.fill('4355');
  await expect(page.locator('.search__hit')).toHaveCount(1);
  await input.press('Enter');
  await expect(page.locator('#panel h2')).toHaveText('Large Meeting Room 4355');
  await expect(page.locator('#map [data-floor-id]')).toHaveAttribute('data-floor-id', '4');

  await input.fill('2322');
  await input.press('Enter');
  await expect(page.locator('#panel h2')).toHaveText('Assembly Lab 2322');
  await expect(page.locator('#map [data-floor-id]')).toHaveAttribute('data-floor-id', '2');

  await input.fill('lactation');
  await expect(page.locator('.search__hit').first()).toContainText('Lactation Room');
});

test('category filters dim non-matching rooms and filter the list', async ({ page }) => {
  await page.getByRole('button', { name: '4', exact: true }).click();
  await page.getByRole('button', { name: 'Labs' }).click();
  await expect(page.locator('#map [data-space-id="4-4161"]')).toHaveClass(/is-dimmed/);
  await expect(page.locator('#map [data-space-id="4-4131"]')).not.toHaveClass(/is-dimmed/);
  await expect(page.locator('#panel .list-btn')).toHaveCount(6);
  await expect(page.locator('#panel .list-btn').first()).toContainText('Lab');
});

test('wheel zoom and drag pan change the view', async ({ page }) => {
  const map = page.locator('#map');
  const before = await map.getAttribute('viewBox');
  const box = (await map.boundingBox())!;
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.wheel(0, -300);
  const zoomed = await map.getAttribute('viewBox');
  expect(zoomed).not.toBe(before);

  await page.mouse.down();
  await page.mouse.move(box.x + box.width / 2 + 120, box.y + box.height / 2 + 40, { steps: 5 });
  await page.mouse.up();
  expect(await map.getAttribute('viewBox')).not.toBe(zoomed);
  // A drag must not select whatever room ends up under the pointer.
  await expect(page.locator('#panel h2')).toHaveText('Floor 1');
});
