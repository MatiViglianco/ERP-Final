import { useEffect, useMemo, useState } from 'react'

export const MONTHS = [
  'Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
  'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre',
].map((label, index) => ({ value: String(index + 1), label }))

export const VAT_RATES = [
  { value: '10.5', label: 'IVA 10,5%' },
  { value: '21', label: 'IVA 21%' },
]

export const PAYMENT_SOURCES = [
  { value: 'getnet', label: 'Getnet' },
  { value: 'santander', label: 'Santander' },
  { value: 'bancon', label: 'Bancor' },
  { value: 'transfer', label: 'Transferencia' },
  { value: 'cash', label: 'Efectivo' },
  { value: 'manual', label: 'Manual' },
]

export const INVOICE_STATUSES = [
  { value: 'authorized', label: 'Autorizada' },
  { value: 'cancelled', label: 'Anulada' },
  { value: 'error', label: 'Error' },
  { value: 'rejected', label: 'Rechazada' },
  { value: 'draft', label: 'Borrador' },
]

export const INVOICE_SOURCES = [
  { value: 'getnet', label: 'Posnet' },
  { value: 'manual', label: 'Manual' },
  { value: 'account', label: 'Cuenta corriente' },
]

const VOUCHER_LETTERS = { 1: 'A', 3: 'NC A', 6: 'B', 8: 'NC B', 11: 'C', 13: 'NC C' }
const CREDIT_NOTE_TYPES = new Set([3, 8, 13])
export const RETRYABLE_STATUSES = new Set(['error', 'rejected', 'draft'])

const integerFormatter = new Intl.NumberFormat('es-AR', { minimumFractionDigits: 0, maximumFractionDigits: 0 })
const moneyFormatter = new Intl.NumberFormat('es-AR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })

// Montos redondeados, para indicadores y totales grandes.
export function formatCurrency(value) {
  return `$ ${integerFormatter.format(Number(value || 0))}`
}

// Montos con centavos, para comprobantes fiscales.
export function formatMoney(value) {
  return `$ ${moneyFormatter.format(Number(value || 0))}`
}

export function formatDate(value) {
  if (!value) return '-'
  const [year, month, day] = String(value).slice(0, 10).split('-')
  return day && month && year ? `${day}/${month}/${year}` : String(value)
}

export function currentIsoDate() {
  return new Date().toISOString().split('T')[0]
}

export function isCreditNote(invoice) {
  return Boolean(invoice?.is_credit_note) || CREDIT_NOTE_TYPES.has(invoice?.voucher_type)
}

export function formatVoucher(invoice) {
  if (!invoice?.voucher_number) return 'Sin numero'
  const letter = VOUCHER_LETTERS[invoice.voucher_type] || invoice.voucher_type
  const pos = String(invoice.point_of_sale || 0).padStart(5, '0')
  const number = String(invoice.voucher_number).padStart(8, '0')
  return `${letter} ${pos}-${number}`
}

export function invoiceClientLabel(invoice) {
  if (invoice?.client_name) return invoice.client_name
  return ['getnet', 'manual'].includes(invoice?.source) ? 'Consumidor final' : '-'
}

export function statusColor(status) {
  if (['authorized', 'approved', 'reconciled'].includes(status)) return 'success'
  if (['draft', 'pending'].includes(status)) return 'warning'
  if (['needs_review', 'cancelled'].includes(status)) return 'default'
  return 'error'
}

export function arcaModeLabel(arca) {
  if (!arca) return 'Consultando ARCA...'
  if (arca.provider !== 'wsfe') return 'Simulado (sin validez fiscal)'
  if (!arca.ready) return 'ARCA sin conexion'
  return arca.environment === 'produccion' ? 'ARCA produccion' : 'ARCA homologacion (prueba)'
}

export function arcaModeColor(arca) {
  if (!arca || arca.provider !== 'wsfe') return 'default'
  if (!arca.ready) return 'error'
  return arca.environment === 'produccion' ? 'success' : 'warning'
}

export function isRealVoucher(arca) {
  return arca?.provider === 'wsfe' && arca?.environment === 'produccion'
}

// Acepta "1500", "1500.50", "1.500,50" o "1500,50".
export function parseAmount(value) {
  let text = String(value || '').trim().replace(/\s|\$/g, '')
  if (text.includes(',') && text.includes('.') && text.lastIndexOf(',') > text.lastIndexOf('.')) {
    text = text.replace(/\./g, '')
  } else if (/^\d{1,3}(\.\d{3})+$/.test(text)) {
    text = text.replace(/\./g, '') // 1.000.000 sin decimales
  }
  const number = Number(text.replace(',', '.'))
  return Number.isFinite(number) ? number : NaN
}

// Reparte un total en N importes; el ultimo absorbe el redondeo.
export function splitAmount(total, count) {
  const cents = Math.round(total * 100)
  const base = Math.floor(cents / count)
  return Array.from({ length: count }, (_, index) => (
    (index === count - 1 ? cents - base * (count - 1) : base) / 100
  ))
}

export function normalizeText(value) {
  return String(value || '')
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase()
}

// Descarga un CSV compatible con Excel en espanol (separador ";" y BOM UTF-8).
export function downloadCsv(filename, headers, rows) {
  const escapeCell = (value) => {
    const text = value === null || value === undefined ? '' : String(value)
    return /[";\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text
  }
  const lines = [headers, ...rows].map((row) => row.map(escapeCell).join(';'))
  const blob = new Blob([`﻿${lines.join('\r\n')}`], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}

export function csvNumber(value) {
  return Number(value || 0).toFixed(2).replace('.', ',')
}

export const ROWS_PER_PAGE_OPTIONS = [10, 25, 50, 100]

// Paginado del lado del cliente; vuelve a la primera pagina cuando cambian los filtros.
export function useClientPagination(items, resetKey, initialRowsPerPage = 25) {
  const [page, setPage] = useState(0)
  const [rowsPerPage, setRowsPerPage] = useState(initialRowsPerPage)

  useEffect(() => {
    setPage(0)
  }, [resetKey])

  const lastPage = Math.max(0, Math.ceil(items.length / rowsPerPage) - 1)
  const safePage = Math.min(page, lastPage)
  const pageItems = useMemo(
    () => items.slice(safePage * rowsPerPage, safePage * rowsPerPage + rowsPerPage),
    [items, safePage, rowsPerPage],
  )

  return {
    pageItems,
    paginationProps: {
      component: 'div',
      count: items.length,
      page: safePage,
      rowsPerPage,
      rowsPerPageOptions: ROWS_PER_PAGE_OPTIONS,
      onPageChange: (_event, nextPage) => setPage(nextPage),
      onRowsPerPageChange: (event) => {
        setRowsPerPage(Number.parseInt(event.target.value, 10))
        setPage(0)
      },
      labelRowsPerPage: 'Filas por pagina',
      labelDisplayedRows: ({ from, to, count }) => `${from}-${to} de ${count}`,
      getItemAriaLabel: (type) => ({
        first: 'Primera pagina',
        last: 'Ultima pagina',
        next: 'Pagina siguiente',
        previous: 'Pagina anterior',
      })[type],
      showFirstButton: true,
      showLastButton: true,
    },
  }
}
