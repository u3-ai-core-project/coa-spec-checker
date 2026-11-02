import { formatNumber } from '../../domain/format';
import { pendingLowConfidenceCount } from '../../domain/items';
import type { Api } from '../Api';
import { ApiError } from '../errors';
import { LocalOnlyStore } from '../localOnly';
import { getToken, handleUnauthorized, setToken } from '../session';
import type {
  Anomaly,
  ApprovalLog,
  ApproveBody,
  ApproveResult,
  AuthUser,
  CancelApprovalBody,
  CancelApprovalResult,
  ConfirmItemResult,
  ConversionsResponse,
  DocumentDetail,
  DocumentListItem,
  DocumentListQuery,
  DocumentListResult,
  DocumentStatus,
  ExtractionItem,
  ExtractionResult,
  FollowUpsOptions,
  FollowUpsResponse,
  HoldBody,
  HoldResult,
  LoginResult,
  MappingDeleted,
  MappingRecord,
  PatchItemBody,
  PatchItemResult,
  PatchSpecBody,
  PatchSpecResult,
  ReviewedItem,
  ReviewLog,
  SpecChangeLog,
  SpecItem,
  SpecListQuery,
  SpecSet,
} from '../types';
import { type MockDoc, type MockState, type MockUser, createMockState } from './fixtures';
import { getFollowUps, MOCK_AI_TIMEOUT_DOCS } from './followUps';
import { buildPdfBlob } from './mockPdf';
import { checkApprove, checkSpecRange, currentOverride, evaluateItem, fmtValue, type ParsedValue, recommendLot, rejudgeItem, summarize } from './serverRules';

const TOKEN_PREFIX = 'mock-token-';
let latencyMs = 120;

/** 테스트에서 지연을 끌 때 씁니다. */
export function setMockLatency(ms: number): void {
  latencyMs = ms;
}

const READY_STATUSES: DocumentStatus[] = ['extracted', 'in_review', 'on_hold', 'approved'];

function delay<T>(value: T): Promise<T> {
  if (latencyMs === 0) return Promise.resolve(value);
  return new Promise((resolve) => setTimeout(() => resolve(value), latencyMs));
}

/** AI 초안 목업의 응답 지연(지연을 끈 테스트에서는 기다리지 않습니다). */
const MOCK_AI_LATENCY_MS = 2500;

function wait(ms: number): Promise<void> {
  return latencyMs === 0 ? Promise.resolve() : new Promise((resolve) => setTimeout(resolve, ms));
}

// 목업 시계: 시안과 같은 시각(수정 14:32, 확인 14:35, 처분 15:02 …)이 나오도록 이력 종류마다 시작 시각을 고정하고,
// 같은 종류가 또 생기면 1분씩 늦춥니다.
type ClockKind = 'edit' | 'confirm' | 'rename' | 'approve' | 'hold' | 'cancel' | 'spec';

const CLOCK_ANCHORS: Record<ClockKind, string> = {
  edit: '2026-10-05T14:32:00+09:00',
  confirm: '2026-10-05T14:35:00+09:00',
  rename: '2026-10-05T14:40:00+09:00',
  approve: '2026-10-05T15:02:00+09:00',
  hold: '2026-10-05T10:40:00+09:00',
  cancel: '2026-10-05T16:10:00+09:00',
  spec: '2026-10-05T11:20:00+09:00',
};
let clockCounts: Partial<Record<ClockKind, number>> = {};

/** 테스트에서 목업 시계를 처음으로 되돌릴 때 씁니다. */
export function resetMockClock(): void {
  clockCounts = {};
}

function now(kind: ClockKind): string {
  const count = clockCounts[kind] ?? 0;
  clockCounts[kind] = count + 1;
  return new Date(Date.parse(CLOCK_ANCHORS[kind]) + count * 60 * 1000).toISOString();
}

/** 오늘 날짜(YYYY-MM-DD). 시계를 흘려 보내지 않습니다. */
function todayText(): string {
  return '2026-10-05';
}

function textOf(value: number | string | null): string {
  if (value === null) return '';
  return typeof value === 'number' ? formatNumber(value) : value;
}

