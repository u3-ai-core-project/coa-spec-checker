import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '../shared/api';
import type {
  Anomaly,
  ApprovalLog,
  DocumentDetail,
  ExtractionResult,
  ReviewLog,
  SpecItem,
} from '../shared/api/types';

export interface ReviewData {
  doc: DocumentDetail;
  extraction: ExtractionResult;
  reviewLogs: ReviewLog[];
  approvalLogs: ApprovalLog[];
  /** 문서의 원자재 구분에 해당하는 사내 규격. 항목 정렬(규격 순서)과 항목명 선택지에 씁니다. */
  specs: SpecItem[];
  anomalies: Anomaly[];
}

interface State {
  data: ReviewData | null;
  error: unknown;
  loading: boolean;
}

async function fetchReviewData(documentId: string): Promise<ReviewData> {
  const doc = await api.getDocument(documentId);
  const [extraction, reviewLogs, approvalLogs, specs, anomalies] = await Promise.all([
    api.getExtraction(documentId),
    api.getReviewLogs(documentId),
    api.getApprovalLogs(documentId),
    api.listSpecs(doc.material_code),
    // 이상 패턴은 확장 기능이라 실패해도 검수 화면은 계속 보여 줍니다.
    api.getAnomalies(documentId).catch((): Anomaly[] => []),
  ]);
  return { doc, extraction, reviewLogs, approvalLogs, specs, anomalies };
}

/**
 * 검수 화면이 쓰는 문서 데이터를 한 번에 불러옵니다.
 * 값 수정, 확인, 처분 뒤에는 reload()로 서버 응답을 다시 불러와 화면에 반영합니다(판정과 집계는 서버가 계산합니다).
 * 다시 불러오는 동안에는 이전 데이터를 유지합니다.
 */
export function useReviewData(documentId: string) {
  const [state, setState] = useState<State>({ data: null, error: null, loading: true });
  const requestId = useRef(0);

  const load = useCallback(
    async (keepData: boolean) => {
      const current = ++requestId.current;
      setState((prev) => ({ data: keepData && prev.data?.doc.document_id === documentId ? prev.data : null, error: null, loading: true }));
      try {
        const data = await fetchReviewData(documentId);
        if (current === requestId.current) setState({ data, error: null, loading: false });
      } catch (error) {
        if (current === requestId.current) setState((prev) => ({ data: prev.data, error, loading: false }));
      }
    },
    [documentId],
  );

  useEffect(() => {
    void load(false);
    return () => {
      requestId.current += 1;
    };
  }, [load]);

  const reload = useCallback(() => load(true), [load]);
  return { ...state, reload };
}
