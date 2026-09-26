import { expect, expectNoSeriousA11yViolations, test } from './fixtures'

// Must match backend/tests/translator_eval/cases/01-refund-limit-card-reason.yaml exactly:
// the Claude responses are replayed from recordings keyed by the request.
const CASE = {
  text: "Refunds over $500 need a manager. Never refund to a different card than the one used for the purchase. The agent must say why it's refunding.",
  tools: 'issue_refund, lookup_order, read_customer_profile',
  purpose: 'Handles customer support for orders, refunds and customer accounts',
}

test('business case -> 3 rules -> try one -> save -> in Rules list with tests', async ({ page, consoleErrors }) => {
  void consoleErrors
  await page.goto('/rules')
  await page.getByRole('link', { name: 'New from business case' }).click()
  await page.getByLabel('Business case', { exact: true }).fill(CASE.text)
  await page.getByLabel('Gate hint').selectOption('tool_call')
  await page.getByLabel('Tools').fill(CASE.tools)
  await page.getByLabel('Agent purpose').fill(CASE.purpose)
  await page.getByRole('button', { name: 'Translate' }).click()

  const cards = page.locator('[data-testid^="translated-rule-"]')
  await expect(cards).toHaveCount(3, { timeout: 15_000 })
  await expect(page.getByTestId('progress').locator('li[data-state="done"]')).toHaveCount(4)
  await expect(page.getByTestId('translation-meta')).toContainText('claude-sonnet-5')
  await expect(page.getByRole('region', { name: 'Requirements' })).toContainText('deterministic')
  const limit = page.getByTestId('translated-rule-refund-over-limit')
  await expect(limit).toContainText('request.args.amount > 500 → escalate')
  await expect(page.getByTestId('translated-rule-refund-different-payment-method')).toContainText('Looks at')
  await expectNoSeriousA11yViolations(page)

  // Try the (unsaved) limit rule with its first generated test.
  await limit.getByRole('button', { name: 'Try in playground' }).click()
  await expect(page).toHaveURL(/\/playground$/)
  await expect(page.getByLabel('Scope')).toHaveValue('inline')
  await page.getByRole('button', { name: 'Run' }).click()
  await expect(page.getByTestId('rule-result-refund-over-limit')).toBeVisible()
  await page.goBack()

  // Translation state is gone after navigating away; translate again (replayed) and save.
  await page.getByLabel('Business case', { exact: true }).fill(CASE.text)
  await page.getByLabel('Gate hint').selectOption('tool_call')
  await page.getByLabel('Tools').fill(CASE.tools)
  await page.getByLabel('Agent purpose').fill(CASE.purpose)
  await page.getByRole('button', { name: 'Translate' }).click()
  await expect(cards).toHaveCount(3, { timeout: 15_000 })
  await page.getByRole('button', { name: 'Save all as draft' }).click()
  await expect(page.getByText(/Saved 3 draft rule\(s\) and 12 test case\(s\)/)).toBeVisible()
  await expect(page).toHaveURL(/\/rules$/)

  const row = page.getByRole('row', { name: /Refund must go to original payment method/ }).first()
  await expect(row).toContainText('jev')
  await row.getByRole('link').click()
  await page.getByRole('tab', { name: 'Tests' }).click()
  await expect(page.getByTestId('rule-tests')).toContainText('4 test cases')
  await expect(page.getByTestId('rule-tests')).toContainText('generated')
  await page.getByRole('tab', { name: 'Overview' }).click()
  await expect(page.getByText(/translator claude-sonnet-5/)).toBeVisible()
})
