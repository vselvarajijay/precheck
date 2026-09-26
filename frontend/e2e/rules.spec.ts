import { expect, expectNoSeriousA11yViolations, test } from './fixtures'

test('create -> edit -> v2 diff -> live blocked on jev-latest -> pin -> live', async ({ page, consoleErrors }) => {
  const name = `Refund different method ${Date.now()}`

  await page.goto('/rules/new')
  await page.getByLabel('Name', { exact: true }).fill(name)
  await page.getByLabel('Source text').fill('Never refund to a different card than the one used for the purchase.')
  await page.getByLabel('Question q1 instructions').fill('Does this refund go to a different payment method?')
  await page.getByRole('checkbox', { name: 'history' }).first().click()
  await expectNoSeriousA11yViolations(page)
  await page.getByRole('button', { name: 'Create draft' }).click()

  await expect(page.getByRole('heading', { name })).toBeVisible()
  await expect(page.getByText('v1', { exact: true })).toBeVisible()
  await expect(page.getByText('○ draft')).toBeVisible()
  await expectNoSeriousA11yViolations(page)

  // Edit -> v2
  await page.getByRole('tab', { name: 'Definition' }).click()
  await page.getByLabel('Question q1 instructions').fill('Does this refund send money to a different card than the original purchase?')
  await page.getByRole('button', { name: 'Save new version' }).click()
  await expect(page.getByText('Saved as v2')).toBeVisible()

  // Versions diff shows the changed instruction
  await page.getByRole('tab', { name: /Versions/ }).click()
  const diff = page.getByTestId('version-diff')
  await expect(diff).toContainText('v1 → v2')
  await expect(diff.locator('[data-diff="removed"]')).toContainText('different payment method?')
  await expect(diff.locator('[data-diff="added"]')).toContainText('different card than the original purchase?')

  // Live fails while unpinned (the browser logs the deliberate 422)
  consoleErrors.expect(/status of 422/)
  await page.getByRole('button', { name: 'Set live' }).click()
  await expect(page.getByText('Rule cannot be published')).toBeVisible()
  await expect(page.getByText(/must pin a Jev version/).first()).toBeVisible()

  // Pin -> v3 -> live
  await page.getByRole('tab', { name: 'Definition' }).click()
  await page.getByLabel('Jev model').fill('jev-1.13.0')
  await expect(page.getByTestId('validation-summary')).toContainText('publishable')
  await page.getByRole('button', { name: 'Save new version' }).click()
  await expect(page.getByText('Saved as v3')).toBeVisible()
  await page.getByRole('button', { name: 'Set live' }).click()
  await expect(page.getByText('Published v3')).toBeVisible()
  await expect(page.getByText('● live')).toBeVisible()

  // Listed as live
  await page.goto('/rules')
  const row = page.getByRole('row', { name: new RegExp(name) })
  await expect(row).toContainText('● live')
  await expect(row).toContainText('jev-1.13.0')
  await expectNoSeriousA11yViolations(page)
})

test('JSON tab edits flow back into the form', async ({ page, consoleErrors }) => {
  void consoleErrors
  await page.goto('/rules/new')
  await page.getByLabel('Question q1 instructions').fill('Original question?')
  await page.getByRole('tab', { name: 'JSON' }).click()
  const editor = page.getByTestId('json-editor').locator('.cm-content')
  await expect(editor).toContainText('Original question?')
  // Replace the whole document with an edited body.
  const body = {
    requires: [],
    on_missing: 'escalate',
    severity: 'high',
    jev: {
      model: 'jev-latest',
      state_template: ['request', 'reason'],
      questions: { q1: { type: 'noul', instructions: 'Edited in JSON?' } },
      outcomes: { q1: { type: 'noul', bands: { escalate_at: 0.3, deny_at: 0.8 }, direction: 'high_is_bad' } },
    },
  }
  await editor.click()
  await page.keyboard.press('ControlOrMeta+a')
  await page.keyboard.press('Delete')
  await editor.fill(JSON.stringify(body, null, 2))
  await expect(page.getByTestId('json-status')).toContainText('In sync with the form')
  await page.getByRole('tab', { name: 'Form' }).click()
  await expect(page.getByLabel('Question q1 instructions')).toHaveValue('Edited in JSON?')
  await expect(page.getByLabel('Severity')).toHaveValue('high')
  await expect(page.getByLabel('Escalate at')).toHaveValue('0.3')
  await expect(page.getByRole('checkbox', { name: 'reason' }).last()).toBeChecked()
})

