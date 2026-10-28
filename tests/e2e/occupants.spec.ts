import { expect, test } from '@playwright/test';
import { OCCUPANTS } from '../../src/data/gateway/occupants';

// Faculty names come from the EECS directory via tools/faculty/import_faculty.py; the
// tests follow whatever that file holds, so they pass on a fresh (empty) import as well.
const entries = Object.entries(OCCUPANTS).filter(([, names]) => names.length);
const [room, names] = entries[0] ?? ['', []];
const name = names[0] ?? '';
const floor = room.replace(/^[A-Z]/, '')[0];
const spaceId = floor ? `${floor === 'B' ? '0' : floor}-${room.toLowerCase()}` : '';

test.describe('faculty offices', () => {
  test.skip(!room, 'no occupants are listed in src/data/gateway/occupants.ts');

  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.waitForSelector('#map [data-space-id]');
  });

  test('search finds an office by its occupant, and the details name them', async ({ page }) => {
    const input = page.getByRole('searchbox', { name: 'Search spaces' });
    await input.fill(name);
    const hit = page.locator('.search__hit').first();
    await expect(hit).toContainText(room);
    await expect(hit.locator('.search__who')).toContainText(name);
    await input.press('Enter');
    await expect(page).toHaveURL(new RegExp(`room=${spaceId}$`));
    await expect(page.locator('#panel h2')).toContainText(room);
    await expect(page.locator('#panel .occupants')).toContainText(name);

    // The surname alone is enough.
    await input.fill(name.split(' ').pop()!);
    await expect(page.locator('.search__hit').first()).toContainText(room);
  });

  test('the office is labelled with the name on the map and in the floor list', async ({ page }) => {
    await page.goto(`/floor-${spaceId.split('-')[0]}`);
    const space = page.locator(`#map [data-space-id="${spaceId}"]`);
    await expect(space).toHaveAttribute('aria-label', new RegExp(`${room}, ${name}`));
    const label = space.locator('.space__label');
    await expect(label).toContainText(room);
    for (const part of name.split(' ')) await expect(label).toContainText(part);
    expect(await label.locator('.space__label-name').count()).toBeGreaterThan(0);

    // The list line reads "names · department" when the room has a department too.
    await expect(page.locator(`#panel [data-space-id="${spaceId}"] .list-btn__who`)).toContainText(names.join(', '));
    await space.hover();
    await expect(page.locator('#tooltip')).toContainText(name);
  });
});

test('every room in the directory is on the map', async ({ page }) => {
  const warnings: string[] = [];
  page.on('console', (msg) => {
    if (msg.type() === 'error') warnings.push(msg.text());
  });
  await page.goto('/');
  await page.waitForSelector('#map [data-space-id]');
  expect(warnings.filter((w) => w.includes('Occupants listed for room'))).toEqual([]);
});
