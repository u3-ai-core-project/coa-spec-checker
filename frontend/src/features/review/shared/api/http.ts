import { API_BASE } from '../config';
import type {
  Api,
  MappingEntry,
  PatchItemOptions,
  SpecHistoryEntry,
  UnitConversion,
} from './Api';
import { ApiError } from './errors';
import { LocalOnlyStore } from './localOnly';
import { getToken, handleUnauthorized } from './session';
import type {
  Anomaly,
  ApiErrorBody,
  ApprovalLog,
  ApproveBody,
  ApproveResult,
  AuthUser,
  CancelApprovalBody,
  CancelApprovalResult,
  ConfirmItemResult,
  DocumentDetail,
  DocumentListQuery,
  DocumentListResult,
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
} from './types';

interface Envelope<T> {
  success: boolean;
  data: T | null;
  error: ApiErrorBody | null;
}

function buildQuery(params: Record<string, string | number | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== '') search.set(key, String(value));
  }
  const text = search.toString();
  return text ? `?${text}` : '';
}

async function send(path: string, init: RequestInit = {}, auth = true): Promise<Response> {
  const headers = new Headers(init.headers);
  if (init.body !== undefined && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }
  const token = getToken();
  if (auth && token) headers.set('Authorization', `Bearer ${token}`);

  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, { ...init, headers });
  } catch {
    throw new ApiError(0, 'NETWORK_ERROR', '서버에 연결하지 못했습니다.');
  }

  if (response.status === 401 && auth) {
    // 로그인 API의 401(INVALID_CREDENTIALS)은 auth=false로 호출하므로 여기서 걸리지 않습니다.
    handleUnauthorized();
  }
  return response;
}

async function readError(response: Response): Promise<ApiError> {
  try {
    const body = (await response.json()) as Envelope<unknown>;
    if (body.error) return new ApiError(response.status, body.error.code, body.error.message);
  } catch {
    // 본문이 JSON이 아니면 아래 기본값을 씁니다.
  }
  return new ApiError(response.status, 'UNKNOWN_ERROR', '요청을 처리하지 못했습니다.');
}

async function request<T>(path: string, init: RequestInit = {}, auth = true): Promise<T> {
  const response = await send(path, init, auth);
  if (!response.ok) throw await readError(response);
  const body = (await response.json()) as Envelope<T>;
  if (!body.success || body.data === null) {
    throw new ApiError(response.status, body.error?.code ?? 'UNKNOWN_ERROR', body.error?.message ?? '');
  }
  return body.data;
}

function jsonBody(value: unknown): RequestInit {
  return { method: 'POST', body: JSON.stringify(value) };
}

/**
 * 실제 백엔드 API 구현입니다.
 * 명세(v1.3)에 없는 기능(변경 이력, 매핑 사전, 단위 환산표)은 LocalOnlyStore에 위임합니다.
 */
export class HttpApi implements Api {
  private readonly local = new LocalOnlyStore();

  login(username: string, password: string): Promise<LoginResult> {
    return request<LoginResult>('/auth/login', jsonBody({ username, password }), false);
  }

  me(): Promise<AuthUser> {
    return request<AuthUser>('/auth/me');
  }

  listDocuments(query: DocumentListQuery = {}): Promise<DocumentListResult> {
    return request<DocumentListResult>(`/documents${buildQuery({ ...query })}`);
  }

  getDocument(documentId: string): Promise<DocumentDetail> {
    return request<DocumentDetail>(`/documents/${encodeURIComponent(documentId)}`);
  }

  async getDocumentFile(documentId: string): Promise<Blob> {
    const response = await send(`/documents/${encodeURIComponent(documentId)}/file`);
    if (!response.ok) throw await readError(response);
    return response.blob();
  }

  async getExtraction(documentId: string): Promise<ExtractionResult> {
    const result = await request<ExtractionResult>(`/documents/${encodeURIComponent(documentId)}/extraction`);
    // [v1.4안] document_issues가 응답에 없으면(문제 없음 또는 구버전 서버) 빈 배열로 둡니다.
    return { ...result, document_issues: result.document_issues ?? [] };
  }

