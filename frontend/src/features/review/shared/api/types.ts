// API 명세서 v1.3의 JSON 스키마에 v1.4(develop에 머지된 백엔드 구현, backend/app/schemas)를 더해 옮긴 타입입니다.
// 필드 이름과 값은 백엔드 스키마와 같게 유지합니다. [v1.4]는 v1.3 명세에 없고 백엔드 구현에서 가져온 부분입니다.

export type Role = 'ADMIN' | 'USER';

/** 항목 판정 5종 */
export type Judgement = 'pass' | 'fail' | 'undetermined' | 'missing' | 'check';

export type MappingSource = 'dictionary' | 'ai' | 'manual' | 'spec';

export type ValueQualifier = 'exact' | 'less_than' | 'less_equal' | 'not_detected' | 'text';

/** 로트 권고 */
export type LotRecommendation = 'approve' | 'hold' | 'reject';

/** 담당자 최종 처분. 보류는 처분이 아니라 on_hold 상태입니다. */
export type FinalDecision = 'accept' | 'conditional_accept' | 'reject';

/** 문서 상태의 기준은 documents.status입니다. JSON의 review_status는 쓰지 않습니다. */
export type DocumentStatus =
  | 'queued'
  | 'processing'
  | 'extracted'
  | 'in_review'
  | 'on_hold'
  | 'approved'
  | 'failed';

export type ReviewAction = 'edit' | 'confirm' | 'rename';
export type ApprovalAction = 'approve' | 'hold' | 'cancel';
export type HoldFollowUp =
  | 'request_actual_value'
  | 'request_detection_limit'
  | 'internal_test'
  | 'other'
  // [v1.4] 보류 후속 조치 추가
  | 'request_single_value'
  | 'request_reissue'
  | 'request_correct_coa';

/** [v1.4] 항목의 예외 사유코드(서버가 작성). 판정이 pass이면 null입니다. 사유코드에서 판정 5종이 정해집니다(백엔드 policy.py). */
export type ReasonCode =
  | 'OUT_OF_SPEC'
  | 'CONVERTED_OOS'
  | 'BOUND_ABOVE_LIMIT'
  | 'ND_NO_LOD'
  | 'SPEC_COPIED'
  | 'MISSING_REQUIRED'
  | 'AMBIGUOUS_ANALYTE'
  | 'SUM_ONLY'
  | 'LOW_CONFIDENCE'
  | 'UNMAPPED_ITEM'
  // 아래 셋은 명세 v1.4안 목록에 없고 백엔드가 추가했습니다(명세 반영 필요).
  | 'LOD_ABOVE_LIMIT'
  | 'LOWER_LIMIT_UNVERIFIABLE'
  | 'UNPARSEABLE_VALUE';

/** [v1.4] 해결 조건의 종류. 어떤 값을 받으면 항목이 해결되는지 */
export type ResolutionType = 'actual_value' | 'detection_limit' | 'single_value' | 'internal_test' | 'confirm';

/**
 * [v1.4] 항목의 해결 조건(서버가 작성). condition은 화면, 리포트, 문의 초안에 쓰는 문구이고,
 * operator, threshold, unit은 서버가 회신값이 조건을 만족하는지 비교할 때 쓰는 값입니다(비교할 수치가 없으면 null).
 * 조건을 만족하는 값이 들어오면 서버가 자동 재판정합니다.
 */
export interface Resolution {
  type: ResolutionType;
  condition: string;
  /** 값을 받아야 하는 항목(예: 중금속 총량이면 "Pb"). 보통은 이 항목 자신입니다. */
  target_item?: string | null;
  operator?: '<' | '<=' | '>=' | null;
  threshold?: number | null;
  unit?: string | null;
}

/** [v1.4] 담당자가 입력한 값의 출처. correction(원문을 보고 바로잡음, 기본), supplier_reply(공급사 회신값), internal_test(자체 시험값) */
export type ValueSource = 'correction' | 'supplier_reply' | 'internal_test';

/** [v1.4] 문서 수준 문제. 1개 이상이면 부적합 항목이 없어도 로트 권고는 보류입니다. */
export type DocumentIssueCode =
  | 'LOT_MISMATCH'
  | 'PRODUCT_MISMATCH'
  | 'DATE_CONFLICT'
  | 'SUPPLIER_CONFLICT'
  | 'SPEC_VERSION_UNKNOWN';

export interface DocumentIssue {
  code: DocumentIssueCode;
  message: string;
}

