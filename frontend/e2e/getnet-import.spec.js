import { expect, test } from '@playwright/test'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const dirname = path.dirname(fileURLToPath(import.meta.url))

test('importa Getnet y muestra la terminal separada en facturacion', async ({ page }) => {
  await page.goto('login')

  await page.getByLabel('Usuario').fill('e2eadmin')
  await page.getByLabel(/Contrase/).fill('e2eadmin123')
  await page.getByRole('button', { name: 'Ingresar' }).click()

  await expect(page.getByText('Viglianco ERP')).toBeVisible()
  await page.getByRole('banner').getByRole('link', { name: 'Cargar' }).click()
  await expect(page.getByRole('heading', { name: 'Cargar datos' })).toBeVisible()
  await page.getByTestId('getnet-csv-input').setInputFiles(path.join(dirname, 'fixtures', 'getnet-transactions.csv'))

  const getnetCard = page.getByRole('heading', { name: 'Transacciones Getnet (CSV)' }).locator('..')
  await getnetCard.getByLabel('Sucursal').click()
  await page.getByRole('option', { name: 'E2E Central' }).click()
  await page.getByRole('button', { name: 'Subir transacciones Getnet' }).click()

  await expect(page.getByRole('alert')).toContainText('Importacion Getnet completada: 1 nuevas, 0 actualizadas')

  await page.getByRole('banner').getByRole('link', { name: 'Facturacion' }).click()
  await expect(page.getByRole('heading', { name: 'Facturacion' })).toBeVisible()
  await expect(page.getByRole('cell', { name: 'AR0E2E01', exact: true }).first()).toBeVisible()
  await expect(page.getByText('Getnet $ 12.345')).toBeVisible()
})
