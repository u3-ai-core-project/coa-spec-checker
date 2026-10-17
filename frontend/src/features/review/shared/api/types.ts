// API 명세서 v1.3의 JSON 스키마를 그대로 옮긴 타입입니다. 필드 이름과 값은 명세와 같게 유지합니다.

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
  | 'other';

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

export type AnomalyType =
  | 'lot_mismatch'
  | 'spec_text_as_result'
  | 'identical_values'
  | 'at_spec_limit'
  | 'issued_before_test';

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
  source: string | null;
  updated_by: string | null;
  updated_at: string | null;
}

export interface PatchSpecBody {
  lsl: number | null;
  usl: number | null;
  unit: string;
}

/** 공통 에러 응답의 error 필드 */
export interface ApiErrorBody {
  code: string;
  message: string;
}
