import AxeBuilder from '@axe-core/playwright'
import { test as base, expect, type APIRequestContext, type Page } from '@playwright/test'

interface ConsoleGuard {
  /** Declare an expected console error (e.g. a deliberate 422); each match is consumed once. */
  expect: (pattern: RegExp) => void
}

/** Fails the test on any browser console error or uncaught page error not declared up front. */
export const test = base.extend<{ consoleErrors: ConsoleGuard }>({
  consoleErrors: async ({ page }, use) => {
    const errors: string[] = []
    const expected: RegExp[] = []
    page.on('console', (m) => {
      if (m.type() !== 'error') return
      const i = expected.findIndex((re) => re.test(m.text()))
      if (i >= 0) expected.splice(i, 1)
      else errors.push(m.text())
    })
    page.on('pageerror', (e) => errors.push(String(e)))
    await use({ expect: (re) => expected.push(re) })
    expect(errors, 'unexpected browser console errors').toEqual([])
  },
})

export { expect }

export async function expectNoSeriousA11yViolations(page: Page) {
  // Let transitions (e.g. toasts fading in) settle; mid-fade opacity skews contrast checks.
  await page.waitForFunction(() => document.getAnimations().every((a) => a.playState !== 'running'))
  const results = await new AxeBuilder({ page }).analyze()
  const serious = results.violations.filter((v) => v.impact === 'critical' || v.impact === 'serious')
  expect(
    serious.map((v) => `${v.id}: ${v.help} (${v.nodes.length})`),
    'critical/serious axe violations',
  ).toEqual([])
}

export const API = process.env.E2E_API_URL ?? 'http://127.0.0.1:8000'

/** Empty the isolated e2e database (endpoint exists only there). */
export async function resetDb(request: APIRequestContext) {
  const res = await request.post(`${API}/api/testing/reset`)
  expect(res.status(), 'test reset endpoint').toBe(204)
}
