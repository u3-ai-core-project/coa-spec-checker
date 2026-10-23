const pad = (n: number) => String(n).padStart(2, '0');

/** ISO 8601 문자열을 한국 시간(KST) 기준 부분으로 나눕니다. */
function kstParts(iso: string): { y: number; mo: number; d: number; h: number; mi: number } | null {
  const time = new Date(iso).getTime();
  if (Number.isNaN(time)) return null;
  const kst = new Date(time + 9 * 60 * 60 * 1000);
  return {
    y: kst.getUTCFullYear(),
    mo: kst.getUTCMonth() + 1,
    d: kst.getUTCDate(),
    h: kst.getUTCHours(),
    mi: kst.getUTCMinutes(),
  };
}

/** 2026-10-05 14:32 */
export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return '-';
  const p = kstParts(iso);
  if (!p) return iso;
  return `${p.y}-${pad(p.mo)}-${pad(p.d)} ${pad(p.h)}:${pad(p.mi)}`;
}

/** 10-05 14:32 */
export function formatShortDateTime(iso: string | null | undefined): string {
  if (!iso) return '-';
  const p = kstParts(iso);
  if (!p) return iso;
  return `${pad(p.mo)}-${pad(p.d)} ${pad(p.h)}:${pad(p.mi)}`;
}

/** 2026-10-05 */
export function formatDate(iso: string | null | undefined): string {
  if (!iso) return '-';
  if (/^\d{4}-\d{2}-\d{2}$/.test(iso)) return iso;
  const p = kstParts(iso);
  if (!p) return iso;
  return `${p.y}-${pad(p.mo)}-${pad(p.d)}`;
}

/** 숫자를 불필요한 소수점 0 없이 표시합니다. 25.60 → 25.6 */
export function formatNumber(value: number): string {
  return Number.isInteger(value) ? String(value) : String(Number(value.toFixed(6)));
}
