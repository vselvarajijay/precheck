import { API, expect, expectNoSeriousA11yViolations, resetDb, test } from './fixtures'

const RULE = 'refund-different-payment-method'

test.beforeEach(async ({ request }) => {
  await resetDb(request)
  // Demo rules; loosen the card rule's deny threshold so a clear violation only escalates.
  expect((await request.post(`${API}/api/examples/packs/demo/load`)).ok()).toBe(true)
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
})

test('run tests -> one fails -> suggest -> apply to draft -> rerun passes', async ({ page, consoleErrors }) => {
  void consoleErrors
  await page.goto(`/rules/${RULE}`)
  await page.getByRole('tab', { name: 'Tests' }).click()
  await page.getByRole('button', { name: 'Run all' }).click()
  const summary = page.getByTestId('tests-summary')
  await expect(summary).toContainText('1/2 passing')
  await expect(page.getByTestId('case-refund-different-card')).toContainText('fail')
  await page.getByTestId('case-refund-different-card').getByRole('button', { name: /why/ }).click()
  // Jev isn't bit-for-bit deterministic (jev.md): only require a clear, high value.
  await expect(page.getByText(/value 0\.9\d → allow/)).toBeVisible()

  await page.getByRole('button', { name: 'Suggest thresholds' }).click()
  await expect(page.getByTestId('calibration-histogram')).toBeVisible()
  await expect(page.getByTestId('calibration')).toContainText('→ 2/2')
  await expectNoSeriousA11yViolations(page)
  await page.getByTestId('calibration').screenshot({ path: 'test-results/09-calibration.png' })
  await page.getByRole('button', { name: 'Apply to draft' }).click()
  await expect(page.getByText(/Applied to draft v3/)).toBeVisible()

  await page.getByRole('button', { name: 'Run all' }).click()
  await expect(summary).toContainText('2/2 passing')
  await expect(page.getByText('v3', { exact: true })).toBeVisible()
})

test('policy-wide Tests page runs every case', async ({ page, consoleErrors }) => {
  void consoleErrors
  await page.goto('/tests')
  await page.getByRole('button', { name: 'Run every test case' }).click()
  await expect(page.getByTestId('policy-summary')).toContainText('1 passed · 1 failed · 0 errors')
  await expect(page.getByRole('link', { name: RULE })).toBeVisible()
})