/**
 * 이력(review_logs)에 남길 값 문자열. 담당자가 값을 넣은 적이 없으면 CoA의 해석값(없으면 원문), 넣었으면 그 값입니다.
 * 시안과 같게 숫자에는 단위를 붙이지 않습니다(화면이 단위를 붙입니다). 실제 서버 문자열에는 단위가 들어 있어 화면이 둘 다 처리합니다.
 */
function logValue(item: ExtractionItem, unit: string | null): string {
  if (item.value_source === null) return textOf(item.converted_value) || (item.raw_value ?? '');
  const { value_qualifier: qualifier, converted_value: value, detection_limit: limit } = item;
  if (qualifier === 'not_detected') return limit !== null ? `검출 안 됨 (검출한계 ${fmtValue(limit, unit)})` : '검출 안 됨';
  if (qualifier === 'text' || typeof value === 'string') return String(value);
  const prefix = qualifier === 'less_than' ? '< ' : qualifier === 'less_equal' ? '≤ ' : '';
  return prefix + textOf(value);
}

/** 값 수정 요청(PATCH)의 값 조합을 검사해 판정에 넣을 값으로 바꿉니다. 잘못된 조합은 400 VALIDATION_ERROR입니다(백엔드 ItemUpdateRequest). */
function parseOverride(body: PatchItemBody): ParsedValue {
  const invalid = (message: string) => new ApiError(400, 'VALIDATION_ERROR', message);
  const qualifier = body.value_qualifier ?? (body.converted_value !== undefined ? 'exact' : 'not_detected');
  let value: number | string | null = null;
  if (qualifier === 'exact' || qualifier === 'less_than' || qualifier === 'less_equal') {
    const number = body.converted_value === undefined || body.converted_value === '' ? Number.NaN : Number(body.converted_value);
    if (!Number.isFinite(number)) throw invalid(`value_qualifier=${qualifier} 이면 converted_value는 숫자여야 합니다`);
    value = number;
  } else if (qualifier === 'not_detected') {
    if (body.converted_value !== undefined) throw invalid('검출 안 됨이면 converted_value를 비우고 detection_limit을 보내야 합니다');
  } else if (typeof body.converted_value !== 'string' || !body.converted_value.trim()) {
    throw invalid('value_qualifier=text 이면 converted_value는 문자열이어야 합니다');
  } else {
    value = body.converted_value;
  }
  if (body.detection_limit !== undefined && qualifier !== 'not_detected') throw invalid('detection_limit은 검출 안 됨 값에만 보낼 수 있습니다');
  return { qualifier, value, detectionLimit: body.detection_limit ?? null };
}

/** 서버가 만든 누락 항목 중 담당자가 아직 값을 넣지 않은 것 */
function isUntouchedMissing(item: ExtractionItem): boolean {
  return item.mapping_source === 'spec' && item.value_source === null && !item.reviewed;
}

function toReviewedItem(item: ExtractionItem): ReviewedItem {
  return {
    item_id: item.item_id,
    normalized_name: item.normalized_name,
    converted_value: item.converted_value,
    value_qualifier: item.value_qualifier,
    detection_limit: item.detection_limit,
    judgement: item.judgement,
    judgement_reason: item.judgement_reason,
    deviation: item.deviation,
    reason_code: item.reason_code,
    resolution: item.resolution,
    reviewed: item.reviewed,
    value_source: item.value_source,
  };
}

/**
 * 목업 API. 서버 규칙(판정, 처분 검증, 에러 코드)을 메모리에서 그대로 흉내 냅니다.
 * 화면은 이 클래스를 직접 알지 못하고 Api 인터페이스로만 호출합니다.
 */
export class MockApi implements Api {
  private state: MockState;
  private readonly local = new LocalOnlyStore();

  constructor(state: MockState = createMockState()) {
    this.state = state;
  }

  /** 목업 데이터를 통째로 바꿉니다. 개발용 화면(src/dev)이 시안 비교용 시작 상태를 만들 때만 씁니다. */
  resetState(state: MockState): void {
    this.state = state;
  }

  // --- 인증 -----------------------------------------------------------------

