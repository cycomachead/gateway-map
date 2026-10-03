import { expect, test } from '@playwright/test';

for (const id of ['0', '1', '2', '3', '4', '5']) {
  test(`floor ${id} can be opened directly and reloaded`, async ({ page }) => {
    // Static hosts may redirect directory paths to a trailing slash.
    await page.goto(`/floor-${id}/`);
    await expect(page).toHaveURL(`/floor-${id}`);
    await page.reload();
    await expect(page.locator('#map [data-floor-id]')).toHaveAttribute('data-floor-id', id);
    await expect(page.locator('#panel h2')).toHaveText(`Floor ${id === '0' ? 'LL' : id}`);
    await expect(page.getByRole('button', { name: id === '0' ? 'LL' : id, exact: true }))
      .toHaveAttribute('aria-pressed', 'true');
  });
}

test('room links restore the details, highlight, and zoom on reload', async ({ page }) => {
  await page.goto('/floor-4');
  const floorView = await page.locator('#map').getAttribute('viewBox');
  await page.locator('#panel [data-space-id="4-4161"]').click();
  await expect(page).toHaveURL('/floor-4?room=4-4161');
  const roomView = await page.locator('#map').getAttribute('viewBox');
  expect(roomView).not.toBe(floorView);

  await page.reload();
  await expect(page.locator('#panel h2')).toHaveText('Small Meeting Room 4161');
  await expect(page.locator('#map [data-space-id="4-4161"]')).toHaveClass(/is-selected/);
  await expect(page.locator('#map')).toHaveAttribute('viewBox', roomView!);

  await page.getByRole('button', { name: 'Fit floor to view' }).click();
  await expect(page).toHaveURL('/floor-4');
  await expect(page.locator('#map')).toHaveAttribute('viewBox', floorView!);
});

test('Back and Forward restore selections without adding history entries', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('button', { name: '4', exact: true }).click();
  await page.locator('#panel [data-space-id="4-4161"]').click();
  // Selecting the same room, hovering, and filtering must not add history entries.
  await page.locator('#map [data-space-id="4-4161"]').focus();
  await page.keyboard.press('Enter');
  await page.locator('#map [data-space-id="4-4161"]').hover();
  await page.getByRole('button', { name: 'Labs', exact: true }).click();
  await page.getByRole('button', { name: '2', exact: true }).click();
  await expect(page).toHaveURL('/floor-2');

  await page.goBack();
  await expect(page).toHaveURL('/floor-4?room=4-4161');
  await expect(page.locator('#panel h2')).toHaveText('Small Meeting Room 4161');
  await expect(page.locator('#map [data-space-id="4-4161"]')).toHaveClass(/is-selected/);
  await page.goBack();
  await expect(page).toHaveURL('/floor-4');
  await expect(page.locator('#panel h2')).toHaveText('Floor 4');
  await page.goBack();
  await expect(page).toHaveURL('/floor-1');
  await expect(page.locator('#panel h2')).toHaveText('Floor 1');
  await page.goForward();
  await page.goForward();
  await expect(page).toHaveURL('/floor-4?room=4-4161');
  await expect(page.locator('#panel h2')).toHaveText('Small Meeting Room 4161');
  await page.goForward();
  await expect(page).toHaveURL('/floor-2');
  await expect(page.locator('#panel h2')).toHaveText('Floor 2');
});

test('invalid routes fall back safely and preserve unrelated query parameters', async ({ page }) => {
  for (const path of ['/floor-999?room=missing', '/floor-unknown?room=%FF']) {
    await page.goto(path);
    await expect(page).toHaveURL('/floor-1');
    await expect(page.locator('#panel h2')).toHaveText('Floor 1');
  }
  for (const room of ['missing', '2-2322', '']) {
    await page.goto(`/floor-4?source=shared&room=${room}`);
    await expect(page).toHaveURL('/floor-4?source=shared');
    await expect(page.locator('#panel h2')).toHaveText('Floor 4');
    await expect(page.locator('#map .is-selected')).toHaveCount(0);
  }
});
