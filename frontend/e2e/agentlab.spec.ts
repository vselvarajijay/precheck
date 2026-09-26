import { API, expect, expectNoSeriousA11yViolations, resetDb, test } from './fixtures'

const PROXY = process.env.E2E_PROXY_URL ?? 'http://127.0.0.1:8200'
const PII_RULE = 'pii-to-external-domain'
const TOOLS = process.env.E2E_TOOLS_URL ?? 'http://127.0.0.1:8100'

test.beforeEach(async ({ request }) => {
  await resetDb(request)
  expect((await request.post(`${API}/api/testing/seed-demo`)).ok()).toBe(true)
  expect((await request.post(`${PROXY}/reload`)).ok()).toBe(true)
  expect((await request.post(`${TOOLS}/reset`)).ok()).toBe(true)
})

test('pii-exfiltration: timeline shows the read allowed and the post denied, not reached', async ({ page, request, consoleErrors }) => {
  void consoleErrors
  await page.goto('/lab')
  await expect(page.getByRole('heading', { name: 'Agent Lab' })).toBeVisible()
  await page.getByLabel('Scenario', { exact: true }).selectOption('pii-exfiltration')
  await page.getByRole('button', { name: 'Run', exact: true }).click()
  const timeline = page.getByTestId('run-timeline')
  await expect(timeline.getByTestId('run-status')).toHaveText('passed', { timeout: 30_000 })
  const s1 = timeline.getByTestId('step-1')
  await expect(s1).toContainText('read_customer_profile')
  await expect(s1).toContainText('allow')
  await expect(s1.getByTestId('reached')).toBeVisible()
  const s2 = timeline.getByTestId('step-2')
  await expect(s2).toContainText('http_request')
  await expect(s2).toContainText('deny')
  await expect(s2.getByTestId('not-reached')).toBeVisible()
  await expect(s2).toHaveAttribute('data-passed', 'true')
  await expectNoSeriousA11yViolations(page)

  // Round trip: the denied step opens prefilled in the playground; loosening the rule in a
  // draft changes the playground verdict while the live policy still denies.
  await s2.getByRole('button', { name: 'Open in Playground' }).click()
  await expect(page).toHaveURL(/\/playground$/)
  await expect(page.getByText('pastebin.com').first()).toBeVisible()
  const rule = await (await request.get(`${API}/api/rules/${PII_RULE}`)).json()
  const body = rule.current.body
  for (const o of Object.values(body.jev.outcomes) as { bands: object }[]) o.bands = { escalate_at: 0.999, deny_at: 1 }
  expect((await request.put(`${API}/api/rules/${PII_RULE}`, { data: { body } })).ok()).toBe(true)

  const decision = page.getByRole('region', { name: 'Decision' })
  await page.getByLabel('Scope').selectOption('draft')
  await page.getByRole('button', { name: 'Run', exact: true }).click()
  await expect(decision.getByTestId(`rule-result-${PII_RULE}`)).toContainText('allow')
  await page.getByLabel('Scope').selectOption('live')
  await page.getByRole('button', { name: 'Run', exact: true }).click()
  await expect(decision.getByTestId(`rule-result-${PII_RULE}`)).toContainText('deny')
})

test('scenario suite: run all is green', async ({ page, consoleErrors }) => {
  void consoleErrors
  test.setTimeout(180_000)
  await page.goto('/lab')
  await page.getByRole('tab', { name: 'Scenarios' }).click()
  await page.getByRole('button', { name: 'Run all' }).click()
  await expect(page.getByText('9/9 scenarios passed')).toBeVisible({ timeout: 150_000 })
  const rows = page.locator('[data-testid^="scenario-"]')
  await expect(rows).toHaveCount(9)
  for (const row of await rows.all()) await expect(row.getByTestId('last-status')).toHaveText('passed')
  await expectNoSeriousA11yViolations(page)
})

test('approve an escalation, then retrying the step is allowed', async ({ page, consoleErrors }) => {
  void consoleErrors
  await page.goto('/lab')
  await page.getByLabel('Scenario', { exact: true }).selectOption('large-refund')
  await page.getByRole('button', { name: 'Run', exact: true }).click()
  const step = page.getByTestId('run-timeline').getByTestId('step-2')
  await expect(step).toContainText('escalate', { timeout: 30_000 })
  await expect(page.getByTestId('escalation-badge')).toHaveText('1')

  await page.getByRole('tab', { name: /Escalations/ }).click()
  const esc = page.locator('[data-testid^="escalation-item-"]').first()
  await expect(esc).toContainText('issue_refund')
  await expectNoSeriousA11yViolations(page)
  await esc.getByRole('button', { name: 'Approve' }).click()
  await expect(page.getByText('No pending escalations.')).toBeVisible()
  await expect(page.getByTestId('escalation-badge')).toHaveCount(0)

  await page.getByRole('tab', { name: 'Run' }).click()
  await step.getByRole('button', { name: 'Retry' }).click()
  const retried = page.getByTestId('run-timeline').getByTestId('step-3')
  await expect(retried).toContainText('issue_refund')
  await expect(retried).toContainText('allow')
  await expect(retried.getByTestId('reached')).toBeVisible()
})
