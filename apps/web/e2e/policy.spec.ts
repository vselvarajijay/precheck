import { API, expect, expectNoSeriousA11yViolations, resetDb, test } from './fixtures'

const RULE = 'refund-over-limit' // deterministic: publishing needs no Jev calls

test.beforeEach(async ({ request }) => {
  await resetDb(request)
  expect((await request.post(`${API}/api/examples/packs/demo/load`)).ok()).toBe(true)
  expect((await request.post(`${API}/api/rules/${RULE}/publish`)).ok()).toBe(true) // policy v1
  const rule = await (await request.get(`${API}/api/rules/${RULE}`)).json()
  const body = rule.current.body
  body.deterministic.predicate.value = 300
  expect((await request.put(`${API}/api/rules/${RULE}`, { data: { body } })).ok()).toBe(true)
  expect((await request.post(`${API}/api/rules/${RULE}/publish`)).ok()).toBe(true) // policy v2
})

test('policy versions: roll back to v1 re-points the live version', async ({ page, request, consoleErrors }) => {
  void consoleErrors
  await page.goto('/settings')
  await expect(page.getByTestId('policy-v2')).toContainText('active')
  await expect(page.getByTestId('policy-v2')).toContainText(`${RULE}@v2`)
  await expectNoSeriousA11yViolations(page)
  await page.getByTestId('policy-v1').getByRole('button', { name: 'Activate' }).click()
  await expect(page.getByText('Rolled back: policy v3 = v1')).toBeVisible()
  await expect(page.getByTestId('policy-v3')).toContainText(`${RULE}@v1`)
  const rule = await (await request.get(`${API}/api/rules/${RULE}`)).json()
  expect(rule.live_version).toBe(1)
  expect(rule.live.body.deterministic.predicate.value).toBe(500)
})

test('export YAML, then import it back as drafts', async ({ page, consoleErrors }) => {
  void consoleErrors
  await page.goto('/settings')
  const [download] = await Promise.all([
    page.waitForEvent('download'),
    page.getByRole('button', { name: 'Export live rules' }).click(),
  ])
  expect(download.suggestedFilename()).toBe('policy.yaml')
  const text = await (await download.createReadStream()).toArray().then((c) => Buffer.concat(c).toString())
  expect(text).toContain(`id: ${RULE}`)
  expect(text).toContain('schema: 1')
  await page.getByLabel('Import YAML').fill(text)
  await page.getByRole('button', { name: 'Import as drafts' }).click()
  await expect(page.getByText('Imported 1 draft rule(s), 0 test case(s)')).toBeVisible()
  await page.goto('/rules')
  await expect(page.getByTestId(`rule-row-${RULE}-2`)).toContainText('○ draft')
})
