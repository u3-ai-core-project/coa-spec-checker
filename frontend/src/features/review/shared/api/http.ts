import { API_BASE } from '../config';
import type { Api } from './Api';
import { AI_DRAFT_TIMEOUT_MS } from '../domain/constants';
import { ApiError } from './errors';
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
  DocumentDeleted,
  DocumentDetail,
  DocumentListQuery,
  DocumentListResult,
  ExtractionResult,
  FollowUpsOptions,
  FollowUpsResponse,
  HoldBody,
  HoldResult,
  ConversionsResponse,
  LoginResult,
  MappingDeleted,
  MappingRecord,
  PatchItemBody,
  PatchItemResult,
  RejudgeRequest,
  RejudgeResult,
  PatchSpecBody,
  PatchSpecResult,
  ReviewLog,
  SpecChangeLog,
  SpecItem,
  SpecListQuery,
  SpecSet,
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

/** timeoutMs를 주면 그 시간 안에 응답이 오지 않을 때 요청을 끊고 ApiError(TIMEOUT)를 던집니다. */
async function send(path: string, init: RequestInit = {}, auth = true, timeoutMs?: number): Promise<Response> {
  const headers = new Headers(init.headers);
  if (init.body !== undefined && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }
  const token = getToken();
  if (auth && token) headers.set('Authorization', `Bearer ${token}`);

  const controller = timeoutMs === undefined ? null : new AbortController();
  const timer = controller && setTimeout(() => controller.abort(), timeoutMs);
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, { ...init, headers, signal: controller?.signal ?? init.signal });
  } catch {
    if (controller?.signal.aborted) throw new ApiError(0, 'TIMEOUT', '서버 응답이 너무 오래 걸립니다.');
    throw new ApiError(0, 'NETWORK_ERROR', '서버에 연결하지 못했습니다.');
  } finally {
    clearTimeout(timer ?? undefined);
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

async function request<T>(path: string, init: RequestInit = {}, auth = true, timeoutMs?: number): Promise<T> {
  const response = await send(path, init, auth, timeoutMs);
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
 * 문서 재판정 API (규격 세트를 바꿔 다시 판정, 백엔드 PR #59).
 *   POST /documents/{id}/rejudge, body { spec_set_code, apply(기본 false), reason }
 *   응답은 문서 상세가 아니라 RejudgeResult(이전 → 이후 비교와 새 판정 결과).
 * 주소, 요청 본문, 응답 해석은 이 함수 한 곳에서만 정합니다. 계약이 바뀌면 이 함수만 고칩니다.
 * 항목과 문서 상세는 적용한 뒤 화면이 GET으로 다시 받습니다.
 */
async function requestRejudge(documentId: string, req: RejudgeRequest): Promise<RejudgeResult> {
  const path = `/documents/${encodeURIComponent(documentId)}/rejudge`;
  const body = {
    spec_set_code: req.spec_set_code,
    apply: req.apply ?? false,
    ...(req.reason === undefined ? {} : { reason: req.reason }),
  };
  return request<RejudgeResult>(path, jsonBody(body));
}

/**
 * 실제 백엔드 API 구현입니다.
 * 값 수정 사유, 규격 변경 이력, 매핑 사전, 환산표는 백엔드 PR #12에서 확정된 형식입니다.
 */
export class HttpApi implements Api {

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

  deleteDocument(documentId: string): Promise<DocumentDeleted> {
    return request<DocumentDeleted>(`/documents/${encodeURIComponent(documentId)}`, { method: 'DELETE' });
  }

  rejudgeDocument(documentId: string, request: RejudgeRequest): Promise<RejudgeResult> {
    return requestRejudge(documentId, request);
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
  ): Promise<PatchItemResult> {
    return request<PatchItemResult>(
      `/documents/${encodeURIComponent(documentId)}/extraction/${encodeURIComponent(itemId)}`,
      { method: 'PATCH', body: JSON.stringify(body) },
    );
  }

  confirmItem(documentId: string, itemId: string): Promise<ConfirmItemResult> {
    return request<ConfirmItemResult>(
      `/documents/${encodeURIComponent(documentId)}/extraction/${encodeURIComponent(itemId)}/confirm`,
      { method: 'POST' },
    );
  }

  getReviewLogs(documentId: string): Promise<ReviewLog[]> {
    return request<ReviewLog[]>(`/documents/${encodeURIComponent(documentId)}/review-logs`);
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

  listSpecs(query: SpecListQuery = {}): Promise<SpecItem[]> {
    return request<SpecItem[]>(`/specs${buildQuery({ material_code: query.material_code, spec_set_code: query.spec_set_code })}`);
  }

  listSpecSets(materialCode?: string): Promise<SpecSet[]> {
    return request<SpecSet[]>(`/specs/sets${buildQuery({ material_code: materialCode })}`);
  }

  getFollowUps(documentId: string, options: FollowUpsOptions = {}): Promise<FollowUpsResponse> {
    // draft=ai는 LLM이 쓰는 초안이라 최대 3분이 걸립니다. 그 요청에만 긴 타임아웃을 둡니다.
    return request<FollowUpsResponse>(
      `/documents/${encodeURIComponent(documentId)}/follow-ups${buildQuery({ draft: options.draft })}`,
      {},
      true,
      options.draft === 'ai' ? AI_DRAFT_TIMEOUT_MS : undefined,
    );
  }

  async patchSpec(specId: number, body: PatchSpecBody): Promise<PatchSpecResult> {
    const result = await request<PatchSpecResult>(`/specs/${specId}`, { method: 'PATCH', body: JSON.stringify(body) });
    // rejudge를 보내지 않은 요청(또는 이 필드가 없는 서버)의 응답에는 rejudged_documents가 비어 있습니다.
    return { ...result, rejudged_documents: result.rejudged_documents ?? [] };
  }

  listSpecChangeLogs(specId: number): Promise<SpecChangeLog[]> {
    return request<SpecChangeLog[]>(`/specs/${specId}/change-logs`);
  }

  // --- 매핑 사전 (5-2) ------------------------------------------------------

  listMappings(materialCode: string): Promise<MappingRecord[]> {
    return request<MappingRecord[]>(`/mappings${buildQuery({ material_code: materialCode })}`);
  }

  deleteMapping(id: number): Promise<MappingDeleted> {
    return request<MappingDeleted>(`/mappings/${id}`, { method: 'DELETE' });
  }

  getConversions(): Promise<ConversionsResponse> {
    return request<ConversionsResponse>('/mappings/conversions');
  }
}
