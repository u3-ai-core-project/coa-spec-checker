// API 명세서 v1.3의 JSON 스키마에 v1.4 변경안(검토 중, 10.12)을 더해 옮긴 타입입니다. 필드 이름과 값은 명세와 같게 유지합니다.
// v1.4 변경안은 AI 파트 검토 전이라, 확정되면 [v1.4안] 표시한 곳을 명세와 다시 대조합니다.

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
  // [v1.4안] 보류 후속 조치 추가
  | 'request_single_value'
  | 'request_reissue'
  | 'request_correct_coa';

/** [v1.4안] 항목의 예외 사유코드(서버가 작성). 판정이 pass이면 null입니다. */
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
  | 'UNMAPPED_ITEM';

/** [v1.4안] 해결 조건의 종류. 어떤 값을 받으면 항목이 해결되는지 */
export type ResolutionType = 'actual_value' | 'detection_limit' | 'single_value' | 'internal_test' | 'confirm';

/** [v1.4안] 항목의 해결 조건(서버가 작성). condition은 자유 문구입니다(예: "LOD < 5 ppm"). 조건을 만족하는 값이 들어오면 서버가 자동 재판정합니다. */
export interface Resolution {
  type: ResolutionType;
  condition: string | null;
}

/** [v1.4안] 문서 수준 문제. 1개 이상이면 부적합 항목이 없어도 로트 권고는 보류입니다. */
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
  /** [v1.4안] fail, undetermined, missing, check 항목에 서버가 채웁니다. 나머지는 null입니다. */
  reason_code: ReasonCode | null;
  /** [v1.4안] reason_code가 있는 항목의 해결 조건. 없으면 null입니다. */
  resolution: Resolution | null;
  confidence: number | null;
  bbox: Bbox | null;
}

export interface ExtractionResult {
  document_id: string;
  supplier: string;
  lot_no: string;
  test_date: string | null;
  origin: string | null;
  applied_standard: string | null;
  items: ExtractionItem[];
  /** [v1.4안] 문서 수준 문제. 없으면 빈 배열(응답에 없으면 HttpApi가 빈 배열로 채웁니다). */
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
  spec_grade: string;
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
  normalized_name?: string;
}

export interface ReviewLog {
  item_id: string;
  action: ReviewAction;
  before_value: string;
  after_value: string;
  reviewer_name: string;
  reviewed_at: string;
  /**
   * 수정 사유. API에는 이 필드가 없어 화면(목업) 쪽에서만 붙입니다.
   * TODO(백엔드 협의): 수정 사유 필드가 생기면 서버 응답을 그대로 씁니다.
   */
  reason?: string | null;
}

export interface PatchItemResult {
  item: {
    item_id: string;
    normalized_name: string;
    converted_value: number | string | null;
    value_qualifier: string;
    judgement: Judgement;
    judgement_reason: string | null;
    deviation: number | null;
  };
  lot_recommendation: LotRecommendation;
  summary: JudgementSummary;
  review_logs: Array<Omit<ReviewLog, 'item_id'>>;
}

export interface ConfirmItemResult {
  item: { item_id: string; judgement: Judgement; judgement_reason: string | null };
  lot_recommendation: LotRecommendation;
  review_log: Omit<ReviewLog, 'item_id'>;
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
  follow_up: HoldFollowUp | string | null;
  user_name: string;
  reason: string | null;
  created_at: string;
}

/** [v1.4안] lot_mismatch, issued_before_test는 문서 수준 문제(document_issues)로 옮겼습니다. 남는 것은 참고 경고입니다. */
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
  unit: string;
  lsl: number | null;
  usl: number | null;
  spec_type: '정량' | '정성';
  grade: string | null;
  /** [v1.4안] 규격 버전(예: YS/T 582-2023) */
  version: string | null;
  /** [v1.4안] 필수 시험 항목인지. 필수 항목이 CoA에 없으면 누락(MISSING_REQUIRED)입니다. */
  is_required: boolean;
  source: string | null;
  updated_by: string | null;
  updated_at: string | null;
}

export interface PatchSpecBody {
  lsl: number | null;
  usl: number | null;
  unit: string;
  /** [v1.4안] true이면 처분 전 문서를 새 규격으로 다시 판정하고, 판정이 바뀐 문서 목록을 돌려줍니다. */
  rejudge?: boolean;
}

/**
 * PATCH /specs/{id} 응답. 수정된 규격 항목입니다.
 * [v1.4안] rejudge=true일 때 "판정이 바뀐 문서 목록"이 함께 오지만 명세에 응답 형식이 없습니다.
 * TODO(백엔드 협의): 필드 이름과 모양이 정해지면 맞춥니다. 지금은 document_id만 가정한 rejudged_documents로 받습니다.
 */
export type PatchSpecResult = SpecItem & { rejudged_documents?: Array<{ document_id: string }> };

/** 공통 에러 응답의 error 필드 */
export interface ApiErrorBody {
  code: string;
  message: string;
}