  async login(username: string, password: string): Promise<LoginResult> {
    const user = this.state.users.find((entry) => entry.username === username && entry.password === password);
    if (!user) throw new ApiError(401, 'INVALID_CREDENTIALS', '아이디 또는 비밀번호 불일치');
    const token = `${TOKEN_PREFIX}${user.id}`;
    setToken(token);
    return delay({
      access_token: token,
      token_type: 'bearer',
      expires_in: 3600,
      user: { id: user.id, name: user.name, role: user.role },
    });
  }

  async me(): Promise<AuthUser> {
    const user = this.requireUser();
    return delay({ id: user.id, username: user.username, name: user.name, role: user.role });
  }

  private currentUser(): MockUser | null {
    const token = getToken();
    if (!token || !token.startsWith(TOKEN_PREFIX)) return null;
    const id = Number(token.slice(TOKEN_PREFIX.length));
    return this.state.users.find((entry) => entry.id === id) ?? null;
  }

  private requireUser(): MockUser {
    const user = this.currentUser();
    if (!user) {
      handleUnauthorized();
      throw new ApiError(401, 'UNAUTHORIZED', '토큰 없음, 만료 또는 유효하지 않은 토큰');
    }
    return user;
  }

  // --- 문서 -----------------------------------------------------------------

  async listDocuments(query: DocumentListQuery = {}): Promise<DocumentListResult> {
    this.requireUser();
    const statuses = query.status ? query.status.split(',').map((value) => value.trim()) : null;
    const filtered = this.state.docs
      .filter((doc) => !doc.hidden)
      .filter((doc) => (statuses ? statuses.includes(doc.detail.status) : true))
      .filter((doc) => (query.lot_recommendation ? doc.detail.lot_recommendation === query.lot_recommendation : true))
      .filter((doc) => (query.uploaded_by !== undefined ? doc.uploaderId === query.uploaded_by : true))
      .sort((a, b) => b.detail.uploaded_at.localeCompare(a.detail.uploaded_at));
    const size = query.size ?? 20;
    const page = query.page ?? 1;
    const items = filtered.slice((page - 1) * size, page * size).map((doc) => this.toListItem(doc));
    return delay({ total: filtered.length, items });
  }

  private toListItem(doc: MockDoc): DocumentListItem {
    const { detail } = doc;
    return {
      document_id: detail.document_id,
      file_name: detail.file_name,
      file_size: doc.fileSize,
      supplier: detail.supplier,
      material_name: detail.material_name ?? '',
      lot_no: detail.lot_no,
      status: detail.status,
      lot_recommendation: detail.lot_recommendation,
      final_decision: detail.final_decision,
      summary: doc.extraction ? { ...doc.extraction.summary } : null,
      uploaded_by: detail.uploaded_by,
      uploaded_at: detail.uploaded_at,
      approved_by: detail.approved_by,
      approved_at: detail.approved_at,
      error_message: detail.error_message,
    };
  }

  private findDoc(documentId: string): MockDoc {
    const doc = this.state.docs.find((entry) => entry.detail.document_id === documentId);
    if (!doc) throw new ApiError(404, 'DOCUMENT_NOT_FOUND', '존재하지 않는 document_id');
    return doc;
  }

  private findReadyDoc(documentId: string): MockDoc & { extraction: ExtractionResult } {
    const doc = this.findDoc(documentId);
    if (!doc.extraction || !READY_STATUSES.includes(doc.detail.status)) {
      throw new ApiError(409, 'NOT_READY', '추출이 끝나지 않은 문서');
    }
    return doc as MockDoc & { extraction: ExtractionResult };
  }

  async getDocument(documentId: string): Promise<DocumentDetail> {
    this.requireUser();
    return delay({ ...this.findDoc(documentId).detail });
  }

  async getDocumentFile(documentId: string): Promise<Blob> {
    this.requireUser();
    const doc = this.findDoc(documentId);
    if (!doc.pdf) throw new ApiError(409, 'NOT_READY', '추출이 끝나지 않은 문서');
    return delay(buildPdfBlob(doc.pdf));
  }

  async getExtraction(documentId: string): Promise<ExtractionResult> {
    this.requireUser();
    const doc = this.findReadyDoc(documentId);
    return delay(structuredClone(doc.extraction));
  }