  async patchItem(
    documentId: string,
    itemId: string,
    body: PatchItemBody,
    options: PatchItemOptions = {},
  ): Promise<PatchItemResult> {
    const result = await request<PatchItemResult>(
      `/documents/${encodeURIComponent(documentId)}/extraction/${encodeURIComponent(itemId)}`,
      { method: 'PATCH', body: JSON.stringify(body) },
    );
    // options.accumulate(사전 누적 끄기)도 보낼 필드가 없어 서버에는 반영되지 않습니다(서버는 항상 누적).
    // 사유는 서버로 보내지 않습니다. TODO(백엔드 협의): API에 사유 필드가 생기면 위 요청에 포함합니다.
    if (options.reason) this.local.saveItemReason(documentId, itemId, options.reason);
    return result;
  }

  confirmItem(documentId: string, itemId: string): Promise<ConfirmItemResult> {
    return request<ConfirmItemResult>(
      `/documents/${encodeURIComponent(documentId)}/extraction/${encodeURIComponent(itemId)}/confirm`,
      { method: 'POST' },
    );
  }

  async getReviewLogs(documentId: string): Promise<ReviewLog[]> {
    const logs = await request<ReviewLog[]>(`/documents/${encodeURIComponent(documentId)}/review-logs`);
    return this.local.attachItemReasons(documentId, logs);
  }

  approve(documentId: string, body: ApproveBody): Promise<ApproveResult> {
    return request<ApproveResult>(`/documents/${encodeURIComponent(documentId)}/approve`, jsonBody(body));
  }

  hold(documentId: string, body: HoldBody): Promise<HoldResult> {
    return request<HoldResult>(`/documents/${encodeURIComponent(documentId)}/hold`, jsonBody(body));
  }

  cancelApproval(documentId: string, body: CancelApprovalBody): Promise<CancelApprovalResult> {
    return request<CancelApprovalResult>(
      `/documents/${encodeURIComponent(documentId)}/cancel-approval`,
      jsonBody(body),
    );
  }

  getApprovalLogs(documentId: string): Promise<ApprovalLog[]> {
    return request<ApprovalLog[]>(`/documents/${encodeURIComponent(documentId)}/approval-logs`);
  }

  getAnomalies(documentId: string): Promise<Anomaly[]> {
    return request<Anomaly[]>(`/documents/${encodeURIComponent(documentId)}/anomalies`);
  }

  listSpecs(materialCode?: string): Promise<SpecItem[]> {
    return request<SpecItem[]>(`/specs${buildQuery({ material_code: materialCode })}`);
  }

  patchSpec(specId: number, body: PatchSpecBody): Promise<PatchSpecResult> {
    return request<PatchSpecResult>(`/specs/${specId}`, { method: 'PATCH', body: JSON.stringify(body) });
  }

  // --- API 없음: LocalOnlyStore 위임 (TODO(백엔드 협의)) -----------------------

  listSpecHistory(materialCode: string): Promise<SpecHistoryEntry[]> {
    return Promise.resolve(this.local.listSpecHistory(materialCode));
  }

  addSpecHistory(entry: Omit<SpecHistoryEntry, 'id'>): Promise<void> {
    this.local.addSpecHistory(entry);
    return Promise.resolve();
  }

  listMappings(materialCode: string): Promise<MappingEntry[]> {
    return Promise.resolve(this.local.listMappings(materialCode));
  }

  addMapping(entry: Omit<MappingEntry, 'id'>): Promise<MappingEntry> {
    return Promise.resolve(this.local.addMapping(entry));
  }

  registerMapping(id: string, registeredBy: string): Promise<void> {
    this.local.registerMapping(id, registeredBy);
    return Promise.resolve();
  }

  deleteMapping(id: string): Promise<void> {
    this.local.deleteMapping(id);
    return Promise.resolve();
  }

  listUnitConversions(): Promise<UnitConversion[]> {
    return Promise.resolve(this.local.listUnitConversions());
  }
}
