import type { DocumentDetail } from '../api/types';

/**
 * 문서의 로트번호 표시. 서버가 복수 로트(is_multi_lot)라고 하면 lot_no는 null이라 lot_nos 전체를 쉼표로 보여 주고 배지를 붙입니다.
 * 판정은 서버가 하고 화면은 표시만 합니다. 새 필드가 없으면 예전처럼 lot_no(없으면 "-")입니다.
 */
export function lotDisplay(doc: Pick<DocumentDetail, 'lot_no' | 'lot_nos' | 'is_multi_lot'>): { text: string; multi: boolean } {
  const multi = doc.is_multi_lot === true;
  if (multi && doc.lot_nos && doc.lot_nos.length > 0) return { text: doc.lot_nos.join(', '), multi };
  return { text: doc.lot_no ?? '-', multi };
}
