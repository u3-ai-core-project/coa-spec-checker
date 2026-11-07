import type {
  Anomaly,
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
  LoginResult,
  ConversionsResponse,
  MappingDeleted,
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
} from './types';

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
  /**
   * 문서 삭제(DELETE /documents/{id}, 백엔드 PR #45). 올린 사람 본인 또는 ADMIN만 지울 수 있습니다.
   * 처분 완료 문서는 409 ALREADY_APPROVED, 추출 중 문서는 409 NOT_READY, 권한이 없으면 403 FORBIDDEN입니다.
   */
  deleteDocument(documentId: string): Promise<DocumentDeleted>;
  /** 원본 파일. 토큰이 필요하므로 fetch로 받아 Blob으로 돌려주고, 화면이 Blob URL로 바꿉니다. */
  getDocumentFile(documentId: string): Promise<Blob>;
  getExtraction(documentId: string): Promise<ExtractionResult>;
  patchItem(
    documentId: string,
    itemId: string,
    body: PatchItemBody,
  ): Promise<PatchItemResult>;
  confirmItem(documentId: string, itemId: string): Promise<ConfirmItemResult>;
  getReviewLogs(documentId: string): Promise<ReviewLog[]>;
  approve(documentId: string, body: ApproveBody): Promise<ApproveResult>;
  hold(documentId: string, body: HoldBody): Promise<HoldResult>;
  cancelApproval(documentId: string, body: CancelApprovalBody): Promise<CancelApprovalResult>;
  getApprovalLogs(documentId: string): Promise<ApprovalLog[]>;
  /**
   * [v1.4] 후속 조치 목록, 보류 후속 조치 추천, 공급사 문의 초안(같은 공급사의 열린 요청 묶음 포함). 읽기만 합니다.
   * options.draft가 'ai'이면 AI 초안을 요청합니다. 최대 3분이 걸릴 수 있어 HttpApi는 200초 뒤에 요청을 끊고
   * ApiError(code TIMEOUT)를 던집니다.
   */
  getFollowUps(documentId: string, options?: FollowUpsOptions): Promise<FollowUpsResponse>;
  /** 확장 기능. */
  getAnomalies(documentId: string): Promise<Anomaly[]>;

  // --- 규격 -----------------------------------------------------------------
  /** [v1.4] 원자재(material_code)나 규격 세트(spec_set_code)로 거릅니다. 둘 다 없으면 모든 세트의 항목이 옵니다. */
  listSpecs(query?: SpecListQuery): Promise<SpecItem[]>;
  /** [v1.4] 규격 세트(등급, 버전) 목록. 원자재별로 기본 세트가 먼저 옵니다. */
  listSpecSets(materialCode?: string): Promise<SpecSet[]>;
  /** 규격 항목 수정(ADMIN). body.rejudge가 true이면 처분 전 문서를 새 규격으로 다시 판정하고 그 결과를 rejudged_documents로 돌려줍니다. */
  patchSpec(specId: number, body: PatchSpecBody): Promise<PatchSpecResult>;

  /** 규격 항목 하나의 변경 이력(GET /specs/{id}/change-logs). 서버는 오래된 순으로 줍니다. */
  listSpecChangeLogs(specId: number): Promise<SpecChangeLog[]>;

  // --- 매핑 사전 (5-2) ------------------------------------------------------
  // GET /mappings?material_code=, DELETE /mappings/{id}(ADMIN만), GET /mappings/conversions(조회만). 표기 추가와 사전 등록 API는 없습니다.
  listMappings(materialCode: string): Promise<MappingRecord[]>;
  deleteMapping(id: number): Promise<MappingDeleted>;
  /** 단위 환산과 산화물 → 원소 환산. 서버 설정값이므로 조회만 합니다. */
  getConversions(): Promise<ConversionsResponse>;
}
