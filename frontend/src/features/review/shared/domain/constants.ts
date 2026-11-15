/**
 * 신뢰도 "낮음" 기준값. 서버 설정값 LOW_CONFIDENCE_THRESHOLD와 같은 값입니다(API 명세 1장).
 * confidence가 이 값 미만이면 서버가 판정을 check로 바꾸고, 승인 가능 여부도 이 기준으로 판단합니다.
 */
export const LOW_CONFIDENCE_THRESHOLD = 0.8;

/**
 * 사내 규격에 없어 판정하지 않고 참고로만 기록한 항목의 판정 근거 문구(서버 REASON_NO_SPEC).
 * 이 문구이면서 reason_code가 없는 항목이 "참고 항목"입니다.
 */
export const REASON_NO_SPEC = '규격 없음';

/**
 * 신뢰도 "높음/보통" 경계. 명세에 정해진 값이 없어 임시로 0.9를 씁니다.
 */
export const HIGH_CONFIDENCE_THRESHOLD = 0.9;

/**
 * AI 문의 초안(follow-ups?draft=ai) 요청의 클라이언트 타임아웃. 서버는 최대 3분(180초)까지 걸릴 수 있어
 * 그보다 조금 길게 기다립니다.
 */
export const AI_DRAFT_TIMEOUT_MS = 200_000;

/**
 * 원본 근거 좌표(bbox)의 단위. 페이지 크기 대비 0~1 비율, 원점은 좌상단, page는 1부터입니다(백엔드 확정 답변).
 */
export const BBOX_UNIT = 'ratio' as const;

/** 원자재 구분. 규격 관리와 검수 화면은 현재 탄산리튬만 다룹니다. */
export const DEFAULT_MATERIAL_CODE = 'LI2CO3';

/**
 * 검수 화면의 주소 기준. 공통 레이아웃의 메뉴(src/navigation.ts)가 검수를 /inspection으로 정해 두어 같게 씁니다.
 * 목록은 REVIEW_PATH, 상세는 REVIEW_PATH/:documentId입니다.
 */
export const REVIEW_PATH = '/inspection';

/** 검수 화면의 이전/다음 이동 기준 목록 (API 명세 4.5). 완료된 문서는 이 목록에 없습니다. */
export const REVIEW_QUEUE_STATUS = 'extracted,in_review,on_hold';
