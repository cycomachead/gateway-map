import AxeBuilder from '@axe-core/playwright';
import { expect, test, type Page } from '@playwright/test';

/**
 * Accessibility checks with axe-core. Each state of the UI that a user can reach is
 * scanned; any violation fails the build. Violations are printed with the offending
 * nodes so the fix is obvious from the CI log.
 */
async function expectNoViolations(page: Page, state: string) {
  const results = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'best-practice'])
    .analyze();
  const summary = results.violations.map(
    (v) => `${v.id} (${v.impact}): ${v.help}\n` + v.nodes.map((n) => `    ${n.target.join(' ')}`).join('\n'),
  );
  expect(summary, `axe violations in state "${state}"`).toEqual([]);
}

test.beforeEach(async ({ page }) => {
  await page.goto('/');
  await page.waitForSelector('#map [data-space-id]');
});

test('floor overview has no axe violations', async ({ page }) => {
  await expectNoViolations(page, 'overview');
});

test('room details panel has no axe violations', async ({ page }) => {
  await page.locator('[data-space-id="1-1171"] .space__shape').click();
  await expect(page.locator('#panel h2')).toHaveText('Small Meeting Room 1171');
  await expectNoViolations(page, 'room selected');
});

test('search results have no axe violations', async ({ page }) => {
  await page.getByRole('searchbox', { name: 'Search spaces' }).fill('lab');
  await expect(page.locator('.search__hit').first()).toBeVisible();
  await expectNoViolations(page, 'search open');
});

test('active filter has no axe violations', async ({ page }) => {
  await page.getByRole('button', { name: 'Meeting rooms' }).click();
  await expectNoViolations(page, 'filter active');
});

test('dark colour scheme has no axe violations', async ({ page }) => {
  await page.emulateMedia({ colorScheme: 'dark' });
  await page.locator('[data-space-id="1-1210"] .space__shape').click();
  await expectNoViolations(page, 'dark mode');
});
