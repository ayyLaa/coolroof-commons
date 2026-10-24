import { expect, test } from '@playwright/test'

test('the browser uploads all scenarios, shows no fake transaction, and explains an unfunded reset', async ({
  page,
}) => {
  await page.goto('/demo')
  await expect(page.getByText('Local chain · 31337', { exact: true })).toBeVisible()
  await page.getByRole('switch', { name: 'Fast mode' }).check()

  await page.getByRole('button', { name: 'Successful intervention (ATH-0142)' }).click()
  const summary = page.getByTestId('demo-summary')
  await expect(summary).toContainText('Payment released', { timeout: 60_000 })
  await expect(summary).toContainText('0.0006 POL')
  await expect(summary.getByRole('link', { name: /View on explorer/ })).toHaveCount(1)

  await page.getByRole('button', { name: 'Poor coating (ATH-0287)' }).click()
  await expect(summary).toContainText('Not submitted', { timeout: 60_000 })
  await expect(summary).toContainText('0 POL paid')
  await expect(summary.getByRole('link', { name: /View on explorer/ })).toHaveCount(0)
  await expect(summary).not.toContainText('Transaction in block')

  await page.getByRole('button', { name: 'Storm scenario (ATH-0355)' }).click()
  await expect(summary).toContainText('Payment released', { timeout: 60_000 })
  await expect(summary).toContainText('0.0001 POL')
  await expect(page.getByTestId('demo-step-7')).toContainText('24 m/s')
  await expect(page.getByTestId('demo-step-7')).toContainText('68 mm')

  await page.getByRole('button', { name: 'Reset backend data' }).click()
  await expect(page.getByTestId('unfunded-round')).toBeVisible()
  await expect(summary).toHaveCount(0)
})
