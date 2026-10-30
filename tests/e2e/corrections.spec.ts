import { expect, test } from '@playwright/test';

test('corrections: pick a room, mark a point, copy the list, keep it across reloads', async ({ page }) => {
  await page.goto('/floor-4');
  await page.getByRole('button', { name: 'Corrections' }).click();
  const panel = page.locator('#corrections');
  await expect(panel).toBeVisible();

  // A room picked while picking does not become the selection; it becomes an entry.
  await panel.getByRole('button', { name: 'Pick a room' }).click();
  await page.locator('#map [data-space-id="4-4161"]').click();
  await expect(page).toHaveURL('/floor-4');
  const entry = panel.locator('.correction').first();
  await expect(entry).toContainText('Small Meeting Room 4161 (4-4161)');
  await entry.locator('textarea').fill('should be a box');
  await entry.locator('input').fill('Jane Doe');

  // A marked point gets a numbered mark on the map and map coordinates in the list.
  await panel.getByRole('button', { name: 'Mark a point' }).click();
  const box = (await page.locator('#map').boundingBox())!;
  await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2);
  await expect(panel.locator('.correction')).toHaveCount(2);
  await expect(panel.locator('.correction').nth(1)).toContainText('point (');
  await expect(page.locator('#map .marks .mark__dot')).toHaveCount(1);
  await page.keyboard.press('Escape');

  await panel.getByRole('button', { name: 'Copy all' }).click();
  const out = panel.locator('.corrections__out');
  await expect(out).toBeVisible();
  await expect(out).toHaveValue(/Gateway map corrections \(2\)/);
  await expect(out).toHaveValue(/Floor 4 · Small Meeting Room 4161 \(4-4161\) · name\/occupant: Jane Doe · should be a box/);
  await expect(out).toHaveValue(/Floor 4 · point \(/);

  // The list is kept in the browser.
  await page.reload();
  await page.getByRole('button', { name: 'Corrections' }).click();
  await expect(page.locator('#corrections .correction')).toHaveCount(2);
  await expect(page.locator('#map .marks .mark__dot')).toHaveCount(1);
  await page.locator('#corrections').getByRole('button', { name: 'Clear' }).click();
  await expect(page.locator('#corrections .correction')).toHaveCount(0);
});
