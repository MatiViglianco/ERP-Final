import { expect, test } from '@playwright/test'

test('balanza muestra cada sucursal y el total combinado', async ({ page }) => {
  await page.goto('login')

  await page.getByLabel('Usuario').fill('e2eadmin')
  await page.getByLabel(/Contrase/).fill('e2eadmin123')
  await page.getByRole('button', { name: 'Ingresar' }).click()

  await expect(page.getByRole('heading', { name: 'Estadísticas' })).toBeVisible()
  const total = page.getByTestId('stats-total-amount')
  const branchSelector = page.getByRole('combobox', { name: 'Sucursal' })
  await expect(total).toContainText('$ 4.000,00')

  await branchSelector.click()
  await page.getByRole('option', { name: 'E2E Central' }).click()
  await expect(total).toContainText('$ 1.000,00')

  await branchSelector.click()
  await page.getByRole('option', { name: 'E2E Norte' }).click()
  await expect(total).toContainText('$ 3.000,00')

  await branchSelector.click()
  await page.getByRole('option', { name: 'Todas las sucursales' }).click()
  await expect(total).toContainText('$ 4.000,00')
})