  async patchItem(
    documentId: string,
    itemId: string,
    body: PatchItemBody,
  ): Promise<PatchItemResult> {
    const user = this.requireUser();
    const doc = this.findReadyDoc(documentId);
    this.assertEditable(doc);
    const index = doc.extraction.items.findIndex((entry) => entry.item_id === itemId);
    if (index === -1) throw new ApiError(404, 'ITEM_NOT_FOUND', '문서에 존재하지 않는 item_id');
    let item = doc.extraction.items[index];
    const newLogs: ReviewLog[] = [];

    const specs = this.specsOf(doc);
    const specOf = (name: string) => specs.find((entry) => entry.item_name === name);
    const hasValue = body.converted_value !== undefined || body.value_qualifier !== undefined || body.detection_limit !== undefined;
    const newName = body.normalized_name?.trim() || undefined;
    if (!hasValue && newName === undefined) {
      throw new ApiError(400, 'VALIDATION_ERROR', 'converted_value, detection_limit, normalized_name 중 하나 이상 보내야 합니다');
    }
    if (body.value_source !== undefined && !hasValue) throw new ApiError(400, 'VALIDATION_ERROR', 'value_source는 값을 입력할 때만 보낼 수 있습니다');
    // 수정 사유(백엔드 확정 답변): 값 수정은 필수이고, 항목명만 수정할 때는 선택입니다.
    const reason = body.reason?.trim() || null;
    if (hasValue && reason === null) throw new ApiError(400, 'REASON_REQUIRED', '값 수정은 사유가 필요합니다');

    // ---- 1) 항목명 수정 ----
    if (newName !== undefined && newName !== item.normalized_name) {
      const target = specOf(newName);
      if (!target) throw new ApiError(400, 'UNKNOWN_ITEM_NAME', '사내 규격에 없는 항목명');
      if (item.mapping_source === 'spec') throw new ApiError(400, 'VALIDATION_ERROR', '누락 항목은 항목명을 바꿀 수 없습니다');
      // 백엔드는 이미 같은 이름의 항목이 있으면 400으로 거절하지만, 목업 규격(7개)은 문서 항목이 전부 차지하고 있어
      // 화면의 매핑 수정 흐름(2-9)을 확인할 수 없어서 이 검사는 목업에서 뺐습니다.
      // TODO(백엔드 협의): 목업 규격에 Pb, 중금속 총량이 생기면 이 검사를 되살립니다.
      newLogs.push({
        item_id: itemId,
        action: 'rename',
        before_value: item.normalized_name,
        after_value: target.item_name,
        reviewer_name: user.name,
        reviewed_at: now('rename'),
        reason,
      });
      // 새 규격으로 다시 판정합니다(검수 상태는 유지).
      item = rejudgeItem({ ...item, normalized_name: target.item_name, mapping_source: 'manual' }, target);
      // 서버는 item_mappings에 raw_name → normalized_name을 manual로 누적합니다.
      if (item.raw_name) {
        const existing = this.local
          .listMappings(target.material_code)
          .find((entry) => entry.raw_name === item.raw_name);
        if (existing) this.local.deleteMapping(existing.id);
        this.local.addMapping({
          material_code: target.material_code,
          raw_name: item.raw_name,
          normalized_name: target.item_name,
          source: 'manual',
          created_by: user.name,
          created_at: `${todayText()}T09:00:00+09:00`,
        });
      }
    }

    // ---- 2) 값 수정, 회신값 입력, 검출한계 입력 ----
    const spec = specOf(item.normalized_name);
    if (hasValue) {
      const override = parseOverride(body);
      const before = logValue(item, spec?.unit ?? item.unit);
      item = evaluateItem(item, spec, { override, reviewed: true, valueSource: body.value_source ?? 'correction' });
      newLogs.push({
        item_id: itemId,
        action: 'edit',
        before_value: before,
        after_value: logValue(item, spec?.unit ?? item.unit),
        value_source: item.value_source,
        reviewer_name: user.name,
        reviewed_at: now('edit'),
        reason,
      });
    }

    doc.reviewLogs.push(...newLogs);
    this.commitItem(doc, index, item);
    this.touchStatus(doc);

    return delay({
      item: toReviewedItem(item),
      lot_recommendation: doc.extraction.lot_recommendation,
      summary: { ...doc.extraction.summary },
      review_logs: structuredClone(newLogs),
    });
  }

