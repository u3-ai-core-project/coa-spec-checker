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
  FollowUpsResponse,
  HoldBody,
  HoldResult,
  LoginResult,
  MappingRecord,
  PatchItemBody,
  PatchItemResult,
  PatchSpecBody,
  PatchSpecResult,
  ReviewLog,
  SpecChangeLog,
  SpecItem,
  SpecListQuery,
  SpecSet,
  UnitConversion,
} from './types';

export interface PatchItemOptions {
  /**
   * 항목명을 고칠 때 매핑 사전에 누적할지(기본 true). false이면 이 문서의 항목명만 바꾸고 사전에는 남기지 않습니다.
   * TODO(백엔드 협의): API(PATCH normalized_name)는 항상 사전에 누적하고 끄는 필드가 없어, 목업만 이 값을 따릅니다.
   * HttpApi는 서버가 누적하는 것을 막을 수 없습니다.
   */
  accumulate?: boolean;
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
  /** [v1.4] 후속 조치 목록, 보류 후속 조치 추천, 공급사 문의 초안(같은 공급사의 열린 요청 묶음 포함). 읽기만 합니다. */
  getFollowUps(documentId: string): Promise<FollowUpsResponse>;
  /** 확장 기능. */
  getAnomalies(documentId: string): Promise<Anomaly[]>;

  // --- 규격 -----------------------------------------------------------------
  /** [v1.4] 원자재(material_code)나 규격 세트(spec_set_code)로 거릅니다. 둘 다 없으면 모든 세트의 항목이 옵니다. */
  listSpecs(query?: SpecListQuery): Promise<SpecItem[]>;
  /** [v1.4] 규격 세트(등급, 버전) 목록. 원자재별로 기본 세트가 먼저 옵니다. */
  listSpecSets(materialCode?: string): Promise<SpecSet[]>;
  patchSpec(specId: number, body: PatchSpecBody): Promise<PatchSpecResult>;

  /** [백엔드 확정 답변] 규격 항목 하나의 변경 이력(변경 전후 값, 수정자, 사유, 시각). 서버 구현 전이라 응답 모양은 가정입니다. */
  listSpecChangeLogs(specId: number): Promise<SpecChangeLog[]>;

  // --- 매핑 사전 (5-2) ------------------------------------------------------
  // [백엔드 확정 답변] GET /mappings?material_code=, DELETE /mappings/{id}(ADMIN만), GET /mappings/conversions(조회만).
  // TODO(백엔드 협의): 서버 구현 전이라 응답 모양은 가정입니다. 표기 추가와 사전 등록 API는 없습니다.
  listMappings(materialCode: string): Promise<MappingRecord[]>;
  deleteMapping(id: number): Promise<void>;
  /** 환산 계수는 서버 설정값이므로 조회만 합니다. */
  listUnitConversions(): Promise<UnitConversion[]>;
}