export interface JudgementSummary {
  pass: number;
  fail: number;
  undetermined: number;
  missing: number;
  check: number;
}

/** 원본 근거 좌표. 누락 항목(mapping_source = spec)은 항목 전체의 bbox가 null입니다. */
export interface Bbox {
  page: number;
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface ExtractionItem {
  item_id: string;
  raw_name: string | null;
  normalized_name: string;
  mapping_source: MappingSource;
  raw_value: string | null;
  raw_spec: string | null;
  unit: string | null;
  value_qualifier: ValueQualifier | null;
  converted_value: number | string | null;
  detection_limit: number | null;
  spec_lsl: number | null;
  spec_usl: number | null;
  judgement: Judgement;
  judgement_reason: string | null;
  deviation: number | null;
  /** [v1.4] fail, undetermined, missing, check 항목에 서버가 채웁니다. 나머지는 null입니다. */
  reason_code: ReasonCode | null;
  /** [v1.4] reason_code가 있는 항목의 해결 조건. 없으면 null입니다. */
  resolution: Resolution | null;
  confidence: number | null;
  bbox: Bbox | null;
  /** [v1.4] 담당자가 확인(confirm)하거나 값을 입력했는지. 신뢰도 낮음 미처리 판단(처분 가능 여부)의 기준입니다. */
  reviewed: boolean;
  /** [v1.4] 담당자가 값을 입력했으면 그 출처. 원문 값을 쓰는 중이면 null입니다. */
  value_source: ValueSource | null;
}

export interface ExtractionResult {
  document_id: string;
  supplier: string;
  lot_no: string;
  test_date: string | null;
  origin: string | null;
  applied_standard: string | null;
  /** [v1.4] AI가 CoA에서 읽은 값(제품 불일치, 날짜 충돌 판단용) */
  product_name?: string | null;
  issue_date?: string | null;
  expiry_date?: string | null;
  retest_date?: string | null;
  items: ExtractionItem[];
  /** [v1.4] 문서 수준 문제. 없으면 빈 배열(응답에 없으면 HttpApi가 빈 배열로 채웁니다). */
  document_issues: DocumentIssue[];
  lot_recommendation: LotRecommendation;
  summary: JudgementSummary;
  /** 호환용 필드입니다. 화면은 documents.status를 씁니다. */
  review_status: 'pending' | 'in_review' | 'on_hold' | 'approved';
}

export interface AuthUser {
  id: number;
  username?: string;
  name: string;
  role: Role;
}

export interface LoginResult {
  access_token: string;
  token_type: string;
  expires_in: number;
  user: { id: number; name: string; role: Role };
}

export interface DocumentListQuery {
  /** 쉼표로 여러 개 지정할 수 있습니다. 예: extracted,in_review,on_hold */
  status?: string;
  lot_recommendation?: LotRecommendation;
  uploaded_by?: number;
  page?: number;
  size?: number;
}

export interface DocumentListItem {
  document_id: string;
  file_name: string;
  file_size: number;
  supplier: string;
  material_name: string;
  lot_no: string | null;
  status: DocumentStatus;
  lot_recommendation: LotRecommendation | null;
  final_decision: FinalDecision | null;
  summary: JudgementSummary | null;
  uploaded_by: string;
  uploaded_at: string;
  approved_by: string | null;
  approved_at: string | null;
  error_message: string | null;
}

export interface DocumentListResult {
  total: number;
  items: DocumentListItem[];
}

export interface DocumentDetail {
  document_id: string;
  file_name: string;
  supplier: string;
  material_code: string;
  material_name: string | null;
  po_no: string | null;
  lot_no: string | null;
  received_lot_no: string | null;
  test_date: string | null;
  origin: string | null;
  applied_standard: string | null;
  spec_grade: string | null;
  /** [v1.4] 판정에 쓴 규격 세트(예: LI2CO3-D1-2023)와 규격 버전(예: YS/T 582-2023) */
  spec_set_code: string | null;
  spec_version: string | null;
  status: DocumentStatus;
  lot_recommendation: LotRecommendation | null;
  final_decision: FinalDecision | null;
  decision_reason: string | null;
  error_message: string | null;
  uploaded_by: string;
  uploaded_at: string;
  approved_by: string | null;
  approved_at: string | null;
}

export interface PatchItemBody {
  converted_value?: number | string;
  value_qualifier?: ValueQualifier;
  /** [v1.4] 검출한계(사내 규격 단위). 검출 안 됨(not_detected) 값에만 보냅니다. */
  detection_limit?: number;
  normalized_name?: string;
  /** [v1.4] 입력값 출처. 값을 입력할 때만 보냅니다. 생략하면 correction입니다. */
  value_source?: ValueSource;
  /**
   * 수정 사유(백엔드 확정 답변). 값 수정은 필수이고 항목명만 수정할 때는 선택입니다. review_logs의 reason으로 돌아옵니다.
   * TODO(백엔드 협의): 서버 구현 전이라 요청과 응답의 reason 필드 이름은 가정입니다.
   */
  reason?: string;
}

export interface ReviewLog {
  item_id: string;
  action: ReviewAction;
  before_value: string | null;
  after_value: string | null;
  /** [v1.4] 값 수정(edit)일 때만 있습니다. */
  value_source?: ValueSource | null;
  reviewer_name: string;
  reviewed_at: string;
  /** 수정 사유(백엔드 확정 답변). 값 수정은 필수이고 항목명만 수정한 이력은 없을 수 있습니다. 서버 구현 전이라 필드 이름은 가정입니다. */
  reason?: string | null;
}

/** 수정, 확인 뒤의 항목(백엔드 ReviewedItem). [v1.4] 검출한계, 사유코드, 해결 조건, 검수 상태가 더해졌습니다. */
export interface ReviewedItem {
  item_id: string;
  normalized_name: string;
  converted_value: number | string | null;
  value_qualifier: ValueQualifier | null;
  detection_limit?: number | null;
  judgement: Judgement;
  judgement_reason: string | null;
  deviation: number | null;
  reason_code?: ReasonCode | null;
  resolution?: Resolution | null;
  reviewed?: boolean;
  value_source?: ValueSource | null;
}

export interface PatchItemResult {
  item: ReviewedItem;
  lot_recommendation: LotRecommendation;
  summary: JudgementSummary;
  review_logs: ReviewLog[];
}

export interface ConfirmItemResult {
  item: ReviewedItem;
  lot_recommendation: LotRecommendation;
  summary: JudgementSummary;
  review_log: ReviewLog;
}

export interface ApproveBody {
  decision: FinalDecision;
  reason: string | null;
}

export interface ApproveResult {
  document_id: string;
  status: 'approved';
  lot_recommendation: LotRecommendation;
  final_decision: FinalDecision;
  approved_by: string;
  approved_at: string;
}

export interface HoldBody {
  follow_up: HoldFollowUp;
  reason: string;
}

export interface HoldResult {
  document_id: string;
  status: 'on_hold';
}

export interface CancelApprovalBody {
  reason: string;
}

export interface CancelApprovalResult {
  document_id: string;
  status: 'in_review';
}

export interface ApprovalLog {
  action: ApprovalAction;
  decision: FinalDecision | null;
  follow_up: HoldFollowUp | null;
  user_name: string;
  reason: string | null;
  created_at: string;
}

/** [v1.4] lot_mismatch, issued_before_test는 문서 수준 문제(document_issues)로 옮겼습니다. 남는 것은 참고 경고입니다. */
export type AnomalyType = 'spec_text_as_result' | 'identical_values' | 'at_spec_limit';

export interface Anomaly {
  type: AnomalyType;
  item_name: string | null;
  message: string;
  related_document_ids: string[];
}

export interface SpecItem {
  id: number;
  material_code: string;
  material_name: string;
  item_name: string;
  unit: string | null;
  lsl: number | null;
  usl: number | null;
  spec_type: '정량' | '정성';
  grade: string | null;
  source: string | null;
  updated_by: string | null;
  updated_at: string | null;
  /** [v1.4] 이 항목이 속한 규격 세트(예: LI2CO3-D1-2023) */
  spec_set_code: string;
  /** [v1.4] 규격 버전(예: YS/T 582-2023) */
  version: string | null;
  /** [v1.4] 필수 시험 항목인지. 필수 항목이 CoA에 없으면 누락(MISSING_REQUIRED)입니다. */
  is_required: boolean;
}

/** [v1.4] GET /specs/sets. 원자재별 규격 세트(등급, 버전). 기본 세트가 먼저 옵니다. */
export interface SpecSet {
  code: string;
  material_code: string;
  material_name: string;
  grade: string | null;
  version: string | null;
  source: string | null;
  description: string | null;
  is_default: boolean;
  item_count: number;
}

/** GET /specs 쿼리. [v1.4] spec_set_code가 더해졌습니다. */
export interface SpecListQuery {
  material_code?: string;
  spec_set_code?: string;
}

export interface PatchSpecBody {
  lsl: number | null;
  usl: number | null;
  unit: string;
  /**
   * 변경 사유(백엔드 확정 답변, 필수). 규격 변경 이력(change-logs)에 남습니다.
   * TODO(백엔드 협의): 서버 구현 전이라 필드 이름은 가정입니다.
   */
  reason: string;
}

/** PATCH /specs/{id} 응답. 수정된 규격 항목입니다. 규격 재판정(rejudge)은 서버에 없어 뺐습니다. */
export type PatchSpecResult = SpecItem;

/** 규격 한 항목의 값(변경 전후 비교용) */
export interface SpecValues {
  lsl: number | null;
  usl: number | null;
  unit: string | null;
}

/**
 * GET /specs/{id}/change-logs 의 변경 이력 1건(백엔드 확정 답변: 변경 전후 값, 수정자, 사유, 시각).
 * TODO(백엔드 협의): 서버 구현 전이라 필드 이름과 모양은 가정입니다.
 */
export interface SpecChangeLog {
  id: number;
  spec_id: number;
  item_name: string;
  before: SpecValues;
  after: SpecValues;
  changed_by: string;
  reason: string;
  changed_at: string;
}

export type MappingRecordSource = 'seed' | 'manual';

/**
 * GET /mappings?material_code= 의 매핑 사전 1건(백엔드 확정 답변: 출처 seed/manual, 등록자, 등록일).
 * 사전은 material_code + raw_name 기준이라 협력사 필드가 없습니다.
 * TODO(백엔드 협의): 서버 구현 전이라 필드 이름과 모양은 가정입니다.
 */
export interface MappingRecord {
  id: number;
  material_code: string;
  /** 협력사가 CoA에 적은 표기 */
  raw_name: string;
  /** 사내 표준 항목명 */
  normalized_name: string;
  source: MappingRecordSource;
  created_by: string | null;
  created_at: string | null;
}

/**
 * GET /mappings/conversions 의 단위 환산표 1건(조회 전용, 백엔드 확정 답변).
 * TODO(백엔드 협의): 서버 구현 전이라 필드 이름과 모양은 가정입니다.
 */
export interface UnitConversion {
  id: number | string;
  label: string;
  formula: string;
  factor: string;
}

/** [v1.4] GET /documents/{id}/follow-ups 응답의 후속 조치 1건. 예외 항목 1개 또는 문서 정합성 오류 1개입니다. */
export interface FollowUpLine {
  /** 항목명. 문서 정합성 오류면 "문서" */
  target: string;
  /** 사유코드(reason_code) 또는 문서 정합성 오류 코드 */
  code: string;
  /** 사유 짧은 이름 */
  label: string;
  /** 왜 문제인가(판정 근거) */
  why: string;
  /** 해결 조건(담당자용 문구) */
  condition: string;
  /** CoA 원문 값(근거 인용) */
  raw_value: string | null;
  /** 공급사에 요청할 일인지(false면 내부 확인) */
  to_supplier: boolean;
}

export type InquiryDraftSource = 'template' | 'ai' | 'template_fallback';

export interface InquiryDraft {
  subject: string;
  body: string;
  /** template | ai | template_fallback(AI 실패로 템플릿 사용) */
  source: InquiryDraftSource;
  lot_nos: Array<string | null>;
}

/** 같은 공급사의 처리 중 문서 중 공급사 요청이 있는 것 */
export interface OpenDocument {
  document_id: string;
  lot_no: string | null;
  status: DocumentStatus;
  request_count: number;
}

export interface FollowUpsResponse {
  document_id: string;
  supplier: string | null;
  lot_no: string | null;
  /** 보류 화면의 후속 조치 기본값 추천 */
  suggested_follow_up: HoldFollowUp | null;
  supplier_lines: FollowUpLine[];
  internal_lines: FollowUpLine[];
  /** 이 로트만의 문의 초안. 공급사 요청이 없으면 null */
  draft: InquiryDraft | null;
  /** 같은 공급사의 처리 중 문서(이 문서 포함) */
  open_documents: OpenDocument[];
  /** 같은 공급사의 열린 요청을 메일 1통으로 묶은 초안. 해당 문서가 2건 이상일 때만 */
  combined_draft: InquiryDraft | null;
}

/** 공통 에러 응답의 error 필드 */
export interface ApiErrorBody {
  code: string;
  message: string;
}