  async confirmItem(documentId: string, itemId: string): Promise<ConfirmItemResult> {
    const user = this.requireUser();
    const doc = this.findReadyDoc(documentId);
    this.assertEditable(doc);
    const index = doc.extraction.items.findIndex((entry) => entry.item_id === itemId);
    if (index === -1) throw new ApiError(404, 'ITEM_NOT_FOUND', '문서에 존재하지 않는 item_id');
    const item = doc.extraction.items[index];
    if (isUntouchedMissing(item)) throw new ApiError(400, 'VALIDATION_ERROR', '누락 항목은 확인할 값이 없습니다. 값을 입력해 주세요');
    const spec = this.specsOf(doc).find((entry) => entry.item_name === item.normalized_name);
    const value = logValue(item, spec?.unit ?? item.unit);
    const log: ReviewLog = {
      item_id: itemId,
      action: 'confirm',
      before_value: value,
      after_value: value,
      reviewer_name: user.name,
      reviewed_at: now('confirm'),
    };
    doc.reviewLogs.push(log);
    // 확인한 항목은 신뢰도 조건을 빼고 값만으로 다시 판정합니다. 검출한계 미기재, 규격 문구 복사처럼 값 자체가 부족하면 확인해도 예외로 남습니다.
    const judged = evaluateItem(item, spec, { reviewed: true, override: currentOverride(item), valueSource: item.value_source });
    this.commitItem(doc, index, judged);
    this.touchStatus(doc);
    return delay({
      item: toReviewedItem(judged),
      lot_recommendation: doc.extraction.lot_recommendation,
      summary: { ...doc.extraction.summary },
      review_log: structuredClone(log),
    });
  }

  /** 문서에 연결된 규격 세트의 항목. 세트 정보가 없는 문서는 원자재의 모든 항목을 씁니다. */
  private specsOf(doc: MockDoc): SpecItem[] {
    const { spec_set_code: setCode, material_code: materialCode } = doc.detail;
    return this.state.specs.filter((entry) => (setCode ? entry.spec_set_code === setCode : entry.material_code === materialCode));
  }

  /** 항목을 바꾼 뒤 집계, 로트 권고, 문서 헤더를 다시 계산합니다. */
  private commitItem(doc: MockDoc & { extraction: ExtractionResult }, index: number, item: ExtractionItem): void {
    doc.extraction.items[index] = item;
    doc.extraction.summary = summarize(doc.extraction.items);
    doc.extraction.lot_recommendation = recommendLot(doc.extraction.summary, doc.extraction.document_issues.length);
    doc.detail.lot_recommendation = doc.extraction.lot_recommendation;
  }

  /** 문서 상태가 extracted 또는 on_hold이면 in_review로 바꿉니다. */
  private touchStatus(doc: MockDoc & { extraction: ExtractionResult }): void {
    if (doc.detail.status === 'extracted' || doc.detail.status === 'on_hold') {
      doc.detail.status = 'in_review';
      doc.extraction.review_status = 'in_review';
    }
  }

  private assertEditable(doc: MockDoc): void {
    if (doc.detail.status === 'approved') throw new ApiError(409, 'ALREADY_APPROVED', '이미 처분된 문서');
  }

  async getReviewLogs(documentId: string): Promise<ReviewLog[]> {
    this.requireUser();
    const doc = this.findDoc(documentId);
    return delay(structuredClone(doc.reviewLogs));
  }