test('keyboard-only: create a rule without the mouse', async ({ page, consoleErrors }) => {
  void consoleErrors
  await page.goto('/rules/new')
  await page.getByLabel('Name', { exact: true }).focus()
  await page.keyboard.type(`Keyboard rule ${Date.now()}`)
  // Tab through to the question instructions and type.
  for (let i = 0; i < 60; i++) {
    await page.keyboard.press('Tab')
    const label = await page.evaluate(() => document.activeElement?.getAttribute('aria-label'))
    if (label === 'Question q1 instructions') break
  }
  await expect(page.getByLabel('Question q1 instructions')).toBeFocused()
  await page.keyboard.type('Is the stated reason vague?')
  for (let i = 0; i < 60; i++) {
    await page.keyboard.press('Tab')
    const text = await page.evaluate(() => document.activeElement?.textContent)
    if (text === 'Create draft') break
  }
  await page.keyboard.press('Enter')
  await expect(page.getByText('○ draft')).toBeVisible()
})

test('refund example rules built in the UI', async ({ page, consoleErrors }) => {
  void consoleErrors
  const suffix = Date.now()

  // Rule 1: deterministic amount > 500 -> escalate, only for issue_refund.
  await page.goto('/rules/new')
  await page.getByLabel('Name', { exact: true }).fill(`Refund over limit ${suffix}`)
  await page.getByLabel('Source text').fill('Refunds over $500 need a manager.')
  await page.getByRole('switch', { name: 'Only when a condition holds' }).click()
  await page.getByLabel('Applies when value', { exact: true }).fill('issue_refund')
  await page.getByRole('switch', { name: 'Use a deterministic check' }).click()
  await page.getByLabel('Deterministic value', { exact: true }).fill('500')
  await page.getByRole('switch', { name: 'Use a Jev check' }).click()
  await page.getByRole('button', { name: 'Create draft' }).click()
  await expect(page.getByText('Created Refund over limit')).toBeVisible()
  await page.getByRole('tab', { name: 'Overview' }).click()
  await expect(page.getByText("request.tool == \"issue_refund\"")).toBeVisible()
  await expect(page.getByText('request.args.amount > 500 → escalate')).toBeVisible()

  // Rule 2: Jev noul on request + history.
  await page.goto('/rules/new')
  await page.getByLabel('Name', { exact: true }).fill(`Refund to different payment method ${suffix}`)
  await page.getByLabel('Source text').fill('Never refund to a different card than the one used for the purchase.')
  await page.getByRole('switch', { name: 'Only when a condition holds' }).click()
  await page.getByLabel('Applies when value', { exact: true }).fill('issue_refund')
  await page.getByRole('checkbox', { name: 'history' }).last().click()
  await page.getByLabel('Question id q1').fill('different_method')
  await page.getByLabel('Question id q1').blur()
  await page.getByLabel('Question different_method instructions').fill(
    'Does this refund send money to a payment method different from the one used for the original purchase?',
  )
  await page.getByLabel('Severity').selectOption('high')
  await page.getByRole('button', { name: 'Create draft' }).click()
  await expect(page.getByText('Created Refund to different payment method')).toBeVisible()

  await page.goto('/rules')
  await expect(page.getByRole('row', { name: new RegExp(`Refund over limit ${suffix}`) })).toContainText('code')
  await expect(page.getByRole('row', { name: new RegExp(`different payment method ${suffix}`) })).toContainText('jev')
  await page.screenshot({ path: 'test-results/05-refund-rules.png', fullPage: true })
})
