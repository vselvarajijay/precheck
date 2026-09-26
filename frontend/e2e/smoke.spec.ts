import { expect, test } from '@playwright/test'

test('shell renders nav and API health badge', async ({ page }) => {
  const errors: string[] = []
  page.on('console', (msg) => msg.type() === 'error' && errors.push(msg.text()))
  await page.goto('/')
  await expect(page).toHaveURL(/\/rules$/)
  for (const label of ['Rules', 'Playground', 'Tests', 'Settings']) {
    await expect(page.getByRole('link', { name: label })).toBeVisible()
  }
  await expect(page.getByTestId('health-badge')).toContainText('API ok')
  expect(errors).toEqual([])
})