  async approve(documentId: string, body: ApproveBody): Promise<ApproveResult> {
    const user = this.requireUser();
    const doc = this.findDoc(documentId);
    const extraction = doc.extraction;
    const code = checkApprove({
      status: doc.detail.status,
      recommendation: extraction?.lot_recommendation ?? 'hold',
      pendingLowConfidence: extraction ? pendingLowConfidenceCount(extraction.items) : 0,
      body,
    });
    if (code) {
      const status = code === 'ALREADY_APPROVED' || code === 'NOT_READY' ? 409 : code === 'REASON_REQUIRED' ? 400 : 422;
      throw new ApiError(status, code, code);
    }
    const approvedAt = now('approve');
    doc.detail.status = 'approved';
    doc.detail.final_decision = body.decision;
    doc.detail.decision_reason = body.reason?.trim() || null;
    doc.detail.approved_by = user.name;
    doc.detail.approved_at = approvedAt;
    if (extraction) extraction.review_status = 'approved';
    doc.approvalLogs.push({
      action: 'approve',
      decision: body.decision,
      follow_up: null,
      user_name: user.name,
      reason: body.reason?.trim() || null,
      created_at: approvedAt,
    });
    return delay({
      document_id: documentId,
      status: 'approved',
      lot_recommendation: extraction?.lot_recommendation ?? 'hold',
      final_decision: body.decision,
      approved_by: user.name,
      approved_at: approvedAt,
    });
  }

  async hold(documentId: string, body: HoldBody): Promise<HoldResult> {
    const user = this.requireUser();
    const doc = this.findReadyDoc(documentId);
    this.assertEditable(doc);
    if (!body.reason.trim()) throw new ApiError(400, 'REASON_REQUIRED', '사유 누락');
    doc.detail.status = 'on_hold';
    doc.extraction.review_status = 'on_hold';
    doc.approvalLogs.push({
      action: 'hold',
      decision: null,
      follow_up: body.follow_up,
      user_name: user.name,
      reason: body.reason.trim(),
      created_at: now('hold'),
    });
    return delay({ document_id: documentId, status: 'on_hold' });
  }

  async cancelApproval(documentId: string, body: CancelApprovalBody): Promise<CancelApprovalResult> {
    const user = this.requireUser();
    if (user.role !== 'ADMIN') throw new ApiError(403, 'FORBIDDEN', '권한 없음');
    const doc = this.findDoc(documentId);
    if (doc.detail.status !== 'approved') throw new ApiError(409, 'NOT_APPROVED', '처분되지 않은 문서');
    if (!body.reason.trim()) throw new ApiError(400, 'REASON_REQUIRED', '사유 누락');
    doc.detail.status = 'in_review';
    doc.detail.final_decision = null;
    doc.detail.decision_reason = null;
    doc.detail.approved_by = null;
    doc.detail.approved_at = null;
    if (doc.extraction) doc.extraction.review_status = 'in_review';
    doc.approvalLogs.push({
      action: 'cancel',
      decision: null,
      follow_up: null,
      user_name: user.name,
      reason: body.reason.trim(),
      created_at: now('cancel'),
    });
    return delay({ document_id: documentId, status: 'in_review' });
  }

  async getApprovalLogs(documentId: string): Promise<ApprovalLog[]> {
    this.requireUser();
    return delay(structuredClone(this.findDoc(documentId).approvalLogs));
  }

  async getAnomalies(documentId: string): Promise<Anomaly[]> {
    this.requireUser();
    return delay(structuredClone(this.findDoc(documentId).anomalies));
  }

  // --- 규격 -----------------------------------------------------------------

  async listSpecs(query: SpecListQuery = {}): Promise<SpecItem[]> {
    this.requireUser();
    const specs = this.state.specs
      .filter((entry) => !query.material_code || entry.material_code === query.material_code)
      .filter((entry) => !query.spec_set_code || entry.spec_set_code === query.spec_set_code);
    return delay(structuredClone(specs));
  }

  async listSpecSets(materialCode?: string): Promise<SpecSet[]> {
    this.requireUser();
    const sets = this.state.specSets
      .filter((entry) => !materialCode || entry.material_code === materialCode)
      .map((entry) => ({ ...entry, item_count: this.state.specs.filter((spec) => spec.spec_set_code === entry.code).length }));
    // 원자재별로 기본 세트가 먼저 옵니다.
    sets.sort((a, b) => a.material_code.localeCompare(b.material_code) || Number(b.is_default) - Number(a.is_default));
    return delay(sets);
  }

