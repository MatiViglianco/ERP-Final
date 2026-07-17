import { expect, test } from '@playwright/test'

test('retira ventas de la navegacion y redirige enlaces anteriores', async ({ page }) => {
  await page.goto('login')

  await page.getByLabel('Usuario').fill('e2eadmin')
  await page.getByLabel(/Contrase/).fill('e2eadmin123')
  await page.getByRole('button', { name: 'Ingresar' }).click()

  await expect(page.getByText('Viglianco ERP')).toBeVisible()
  await expect(page.getByRole('banner').getByRole('link', { name: 'Ventas' })).toHaveCount(0)
  await expect(page.getByRole('contentinfo').getByRole('link', { name: 'Ventas' })).toHaveCount(0)

  await page.goto('ventas')
  await expect(page).toHaveURL(/#\/balanza$/)
  await expect(page.getByRole('heading', { name: 'Estadísticas' })).toBeVisible()
})
