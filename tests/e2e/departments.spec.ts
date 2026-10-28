import { expect, test } from '@playwright/test';
import { DEPARTMENTS, RESERVABLE } from '../../src/data/gateway/departments';

// Departments come from the colour space-assignment sheets via
// tools/departments/import_departments.py; the tests follow whatever that file holds.
const [spaceId, department] = Object.entries(DEPARTMENTS)[0] ?? ['', ''];
const floor = spaceId.split('-')[0];

test.describe('departments', () => {
  test.skip(!spaceId, 'no departments are listed in src/data/gateway/departments.ts');

  test('a room shows its department in the details, the list and search', async ({ page }) => {
    await page.goto(`/floor-${floor}?room=${spaceId}`);
    await page.waitForSelector('#map [data-space-id]');
    await expect(page.locator('#panel .facts')).toContainText(department);
    await expect(page.locator('#panel .department')).toHaveText(department);

    await page.getByRole('button', { name: 'Back to floor' }).click();
    await expect(page.locator(`#panel [data-space-id="${spaceId}"] .list-btn__who`)).toContainText(department);

    const input = page.getByRole('searchbox', { name: 'Search spaces' });
    await input.fill(department.split(/\s+/)[0]);
    await expect(page.locator('.search__hit').first().locator('.search__who')).toContainText(department);
  });
});

test('the reservable meeting rooms of Level 1 are tagged', async ({ page }) => {
  test.skip(!RESERVABLE.length, 'no reservable rooms are listed');
  await page.goto(`/floor-1?room=${RESERVABLE[0]}`);
  await page.waitForSelector('#map [data-space-id]');
  await expect(page.locator('#panel .facts .tag', { hasText: 'reservable' })).toHaveCount(1);
});

test('every department entry is on the map', async ({ page }) => {
  const errors: string[] = [];
  page.on('console', (msg) => {
    if (msg.type() === 'error') errors.push(msg.text());
  });
  await page.goto('/');
  await page.waitForSelector('#map [data-space-id]');
  expect(errors.filter((w) => w.includes('Department listed'))).toEqual([]);
});
