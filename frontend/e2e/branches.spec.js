import { expect, test } from '@playwright/test'

test('filtra cuenta corriente por sucursal', async ({ page }) => {
  await page.goto('login')

  await page.getByLabel('Usuario').fill('e2eadmin')
  await page.getByLabel(/Contrase/).fill('e2eadmin123')
  await page.getByRole('button', { name: 'Ingresar' }).click()

  await expect(page.getByText('Viglianco ERP')).toBeVisible()
  await page.getByRole('banner').getByRole('link', { name: 'Cuenta corriente' }).click()

  await expect(page.getByRole('heading', { name: 'Clientes' })).toBeVisible()
  await page.getByLabel('Sucursal').selectOption({ label: 'E2E Central' })
  await page.getByPlaceholder('Buscar cliente...').fill('Facturacion')

  await expect(page.getByText('Facturacion, Cliente')).toBeVisible()
  await expect(page.getByText('Deuda: $ 3.210')).toBeVisible()

  await page.getByLabel('Sucursal').selectOption({ label: 'E2E Norte' })
  await expect(page.getByText('Facturacion, Cliente')).toHaveCount(0)
})
