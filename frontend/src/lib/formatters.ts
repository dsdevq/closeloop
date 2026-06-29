export function money(value: number | null | undefined): string {
  return `$${Number(value || 0).toLocaleString('en-US', {
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  })}`;
}

export function numberText(value: number | null | undefined): string {
  return Number(value || 0).toLocaleString('en-US');
}
