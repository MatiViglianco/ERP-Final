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
  const detectedMovements = page.getByRole('heading', { name: 'Movimientos detectados' }).locator('..')
  await expect(detectedMovements.getByText('Transferencia bancaria')).toBeVisible()
  await expect(detectedMovements.getByText('Efectivo por gastos')).toBeVisible()
  await expect(page.getByText('Cuenta corriente: Retiro cuenta corriente empleado')).toBeVisible()
  await expect(page.getByRole('heading', { name: '$ 69.000' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Pendientes de identificar' })).toBeVisible()
  await expect(page.getByRole('cell', { name: 'Cuenta corriente - Facturacion, Cliente: Venta E2E cuenta corriente' })).toBeVisible()
  const transferRow = page.getByRole('row').filter({ hasText: 'PEREZ JUAN PRUEBA' })
  await expect(transferRow).toBeVisible()
  await transferRow.getByRole('combobox').click()
  await page.getByRole('option', { name: 'Juan Interno E2E' }).click()
  await transferRow.getByRole('button', { name: 'Asignar' }).click()
  await expect(page.getByText('Movimiento asignado a Juan Interno E2E')).toBeVisible()
  await expect(page.getByRole('cell', { name: 'Juan Interno E2E', exact: true }).first()).toBeVisible()
  await expect(page.getByText(/movimientos pendientes de identificar/)).toBeVisible()
})

test('mantiene utilizable sueldos en pantalla movil', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('login')
  await page.getByLabel('Usuario').fill('e2eadmin')
  await page.getByLabel(/Contrase/).fill('e2eadmin123')
  await page.getByRole('button', { name: 'Ingresar' }).click()
  await page.goto('/ERP-Final/#/sueldos')

  await expect(page.getByRole('heading', { name: 'Sueldos' })).toBeVisible()
  await expect(page.getByText('Total empleados')).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Pendientes de identificar' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Asignar' }).first()).toBeVisible()
  const viewportHasNoOverflow = await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)
  expect(viewportHasNoOverflow).toBe(true)
})
