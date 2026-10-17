import type { SpecItem } from '../shared/api/types';
import { withEuro } from './completion';

/**
 * 항목 매핑 수정의 선택지. 사내 규격에 없는 항목명으로 고치면 서버가 400 UNKNOWN_ITEM_NAME으로 거절하므로,
 * 선택지는 GET /specs의 항목명으로만 만듭니다. 검색어는 항목명과 단위에서 찾습니다(대소문자 구분 없음).
 */
export function filterSpecOptions(specs: SpecItem[], query: string): SpecItem[] {
  const needle = query.trim().toLowerCase();
  if (!needle) return specs;
  return specs.filter((spec) => `${spec.item_name} ${spec.unit}`.toLowerCase().includes(needle));
}

/**
 * 원문 표기가 "(as Pb)"처럼 환산 기준을 붙인 합계 표기이면 그 원소 이름을 돌려줍니다. 아니면 null입니다.
 * 이런 표기는 단일 원소가 아닌 합계 항목일 수 있어 매핑 수정 때 안내합니다.
 */
export function asElementOf(rawName: string | null): string | null {
  if (!rawName) return null;
  const match = /\(\s*as\s+([A-Za-z][A-Za-z0-9]*)\s*\)/i.exec(rawName);
  return match ? match[1] : null;
}

const ELEMENT_KO: Record<string, string> = { Pb: '납', As: '비소', Cd: '카드뮴', Hg: '수은', Cr: '크롬' };

/**
 * 원문 표기가 "(as Pb)"처럼 환산 기준이 붙은 합계 표기일 때 매핑 수정에서 보여 주는 안내 문구(시안 2-9).
 * 규격에 "총량" 항목이 있으면 그 항목으로 매핑하라고 안내합니다. 해당 표기가 아니면 null입니다.
 */
export function mappingHint(rawName: string | null, specs: SpecItem[]): string | null {
  const element = asElementOf(rawName);
  if (!element) return null;
  const korean = ELEMENT_KO[element];
  const total = specs.find((spec) => spec.item_name.includes('총량'))?.item_name;
  const sum = korean ? `‘as ${element}’는 ${withEuro(korean)} 환산한 합계 표기이며 ${element} 단일 원소가 아닙니다.` : `‘as ${element}’는 ${element} 환산 합계 표기이며 ${element} 단일 원소가 아닙니다.`;
  return total ? `${sum} ${withEuro(total)} 매핑하는 것이 적합합니다.` : sum;
}
