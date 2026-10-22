import { formatNumber } from '../../domain/format';
import { pendingLowConfidenceCount, processedItemIds } from '../../domain/items';
import type { Api, MappingEntry, PatchItemOptions, SpecHistoryEntry, UnitConversion } from '../Api';
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
  DocumentDetail,
  DocumentListItem,
  DocumentListQuery,
  DocumentListResult,
  DocumentStatus,
  ExtractionItem,
  ExtractionResult,
  HoldBody,
  HoldResult,
  LoginResult,
  PatchItemBody,
  PatchItemResult,
  PatchSpecBody,
  PatchSpecResult,
  ReviewLog,
  SpecItem,
} from '../types';
import { type MockDoc, type MockState, type MockUser, createMockState } from './fixtures';
import { buildPdfBlob } from './mockPdf';
import { checkApprove, checkSpecRange, recommendLot, rejudge, summarize } from './serverRules';

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

/** API 응답의 이력 본문. item_id와 화면 전용 사유(reason)는 빼고 필요한 필드만 담습니다. */
function toLogBody(log: ReviewLog): Omit<ReviewLog, 'item_id' | 'reason'> {
  return {
    action: log.action,
    before_value: log.before_value,
    after_value: log.after_value,
    reviewer_name: log.reviewer_name,
    reviewed_at: log.reviewed_at,
  };
}

