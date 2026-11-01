import { useCallback, useRef, useState } from 'react';
import { api } from '../shared/api';
import { errorMessage } from '../shared/api/errors';
import type { FollowUpsResponse } from '../shared/api/types';

interface AiResult {
  /** 이 AI 응답을 요청할 때의 기본 follow-ups. 이 값이 바뀌면(항목 수정, 확인 뒤 다시 불러옴) 요청 내용이 달라져 응답을 버립니다. */
  base: FollowUpsResponse;
  followUps: FollowUpsResponse;
}

/**
 * "AI로 다듬기": GET /documents/{id}/follow-ups?draft=ai로 AI 문의 초안을 받습니다(최대 3분, 타임아웃은 HttpApi가 200초로 끊음).
 * 응답은 그대로 보관만 하고, source가 ai인지 template_fallback인지는 화면이 응답 값 그대로 보여 줍니다.
 * 실패하면 기존 템플릿 초안(base)은 그대로 두고 오류 문구만 남깁니다.
 */
export function useAiDraft(documentId: string, base: FollowUpsResponse | null) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<AiResult | null>(null);
  const inFlight = useRef(false);

  const request = useCallback(async () => {
    if (inFlight.current || !base) return; // 중복 클릭 방지
    inFlight.current = true;
    setLoading(true);
    setError(null);
    try {
      const followUps = await api.getFollowUps(documentId, { draft: 'ai' });
      setResult({ base, followUps });
    } catch (failure) {
      setError(errorMessage(failure));
    } finally {
      inFlight.current = false;
      setLoading(false);
    }
  }, [documentId, base]);

  return { followUps: result && result.base === base ? result.followUps : null, loading, error, request };
}
