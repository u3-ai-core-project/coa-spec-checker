/** 값 문자열을 숫자로 바꿉니다. 비어 있거나 숫자가 아니면 null입니다. */
export function parseValue(text: string): number | null {
  const normalized = text.replace(/,/g, '').trim();
  if (normalized === '') return null;
  const value = Number(normalized);
  return Number.isFinite(value) ? value : null;
}