function textOf(value: number | string | null): string {
  if (value === null) return '';
  return typeof value === 'number' ? formatNumber(value) : value;
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
    // 시안 2-5와 같은 수정 사유 시드
    this.local.seedItemReason('A0355164', 'na', 'OCR 오인식 정정');
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
    options: PatchItemOptions = {},
  ): Promise<PatchItemResult> {
    const user = this.requireUser();
    const doc = this.findReadyDoc(documentId);
    this.assertEditable(doc);
    const index = doc.extraction.items.findIndex((entry) => entry.item_id === itemId);
    if (index === -1) throw new ApiError(404, 'ITEM_NOT_FOUND', '문서에 존재하지 않는 item_id');
    let item = doc.extraction.items[index];
    const newLogs: ReviewLog[] = [];

    if (body.normalized_name !== undefined) {
      const target = this.state.specs.find((entry) => entry.item_name === body.normalized_name);
      if (!target) throw new ApiError(400, 'UNKNOWN_ITEM_NAME', '사내 규격에 없는 항목명');
      newLogs.push({
        item_id: itemId,
        action: 'rename',
        before_value: item.normalized_name,
        after_value: target.item_name,
        reviewer_name: user.name,
        reviewed_at: now('rename'),
      });
      item = { ...item, normalized_name: target.item_name, mapping_source: 'manual' };
      // 서버는 item_mappings에 raw_name → normalized_name을 manual로 누적합니다.
      if (item.raw_name) {
        const existing = this.local
          .listMappings(target.material_code)
          .find((entry) => entry.rawName === item.raw_name);
        if (existing) this.local.deleteMapping(existing.id);
        this.local.addMapping({
          materialCode: target.material_code,
          standardName: target.item_name,
          rawName: item.raw_name,
          supplier: doc.detail.supplier,
          source: 'manual',
          conversion: null,
          registeredBy: user.name,
          registeredAt: todayText(),
        });
      }
    }

    let edited = false;
    if (body.converted_value !== undefined) {
      const before = textOf(item.converted_value) || (item.raw_value ?? '');
      const qualifier = body.value_qualifier ?? 'exact';
      item = { ...item, converted_value: body.converted_value, value_qualifier: qualifier };
      newLogs.push({
        item_id: itemId,
        action: 'edit',
        before_value: before,
        after_value: textOf(body.converted_value),
        reviewer_name: user.name,
        reviewed_at: now('edit'),
      });
      edited = true;
    } else if (body.value_qualifier !== undefined) {
      item = { ...item, value_qualifier: body.value_qualifier };
    }

    doc.reviewLogs.push(...newLogs);
    const resolved = processedItemIds(doc.reviewLogs).has(itemId);
    const spec = this.state.specs.find((entry) => entry.item_name === item.normalized_name);
    // 담당자가 값을 고쳤으면 결과 칸이 규격 문구와 같다는 조건은 더 이상 해당하지 않습니다.
    const sameAsSpec = !edited && this.resultSameAsSpec(item);
    const judged = rejudge(item, spec, resolved, sameAsSpec);
    this.commitItem(doc, index, judged);
    this.touchStatus(doc);
    if (options.reason) this.local.saveItemReason(documentId, itemId, options.reason);

    return delay({
      item: {
        item_id: judged.item_id,
        normalized_name: judged.normalized_name,
        converted_value: judged.converted_value,
        value_qualifier: judged.value_qualifier ?? 'exact',
        judgement: judged.judgement,
        judgement_reason: judged.judgement_reason,
        deviation: judged.deviation,
      },
      lot_recommendation: doc.extraction.lot_recommendation,
      summary: { ...doc.extraction.summary },
      review_logs: doc.reviewLogs
        .filter((log) => log.item_id === itemId)
        .map(toLogBody),
    });
  }

  async confirmItem(documentId: string, itemId: string): Promise<ConfirmItemResult> {
    const user = this.requireUser();
    const doc = this.findReadyDoc(documentId);
    this.assertEditable(doc);
    const index = doc.extraction.items.findIndex((entry) => entry.item_id === itemId);
    if (index === -1) throw new ApiError(404, 'ITEM_NOT_FOUND', '문서에 존재하지 않는 item_id');
    const item = doc.extraction.items[index];
    const value = textOf(item.converted_value) || (item.raw_value ?? '');
    const log: ReviewLog = {
      item_id: itemId,
      action: 'confirm',
      before_value: value,
      after_value: value,
      reviewer_name: user.name,
      reviewed_at: now('confirm'),
    };
    doc.reviewLogs.push(log);
    const spec = this.state.specs.find((entry) => entry.item_name === item.normalized_name);
    // 확인한 항목은 신뢰도 조건을 빼고 값만으로 다시 판정합니다. 결과 칸이 규격 문구와 같은 항목은 그대로 둡니다.
    const judged = rejudge(item, spec, true, this.resultSameAsSpec(item));
    this.commitItem(doc, index, judged);
    this.touchStatus(doc);
    return delay({
      item: { item_id: itemId, judgement: judged.judgement, judgement_reason: judged.judgement_reason },
      lot_recommendation: doc.extraction.lot_recommendation,
      review_log: toLogBody(log),
    });
  }

  private resultSameAsSpec(item: ExtractionItem): boolean {
    if (!item.raw_value || !item.raw_spec) return false;
    const normalize = (text: string) => text.replace(/\s+/g, '').replace(/=<|<=/g, '≤').toLowerCase();
    return normalize(item.raw_value) === normalize(item.raw_spec);
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
    return delay(this.local.attachItemReasons(documentId, structuredClone(doc.reviewLogs)));
  }

  async approve(documentId: string, body: ApproveBody): Promise<ApproveResult> {
    const user = this.requireUser();
    const doc = this.findDoc(documentId);
    const extraction = doc.extraction;
    const code = checkApprove({
      status: doc.detail.status,
      recommendation: extraction?.lot_recommendation ?? 'hold',
      pendingLowConfidence: extraction ? pendingLowConfidenceCount(extraction.items, doc.reviewLogs) : 0,
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

  async listSpecs(materialCode?: string): Promise<SpecItem[]> {
    this.requireUser();
    const specs = this.state.specs.filter((entry) => !materialCode || entry.material_code === materialCode);
    return delay(structuredClone(specs));
  }

  async patchSpec(specId: number, body: PatchSpecBody): Promise<PatchSpecResult> {
    const user = this.requireUser();
    if (user.role !== 'ADMIN') throw new ApiError(403, 'FORBIDDEN', '권한 없음');
    const target = this.state.specs.find((entry) => entry.id === specId);
    if (!target) throw new ApiError(404, 'SPEC_NOT_FOUND', '존재하지 않는 규격 항목');
    if (checkSpecRange(body.lsl, body.usl)) throw new ApiError(400, 'INVALID_SPEC_RANGE', '규격 하한이 상한보다 큼');
    // rejudge가 없으면 이미 추출된 문서의 판정은 바꾸지 않고, 이후 업로드 건부터 적용됩니다.
    target.lsl = body.lsl;
    target.usl = body.usl;
    target.unit = body.unit;
    target.updated_by = user.name;
    target.updated_at = now('spec');
    // [v1.4안] rejudge=true이면 처분 전 문서를 새 규격으로 다시 판정하고, 판정이 바뀐 문서 목록을 돌려줍니다.
    if (body.rejudge) return delay({ ...target, rejudged_documents: this.rejudgeOpenDocuments(target.material_code) });
    return delay({ ...target });
  }

  /** 처분 전(approved가 아닌) 문서를 현재 규격으로 다시 판정하고, 항목 판정이나 로트 권고가 바뀐 문서를 돌려줍니다. */
  private rejudgeOpenDocuments(materialCode: string): Array<{ document_id: string }> {
    const changed: Array<{ document_id: string }> = [];
    for (const doc of this.state.docs) {
      const extraction = doc.extraction;
      if (!extraction || doc.detail.material_code !== materialCode || !READY_STATUSES.includes(doc.detail.status)) continue;
      if (doc.detail.status === 'approved') continue;
      const resolvedIds = processedItemIds(doc.reviewLogs);
      const before = JSON.stringify([extraction.items.map((item) => item.judgement), extraction.lot_recommendation]);
      extraction.items = extraction.items.map((item) => {
        const spec = this.state.specs.find((entry) => entry.material_code === materialCode && entry.item_name === item.normalized_name);
        // 규격에 없는 이름의 항목(AI 추정 등)은 이 규격 변경과 관계가 없어 그대로 둡니다.
        if (!spec) return item;
        // 누락 항목은 값이 들어오기 전까지 누락 그대로 두고 규격 한계만 새 값으로 바꿉니다.
        if (item.judgement === 'missing' && item.converted_value === null) {
          return { ...item, spec_lsl: spec.lsl, spec_usl: spec.usl };
        }
        const edited = doc.reviewLogs.some((entry) => entry.item_id === item.item_id && entry.action === 'edit');
        return rejudge(item, spec, resolvedIds.has(item.item_id), !edited && this.resultSameAsSpec(item));
      });
      extraction.summary = summarize(extraction.items);
      extraction.lot_recommendation = recommendLot(extraction.summary, extraction.document_issues.length);
      doc.detail.lot_recommendation = extraction.lot_recommendation;
      const after = JSON.stringify([extraction.items.map((item) => item.judgement), extraction.lot_recommendation]);
      if (before !== after) changed.push({ document_id: doc.detail.document_id });
    }
    return changed;
  }

  // --- API 없음: 목업 (TODO(백엔드 협의)) ----------------------------------

  async listSpecHistory(materialCode: string): Promise<SpecHistoryEntry[]> {
    return delay(this.local.listSpecHistory(materialCode));
  }

  async addSpecHistory(entry: Omit<SpecHistoryEntry, 'id'>): Promise<void> {
    this.local.addSpecHistory(entry);
    return delay(undefined);
  }

  async listMappings(materialCode: string): Promise<MappingEntry[]> {
    return delay(this.local.listMappings(materialCode));
  }

  async addMapping(entry: Omit<MappingEntry, 'id'>): Promise<MappingEntry> {
    return delay(this.local.addMapping(entry));
  }

  async registerMapping(id: string, registeredBy: string): Promise<void> {
    this.local.registerMapping(id, registeredBy);
    return delay(undefined);
  }

  async deleteMapping(id: string): Promise<void> {
    this.local.deleteMapping(id);
    return delay(undefined);
  }

  async listUnitConversions(): Promise<UnitConversion[]> {
    return delay(this.local.listUnitConversions());
  }
}
