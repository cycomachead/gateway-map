import { expect, test } from '@playwright/test';

test.beforeEach(async ({ page }) => {
  await page.goto('/');
  await page.waitForSelector('#map [data-space-id]');
});

test('the room list hides unnumbered rooms and can show every floor at once', async ({ page }) => {
  // Floor 1's plan numbers only some rooms; the rest are drawn but not listed.
  expect(await page.locator('#map [data-space-id^="1-room-"]').count()).toBeGreaterThan(5);
  await expect(page.locator('#panel .list-btn', { hasText: /^Room$/ })).toHaveCount(0);
  const onOneFloor = await page.locator('#panel .list-btn').count();

  const toggle = page.getByRole('button', { name: 'All floors' });
  await expect(toggle).toHaveAttribute('aria-pressed', 'false');
  await toggle.click();
  await expect(toggle).toHaveAttribute('aria-pressed', 'true');
  await expect(page.locator('#panel h2')).toHaveText('All floors');
  await expect(page.locator('#panel .space-list__heading')).toHaveText(['Floor 5', 'Floor 4', 'Floor 3', 'Floor 2', 'Floor 1', 'Floor LL']);
  expect(await page.locator('#panel .list-btn').count()).toBeGreaterThan(3 * onOneFloor);
  await expect(page.locator('#panel .list-btn', { hasText: /^Room$/ })).toHaveCount(0);

  // A room on another floor opens that floor.
  await page.locator('#panel [data-space-id="4-4161"]').click();
  await expect(page).toHaveURL('/floor-4?room=4-4161');
  await expect(page.locator('#map [data-floor-id]')).toHaveAttribute('data-floor-id', '4');
  await page.getByRole('button', { name: 'Back to floor' }).click();
  await expect(page.locator('#panel h2')).toHaveText('All floors');
  await expect(page.locator('#panel .space-list__floor.is-current .space-list__heading')).toHaveText('Floor 4');

  await page.getByRole('button', { name: 'All floors' }).click();
  await expect(page.locator('#panel h2')).toHaveText('Floor 4');
});

test('offices are plain offices, and 1110 is a four-walled meeting room', async ({ page }) => {
  await page.getByRole('button', { name: '4', exact: true }).click();
  await page.locator('#map [data-space-id="4-4123"] .space__shape').click();
  await expect(page.locator('#panel h2')).toHaveText('Office 4123');
  await expect(page.locator('#panel .list-btn, #panel h2', { hasText: 'Faculty Office' })).toHaveCount(0);

  await page.getByRole('button', { name: '1', exact: true }).click();
  const room = page.locator('#map [data-space-id="1-1110"]');
  await expect(room).toHaveClass(/space--meeting/);
  const d = (await room.locator('.space__shape').getAttribute('d')) ?? '';
  expect(d.match(/[ML]/g)?.length).toBe(4);
  await room.locator('.space__shape').click();
  await expect(page.locator('#panel h2')).toHaveText('Meeting Room 1110');
});

test('restrooms are named and carry an icon on every floor', async ({ page }) => {
  for (const floor of ['2', '3', '4']) {
    await page.getByRole('button', { name: floor, exact: true }).click();
    const men = page.locator(`#map [data-space-id="${floor}-ne-restroom"]`);
    await expect(men.locator('.space__label')).toHaveText("Men's Restroom");
    await expect(men.locator('.space__icon')).toHaveCount(1);
    const women = page.locator(`#map [data-space-id="${floor}-sw-restroom"]`);
    await expect(women.locator('.space__label')).toHaveText("Women's Restroom");
    await expect(women.locator('.space__icon')).toHaveCount(1);
    // The men's and women's pictograms differ.
    expect(await men.locator('.space__icon').getAttribute('d')).not.toBe(await women.locator('.space__icon').getAttribute('d'));
    for (const id of ['ne-restroom-2', 'sw-restroom-2']) {
      const small = page.locator(`#map [data-space-id="${floor}-${id}"]`);
      await expect(small).toHaveAttribute('aria-label', 'Gender Neutral Restroom');
      await expect(small.locator('.space__icon')).toHaveCount(1);
      await expect(small.locator('.space__label-name')).toHaveText(['Gender', 'Neutral']);
    }
  }
  await page.getByRole('button', { name: '1', exact: true }).click();
  await expect(page.locator('#map [data-space-id="1-ne-restroom"]')).toHaveAttribute('aria-label', "Men's Restroom");
  await expect(page.locator('#map [data-space-id="1-sw-restroom"]')).toHaveAttribute('aria-label', "Women's Restroom");

  await page.getByRole('button', { name: '5', exact: true }).click();
  await expect(page.locator('#map [data-space-id="5-men-restroom"]')).toHaveAttribute('aria-label', "Men's Restroom");
  await expect(page.locator('#map [data-space-id="5-women-restroom"]')).toHaveAttribute('aria-label', "Women's Restroom");
  await expect(page.locator('#map [data-space-id^="5-single-restroom-"]')).toHaveCount(2);

  await page.getByRole('button', { name: 'LL', exact: true }).click();
  await page.locator('#map [data-space-id="0-b1309"] .space__shape').click();
  await expect(page.locator('#panel h2')).toHaveText('Gender Inclusive Restroom B1309');
  // The stalls once drawn as a separate "Restrooms (SW)" sliver are part of B1309 now.
  await expect(page.locator('#map [data-space-id="0-sw-restrooms"]')).toHaveCount(0);
});

test('the Info button opens INFO.md rendered as a dialog', async ({ page }) => {
  const info = page.getByRole('dialog', { name: 'Gateway Building Info' });
  await expect(info).toBeHidden();
  await page.getByRole('button', { name: 'Info', exact: true }).click();
  await expect(info).toBeVisible();
  await expect(info.getByRole('heading', { level: 3 })).toHaveText(['Room Numbers', 'Site Features']);
  await expect(info).toContainText('Northeast side of the building');
  await expect(info.locator('kbd', { hasText: '?' })).toBeVisible();
  await expect(info.locator('li')).toHaveCount(6);
  await info.getByRole('button', { name: 'Close' }).click();
  await expect(info).toBeHidden();
  await expect(page.getByRole('button', { name: 'Info', exact: true })).toBeFocused();
});

test('the fare gates in front of the Northeast elevators are a named room on Floor 1', async ({ page }) => {
  await page.locator('#map [data-space-id="1-fare-gates"] .space__shape').click();
  await expect(page.locator('#panel h2')).toHaveText('🚨 Fare Gates (Turnstiles)');
  await expect(page).toHaveURL('/floor-1?room=1-fare-gates');
  await expect(page.locator('#map [data-space-id="1-fare-gates"] .space__label')).toContainText('Fare Gates');
});