  async getFollowUps(documentId: string, options: FollowUpsOptions = {}): Promise<FollowUpsResponse> {
    this.requireUser();
    const doc = this.findReadyDoc(documentId);
    if (options.draft !== 'ai') return delay(getFollowUps(doc, this.state.docs, options.draft));
    // AI 초안은 오래 걸립니다(실제 서버는 최대 3분). 목업은 로딩 표시를 볼 수 있을 만큼만 기다립니다.
    await wait(MOCK_AI_LATENCY_MS);
    if (MOCK_AI_TIMEOUT_DOCS.has(documentId)) throw new ApiError(0, 'TIMEOUT', '서버 응답이 너무 오래 걸림');
    return getFollowUps(doc, this.state.docs, 'ai');
  }

  async patchSpec(specId: number, body: PatchSpecBody): Promise<PatchSpecResult> {
    const user = this.requireUser();
    if (user.role !== 'ADMIN') throw new ApiError(403, 'FORBIDDEN', '권한 없음');
    const target = this.state.specs.find((entry) => entry.id === specId);
    if (!target) throw new ApiError(404, 'SPEC_NOT_FOUND', '존재하지 않는 규격 항목');
    if (checkSpecRange(body.lsl, body.usl)) throw new ApiError(400, 'INVALID_SPEC_RANGE', '규격 하한이 상한보다 큼');
    // 변경 사유는 필수입니다(백엔드 PR #12). 검사 순서는 서버와 같게 사유 누락, 범위 오류 순입니다.
    const reason = body.reason?.trim();
    if (!reason) throw new ApiError(400, 'REASON_REQUIRED', '변경 사유가 필요합니다');
    // 이미 추출된 문서의 판정은 바꾸지 않고, 이후 업로드 건부터 적용됩니다(규격 재판정은 서버에 없습니다).
    // 서버처럼 실제로 바뀐 값만 "필드: 값" 문자열로 이력에 남기고, 바뀐 값이 없으면 이력은 남기지 않습니다(수정자와 일시는 갱신).
    const next = { lsl: body.lsl, usl: body.usl, unit: body.unit };
    const changed = (['lsl', 'usl', 'unit'] as const).filter((field) => next[field] !== target[field]);
    const fmt = (value: number | string | null) => (value === null ? '없음' : String(value));
    const beforeValue = changed.map((field) => `${field}: ${fmt(target[field])}`).join(', ');
    const afterValue = changed.map((field) => `${field}: ${fmt(next[field])}`).join(', ');
    target.lsl = body.lsl;
    target.usl = body.usl;
    target.unit = body.unit;
    target.updated_by = user.name;
    target.updated_at = now('spec');
    if (changed.length > 0) {
      this.local.addSpecChangeLog(target.id, {
        before_value: beforeValue,
        after_value: afterValue,
        reason,
        user_name: user.name,
        created_at: target.updated_at,
      });
    }
    return delay({ ...target });
  }

  async listSpecChangeLogs(specId: number): Promise<SpecChangeLog[]> {
    this.requireUser();
    if (!this.state.specs.some((entry) => entry.id === specId)) throw new ApiError(404, 'SPEC_NOT_FOUND', '존재하지 않는 규격 항목');
    return delay(this.local.listSpecChangeLogs(specId));
  }

  // --- 매핑 사전 (5-2) -------------------------------------------------------
  // 응답 모양은 백엔드 PR #12에서 확정된 형식입니다(GET /mappings, DELETE /mappings/{id}, GET /mappings/conversions).

  async listMappings(materialCode: string): Promise<MappingRecord[]> {
    this.requireUser();
    return delay(this.local.listMappings(materialCode));
  }

  async deleteMapping(id: number): Promise<MappingDeleted> {
    const user = this.requireUser();
    if (user.role !== 'ADMIN') throw new ApiError(403, 'FORBIDDEN', '권한 없음');
    if (!this.local.deleteMapping(id)) throw new ApiError(404, 'NOT_FOUND', '존재하지 않는 매핑입니다');
    return delay({ id });
  }

  async getConversions(): Promise<ConversionsResponse> {
    this.requireUser();
    return delay(this.local.getConversions());
  }
}
