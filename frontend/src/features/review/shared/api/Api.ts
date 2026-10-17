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
  DocumentListQuery,
  DocumentListResult,
  ExtractionResult,
  HoldBody,
  HoldResult,
  LoginResult,
  PatchItemBody,
  PatchItemResult,
  PatchSpecBody,
  ReviewLog,
  SpecItem,
} from './types';

// ---------------------------------------------------------------------------
// 아래 세 타입은 백엔드 API에 아직 없는 화면(5-1 변경 이력, 5-2 매핑 사전·단위 환산표)용입니다.
// TODO(백엔드 협의): API가 생기면 이 타입을 명세에 맞춰 바꾸고 localOnly 구현을 http 구현으로 교체합니다.
// ---------------------------------------------------------------------------

export interface SpecHistoryEntry {
  id: string;
  materialCode: string;
  title: string;
  by: string;
  at: string;
  reason: string | null;
}

export type MappingEntrySource = 'dictionary' | 'ai' | 'manual';

export interface MappingEntry {
  id: string;
  materialCode: string;
  /** 사내 표준 항목명 */
  standardName: string;
  /** 협력사가 CoA에 적은 표기 */
  rawName: string;
  /**
   * 시안 5-2의 "협력사" 열(공통, Chengxin, -). 표시용 목업 값입니다.
   * TODO(백엔드 협의): 매핑 사전은 material_code + raw_name 기준이라 협력사 필드가 없습니다. API가 정해지면 맞춥니다.
   */
  supplier: string;
  source: MappingEntrySource;
  conversion: string | null;
  registeredBy: string;
  registeredAt: string;
}

export interface UnitConversion {
  id: string;
  label: string;
  formula: string;
  factor: string;
}

export interface PatchItemOptions {
  /**
   * 수정 사유. API에 필드가 없어 서버로 보내지 않고 화면 쪽 저장소에만 둡니다.
   * TODO(백엔드 협의): 사유 필드가 생기면 PATCH 요청에 포함합니다.
   */
  reason?: string;
}

/**
 * 화면이 호출하는 유일한 API 계층입니다. 구현은 목업(MockApi)과 http(HttpApi) 두 가지입니다.
 * VITE_USE_MOCK 환경변수로 전환합니다.
 */
export interface Api {
  // --- 인증 -----------------------------------------------------------------
  login(username: string, password: string): Promise<LoginResult>;
  me(): Promise<AuthUser>;

  // --- 문서 (검수) ----------------------------------------------------------
  listDocuments(query?: DocumentListQuery): Promise<DocumentListResult>;
  getDocument(documentId: string): Promise<DocumentDetail>;
  /** 원본 파일. 토큰이 필요하므로 fetch로 받아 Blob으로 돌려주고, 화면이 Blob URL로 바꿉니다. */
  getDocumentFile(documentId: string): Promise<Blob>;
  getExtraction(documentId: string): Promise<ExtractionResult>;
  patchItem(
    documentId: string,
    itemId: string,
    body: PatchItemBody,
    options?: PatchItemOptions,
  ): Promise<PatchItemResult>;
  confirmItem(documentId: string, itemId: string): Promise<ConfirmItemResult>;
  getReviewLogs(documentId: string): Promise<ReviewLog[]>;
  approve(documentId: string, body: ApproveBody): Promise<ApproveResult>;
  hold(documentId: string, body: HoldBody): Promise<HoldResult>;
  cancelApproval(documentId: string, body: CancelApprovalBody): Promise<CancelApprovalResult>;
  getApprovalLogs(documentId: string): Promise<ApprovalLog[]>;
  /** 확장 기능. */
  getAnomalies(documentId: string): Promise<Anomaly[]>;

  // --- 규격 -----------------------------------------------------------------
  listSpecs(materialCode?: string): Promise<SpecItem[]>;
  patchSpec(specId: number, body: PatchSpecBody): Promise<SpecItem>;

  // --- API 없음: 목업 (TODO(백엔드 협의)) ----------------------------------
  listSpecHistory(materialCode: string): Promise<SpecHistoryEntry[]>;
  addSpecHistory(entry: Omit<SpecHistoryEntry, 'id'>): Promise<void>;
  listMappings(materialCode: string): Promise<MappingEntry[]>;
  addMapping(entry: Omit<MappingEntry, 'id'>): Promise<MappingEntry>;
  /** AI 추정 표기를 사전에 등록합니다(source를 dictionary로 바꿉니다). */
  registerMapping(id: string, registeredBy: string): Promise<void>;
  deleteMapping(id: string): Promise<void>;
  /** 환산 계수는 서버 설정값이므로 조회만 합니다. */
  listUnitConversions(): Promise<UnitConversion[]>;
}
