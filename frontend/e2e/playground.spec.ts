import { expect, expectNoSeriousA11yViolations, test } from './fixtures'

const DEMO_RULES = ['refund-over-limit', 'refund-different-payment-method', 'reason-required', 'pii-to-external-domain']

test('refund example: different card DENY, same card ALLOW, save test case', async ({ page, consoleErrors }) => {
  void consoleErrors
  await page.goto('/playground')
  await page.getByRole('button', { name: 'Load demo rules' }).click()
  await expect(page.getByText(/Demo rules: \d+ created/)).toBeVisible()

  // Evaluate against exactly the demo rules (other e2e tests create rules too).
  await page.getByLabel('Scope').selectOption('rules')
  for (const id of DEMO_RULES) await page.getByRole('checkbox', { name: `Include ${id}` }).click()

  await page.getByLabel('Load example').selectOption('refund-different-card')
  await expect(page.getByLabel('Tool', { exact: true })).toHaveValue('issue_refund')
  await page.getByRole('button', { name: 'Run' }).click()
  const panel = page.getByTestId('decision-panel')
  await expect(panel.locator('[data-slot="badge"]').first()).toHaveText('deny')
  const cardRule = page.getByTestId('rule-result-refund-different-payment-method')
  await expect(cardRule).toContainText('Refund to different payment method')
  await expect(cardRule.getByTestId('probability-bar')).toHaveAttribute('data-region', 'deny')
  await expect(page.getByTestId('rule-result-refund-over-limit')).toContainText('request.args.amount > 500 = false')
  await expectNoSeriousA11yViolations(page)

  // Switch the destination to the original card.
  const args = page.getByTestId('args-editor').locator('.cm-content')
  await args.click()
  await page.keyboard.press('ControlOrMeta+a')
  await page.keyboard.press('Delete')
  await args.fill('{"order_id": "1234", "amount": 120, "destination": "Visa ending 4242"}')
  // The old reason ("to their new Mastercard") no longer matches; the reason rule would deny.
  await page.getByLabel('Reason', { exact: true }).fill('Customer returned the item; refunding the full amount to the original Visa')
  await page.getByRole('button', { name: 'Run' }).click()
  await expect(cardRule.getByTestId('probability-bar')).toHaveAttribute('data-region', 'allow')
  await expect(panel.locator('[data-slot="badge"]').first()).toHaveText('allow')

  // Save as a test case for the card rule and find it on the rule's Tests tab.
  await page.getByLabel('Test case rule').selectOption('refund-different-payment-method')
  await page.getByLabel('Test case name').fill('same card refund')
  await page.getByTestId('save-test-case').getByRole('button', { name: 'Save' }).click()
  await expect(page.getByText(/Saved test case “same card refund”/)).toBeVisible()

  await expect(page.getByTestId('run-history').locator('li')).toHaveCount(2)

  await page.goto('/rules/refund-different-payment-method')
  await page.getByRole('tab', { name: 'Tests' }).click()
  const tests = page.getByTestId('rule-tests')
  await expect(tests).toContainText('1 test case')
  await expect(tests.getByRole('row', { name: /same card refund/ })).toContainText('allow')
  await expect(tests.getByRole('row', { name: /same card refund/ })).toContainText('playground')
})

test('request type toggle swaps the fields', async ({ page, consoleErrors }) => {
  void consoleErrors
  await page.goto('/playground')
  await expect(page.getByTestId('tool-call-fields')).toBeVisible()
  await page.getByRole('radio', { name: 'External call' }).click()
  await expect(page.getByTestId('external-call-fields')).toBeVisible()
  await expect(page.getByTestId('tool-call-fields')).toHaveCount(0)
  await page.getByRole('radio', { name: 'Content' }).click()
  await expect(page.getByTestId('content-fields')).toBeVisible()
})
