import { expect, test } from '@playwright/test'

test('muestra sueldos por transferencias efectivo y cuenta corriente', async ({ page }) => {
  await page.goto('login')

  await page.getByLabel('Usuario').fill('e2eadmin')
  await page.getByLabel(/Contrase/).fill('e2eadmin123')
  await page.getByRole('button', { name: 'Ingresar' }).click()

  await expect(page.getByText('Viglianco ERP')).toBeVisible()
  await page.getByRole('banner').getByRole('link', { name: 'Sueldos' }).click()

  await expect(page.getByRole('heading', { name: 'Sueldos' })).toBeVisible()
  await expect(page.getByText('Total empleados')).toBeVisible()
  await expect(page.getByRole('cell', { name: 'Diego E2E', exact: true }).first()).toBeVisible()
  await expect(page.getByText('Transferencia bancaria')).toBeVisible()
  await expect(page.getByText('Efectivo por gastos')).toBeVisible()
  await expect(page.getByText('Cuenta corriente: Retiro cuenta corriente empleado')).toBeVisible()
  await expect(page.getByRole('heading', { name: '$ 69.000' })).toBeVisible()
})
