import { expect, test } from '@playwright/test';

test.beforeEach(async ({ page }) => {
  await page.goto('/');
  await page.waitForSelector('#map [data-space-id]');
});

test('opens on the ground floor and can switch to every level', async ({ page }) => {
  await expect(page).toHaveURL('/floor-1');
  await expect(page.locator('#map [data-floor-id]')).toHaveAttribute('data-floor-id', '1');
  await expect(page.locator('#panel h2')).toHaveText('Floor 1');
  // Level 1's detached Southwest block is a second outline path.
  expect(await page.locator('#map .floor__outline').count()).toBe(2);

  const expected: Record<string, number> = { LL: 10, '1': 50, '2': 150, '3': 150, '4': 150, '5': 25 };
  for (const [label, minRooms] of Object.entries(expected)) {
    await page.getByRole('button', { name: label, exact: true }).click();
    await expect(page.locator('#panel h2')).toHaveText(`Floor ${label}`);
    await expect(page).toHaveURL(`/floor-${label === 'LL' ? '0' : label}`);
    expect(await page.locator('#map [data-space-id]').count()).toBeGreaterThan(minRooms);
  }
});

test('clicking a room selects it and shows details', async ({ page }) => {
  await page.getByRole('button', { name: '4', exact: true }).click();
  await page.locator('[data-space-id="4-4161"] .space__shape').click();
  await expect(page.locator('#panel h2')).toHaveText('Small Meeting Room 4161');
  await expect(page).toHaveURL('/floor-4?room=4-4161');
  await expect(page.locator('#map [data-space-id="4-4161"]')).toHaveClass(/is-selected/);
  await expect(page.locator('#panel .facts')).toContainText('Northeast');

  await page.getByRole('button', { name: 'Back to floor' }).click();
  await expect(page.locator('#panel h2')).toHaveText('Floor 4');
  await expect(page).toHaveURL('/floor-4');
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

test('open workspaces show their desks, and the research labs are plain boxes', async ({ page }) => {
  await page.getByRole('button', { name: '4', exact: true }).click();
  // Desks are drawn as context only: many of them, none of them focusable or clickable.
  expect(await page.locator('#map .furniture .desk').count()).toBeGreaterThan(200);
  await expect(page.locator('#map .furniture')).toHaveAttribute('aria-hidden', 'true');
  // Labs 4131, 4184 and 4192 are rectangles on the plan: four corners each.
  for (const id of ['4-4131', '4-4184', '4-4192']) {
    const d = (await page.locator(`[data-space-id="${id}"] .space__shape`).getAttribute('d')) ?? '';
    expect(d.match(/[ML]/g)?.length, `${id} should be a box`).toBe(4);
  }
  // Huddle room 4151 stands inside open office 4160, which is drawn with a hole for it.
  const open = (await page.locator('[data-space-id="4-4160"] .space__shape').getAttribute('d')) ?? '';
  expect(open.match(/M/g)?.length).toBe(2);
});

test('keyboard users can select a room with Enter', async ({ page }) => {
  await page.getByRole('button', { name: '4', exact: true }).click();
  await page.locator('#map [data-space-id="4-4131"]').focus();
  await page.keyboard.press('Enter');
  await expect(page.locator('#panel h2')).toHaveText('General Research Lab 4131');
  await expect(page).toHaveURL('/floor-4?room=4-4131');
});

test('search finds rooms by number and by feature, across floors', async ({ page }) => {
  const input = page.getByRole('searchbox', { name: 'Search spaces' });
  await input.fill('4355');
  await expect(page.locator('.search__hit')).toHaveCount(1);
  await input.press('Enter');
  await expect(page.locator('#panel h2')).toHaveText('Large Meeting Room 4355');
  await expect(page.locator('#map [data-floor-id]')).toHaveAttribute('data-floor-id', '4');
  await expect(page).toHaveURL('/floor-4?room=4-4355');

  await input.fill('2322');
  await input.press('Enter');
  await expect(page.locator('#panel h2')).toHaveText('Assembly Lab 2322');
  await expect(page.locator('#map [data-floor-id]')).toHaveAttribute('data-floor-id', '2');
  await expect(page).toHaveURL('/floor-2?room=2-2322');

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

test('Hearst Avenue is drawn north of the building on every floor', async ({ page }) => {
  for (const label of ['LL', '1', '2', '3', '4', '5']) {
    await page.getByRole('button', { name: label, exact: true }).click();
    const street = page.locator('#map [data-street-id="hearst"]');
    await expect(street).toHaveAttribute('aria-hidden', 'true');
    await expect(street.locator('textPath')).toHaveText('Hearst Avenue');
    // The street runs above (north of) the building's outline.
    const road = (await street.locator('.street__road').boundingBox())!;
    const outline = (await page.locator('#map .floor__outline').first().boundingBox())!;
    expect(road.y).toBeLessThan(outline.y);
  }
});

test('every floor shows its atrium, and floor 5 its roof terrace', async ({ page }) => {
  for (const label of ['1', '2', '3']) {
    await page.getByRole('button', { name: label, exact: true }).click();
    await expect(page.locator(`#map [data-space-id="${label}-atrium"]`)).toHaveCount(1);
  }
  await page.getByRole('button', { name: '5', exact: true }).click();
  await expect(page.locator('#map [data-space-id="5-skylight"]')).toHaveCount(1);
  // The terrace wraps around the indoor blocks: they are holes in it.
  const d = (await page.locator('[data-space-id="5-terrace"] .space__shape').getAttribute('d')) ?? '';
  expect(d.match(/M/g)?.length).toBeGreaterThan(1);
});

test('the lower level has round study spaces B1030 and B1010', async ({ page }) => {
  await page.getByRole('button', { name: 'LL', exact: true }).click();
  for (const id of ['0-b1030', '0-b1010']) {
    await expect(page.locator(`#map [data-space-id="${id}"]`)).toHaveClass(/space--study/);
  }
  await expect(page.locator('#map [data-space-id="0-main-stair"]')).toHaveCount(1);
});

test('the East Stair stays inside the building on every floor', async ({ page }) => {
  for (const label of ['1', '2', '3', '4']) {
    await page.getByRole('button', { name: label, exact: true }).click();
    const outside = await page.locator(`#map [data-space-id="${label}-east-stair"] .space__shape`).evaluate((stair: SVGPathElement) => {
      const outlines = [...document.querySelectorAll<SVGPathElement>('#map .floor__outline')];
      const length = stair.getTotalLength();
      let count = 0;
      for (let i = 0; i < 100; i++) {
        const p = stair.getPointAtLength((length * i) / 100);
        if (!outlines.some((o) => o.isPointInFill(new DOMPoint(p.x, p.y)))) count++;
      }
      return count;
    });
    expect(outside).toBe(0);
  }
});

test('the Floor 1 lecture halls and drone lab never overlap, with a hallway behind them', async ({ page }) => {
  await expect(page.locator('#map [data-space-id="1-east-hallway"]')).toHaveClass(/space--circulation/);
  const shared = await page.evaluate(() => {
    const shapes = ['1210', '1220', '1230'].map((id) => document.querySelector<SVGPathElement>(`[data-space-id="1-${id}"] .space__shape`)!);
    let count = 0;
    for (let i = 0; i < shapes.length; i++) {
      for (let j = i + 1; j < shapes.length; j++) {
        const a = shapes[i].getBBox();
        for (let x = a.x; x <= a.x + a.width; x += 4) {
          for (let y = a.y; y <= a.y + a.height; y += 4) {
            const p = new DOMPoint(x, y);
            if (shapes[i].isPointInFill(p) && shapes[j].isPointInFill(p)) count++;
          }
        }
      }
    }
    return count;
  });
  // shared walls may touch a sample point or two, an overlap covers many
  expect(shared).toBeLessThan(5);
});

test('exterior doors are entrance markers, not notches in the outline', async ({ page }) => {
  expect(await page.locator('#map .poi--exit').count()).toBeGreaterThan(5);
});
