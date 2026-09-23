import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

/** Tailwind sınıflarını koşullu birleştirir; çakışanlarda sonuncu kazanır. */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

/** Dolar cinsinden tutarı biçimlendirir (ör. 1234.5 -> "$1,235"). */
export function formatCurrency(value: number, currency: string = 'USD'): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: currency.toUpperCase(),
    maximumFractionDigits: 0,
  }).format(value)
}

/** Büyük sayıları kısaltır (ör. 1200 -> "1.2K", 3400000 -> "3.4M"). */
export function formatCompactNumber(value: number): string {
  return new Intl.NumberFormat('en-US', {
    notation: 'compact',
    maximumFractionDigits: 1,
  }).format(value)
}
