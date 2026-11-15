/** 항목 매핑 수정 다이얼로그의 선택지 한 줄. note는 이름 옆에 회색으로 보여 주는 보조 표기(단위, 영문명, 한글명 등)입니다. */
export interface MappingOption {
  name: string;
  note: string;
  /** 검색어가 이 중 하나를 포함하면 후보로 보여 줍니다(소문자 비교). */
  keywords?: readonly string[];
}

/**
 * 목업 전용 표준 항목 후보(시안 2-9). 규격 목업(7개 항목)은 그대로 두고, 다이얼로그에서만 보여 주는 후보입니다.
 * 실제 API에서는 GET /specs의 항목명만 선택지가 되므로(USE_MOCK=false이면 쓰지 않음) 이 목록은 쓰이지 않습니다.
 * 규격에 없는 이름이라 고른 뒤 "매핑 적용"을 누르면 목업도 서버처럼 400 UNKNOWN_ITEM_NAME으로 거절합니다.
 */
export const MOCK_MAPPING_CANDIDATES: readonly MappingOption[] = [
  { name: '중금속 총량', note: 'Heavy metals, total', keywords: ['중금속', 'heavy metal'] },
  { name: 'Pb', note: '납', keywords: ['중금속', 'heavy metal', 'lead'] },
  { name: 'As', note: '비소', keywords: ['중금속', 'heavy metal', 'arsenic'] },
  { name: 'Cd', note: '카드뮴', keywords: ['중금속', 'heavy metal', 'cadmium'] },
];
