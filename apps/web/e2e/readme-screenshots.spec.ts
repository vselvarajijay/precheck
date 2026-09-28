import type { Page } from '@playwright/test'
import { API, expect, resetDb, test } from './fixtures'

// Captures the README screenshots (docs/images/). Run with `make screenshots`; skipped otherwise.
test.skip(!process.env.README_SCREENSHOTS, 'set README_SCREENSHOTS=1 (make screenshots)')
test.use({ viewport: { width: 1280, height: 800 }, deviceScaleFactor: 2 })

const OUT = 'test-results/readme'

/** Hide toasts and the replay-mode status pill ("Jev not configured") before a capture. */
async function tidy(page: Page) {
  await page.addStyleTag({
    content: '[data-sonner-toaster] { display: none !important; } [data-testid="health-badge"] { visibility: hidden !important; }',
  })
  await expect(page.getByTestId('health-badge')).toBeHidden()
}

const RULE = 'refund-different-payment-method'

// Must match the recorded translation used by translate.spec.ts (replayed by request).
const CASE = {
  text: "Refunds over $500 need a manager. Never refund to a different card than the one used for the purchase. The agent must say why it's refunding.",
  tools: 'issue_refund, lookup_order, read_customer_profile',
  purpose: 'Handles customer support for orders, refunds and customer accounts',
}

test('1: translate a business case into rules', async ({ page, request }) => {
  await resetDb(request)
  await page.goto('/rules')
  await page.getByRole('link', { name: 'New from business case' }).click()
  await page.getByLabel('Business case', { exact: true }).fill(CASE.text)
  await page.getByLabel('Gate hint').selectOption('tool_call')
  await page.getByLabel('Tools').fill(CASE.tools)
  await page.getByLabel('Agent purpose').fill(CASE.purpose)
  await page.getByRole('button', { name: 'Translate' }).click()
  await expect(page.locator('[data-testid^="translated-rule-"]')).toHaveCount(3, { timeout: 15_000 })
  await tidy(page)
  await page.screenshot({ path: `${OUT}/translate.png`, fullPage: true })
})

test('2: review a rule and its Jev question', async ({ page, request }) => {
  await resetDb(request)
  expect((await request.post(`${API}/api/examples/packs/demo/load`)).ok()).toBe(true)
  await page.goto(`/rules/${RULE}`)
  await page.getByRole('tab', { name: 'Definition' }).click()
  await tidy(page)
  // Crop to the Jev check: its heading through the "Add question" button.
  const top = await page.getByText('Jev check', { exact: true }).boundingBox()
  const bottom = await page.getByRole('button', { name: 'Add question' }).boundingBox()
  if (!top || !bottom) throw new Error('Jev check section not found')
  const x = top.x - 24
  await page.screenshot({
    path: `${OUT}/rule-jev-check.png`,
    fullPage: true,
    clip: { x, y: top.y - 24, width: 1280 - x - 16, height: bottom.y + bottom.height + 24 - (top.y - 24) },
  })
})

test('3: calibrate thresholds against labeled cases', async ({ page, request }) => {
  await resetDb(request)
  expect((await request.post(`${API}/api/examples/packs/demo/load`)).ok()).toBe(true)
  // Start from thresholds that are too loose so calibration has something to fix.
  const rule = await (await request.get(`${API}/api/rules/${RULE}`)).json()
  const body = rule.current.body
  body.jev.outcomes.different_method.bands = { escalate_at: 0.98, deny_at: 0.99 }
  expect((await request.put(`${API}/api/rules/${RULE}`, { data: { body } })).ok()).toBe(true)
  const examples = await (await request.get(`${API}/api/examples`)).json()
  for (const [id, verdict] of [['refund-different-card', 'deny'], ['refund-same-card-ok', 'allow']]) {
    const ex = examples.find((e: { id: string }) => e.id === id)
    const res = await request.post(`${API}/api/test-cases`, {
      data: { rule_id: RULE, name: id, check_request: ex.check_request, expected_verdict: verdict },
    })
    expect(res.ok()).toBe(true)
  }
  await page.goto(`/rules/${RULE}`)
  await page.getByRole('tab', { name: 'Tests' }).click()
  await page.getByRole('button', { name: 'Run all' }).click()
  await expect(page.getByTestId('tests-summary')).toContainText('1/2 passing')
  await page.getByRole('button', { name: 'Suggest thresholds' }).click()
  await expect(page.getByTestId('calibration-histogram')).toBeVisible()
  await tidy(page)
  await page.screenshot({ path: `${OUT}/calibration.png`, fullPage: true })
})

test('4: try a request in the playground', async ({ page, request }) => {
  await resetDb(request)
  await page.goto('/playground')
  await page.getByRole('button', { name: 'Load demo rules' }).click()
  await expect(page.getByText(/Demo rules: \d+ created/)).toBeVisible()
  await page.getByLabel('Load example').selectOption('refund-different-card')
  await page.getByRole('button', { name: 'Run' }).click()
  await expect(page.getByTestId('decision-panel').locator('[data-slot="badge"]').first()).toHaveText('deny')
  await tidy(page)
  await page.screenshot({ path: `${OUT}/playground.png`, fullPage: true })
})
