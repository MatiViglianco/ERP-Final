import { expect, test } from '@playwright/test'

test('factura deuda de cuenta corriente y actualiza el tablero', async ({ page }) => {
  await page.goto('login')

  await page.getByLabel('Usuario').fill('e2eadmin')
  await page.getByLabel(/Contrase/).fill('e2eadmin123')
  await page.getByRole('button', { name: 'Ingresar' }).click()

  await expect(page.getByText('Viglianco ERP')).toBeVisible()
  await page.getByRole('banner').getByRole('link', { name: 'Facturacion' }).click()

  await expect(page.getByRole('heading', { name: 'Facturacion' })).toBeVisible()
  await expect(page.getByText('Facturado ARCA')).toBeVisible()

  await page.getByLabel('Sucursal a facturar').click()
  await page.getByRole('option', { name: 'E2E Central' }).click()
  await page.getByLabel('Cliente').fill('Facturacion')
  await page.getByRole('option', { name: /Cliente,? Facturacion|Facturacion,? Cliente/ }).click()

  await expect(page.getByText('Venta E2E cuenta corriente')).toBeVisible()
  await expect(page.getByText('Pendiente para facturar: $ 3.210')).toBeVisible()

  await page.getByRole('button', { name: /Facturar \$ 3\.210/ }).click()

  await expect(page.getByRole('alert')).toContainText('Factura creada')
  await expect(page.getByText('Autorizada')).toBeVisible()
  await expect(page.getByRole('cell', { name: 'E2E Central' })).toBeVisible()
  await expect(page.getByText('No hay movimientos pendientes para facturar.')).toBeVisible()
})
