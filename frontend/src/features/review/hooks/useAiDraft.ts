import { useCallback, useRef, useState } from 'react';
import { api } from '../shared/api';
import { errorMessage } from '../shared/api/errors';
import type { FollowUpsResponse } from '../shared/api/types';

interface AiResult {
  /** 이 AI 응답을 요청할 때의 기본 follow-ups. 이 값이 바뀌면(항목 수정, 확인 뒤 다시 불러옴) 요청 내용이 달라져 응답을 버립니다. */
  base: FollowUpsResponse;
  followUps: FollowUpsResponse;
  /** "기본 초안으로 보기"를 눌러 템플릿 초안을 보고 있는 상태. AI 응답은 버리지 않고 두며, 서버 요청은 하지 않습니다. */
  templateView: boolean;
}

/**
 * "AI로 다듬기": GET /documents/{id}/follow-ups?draft=ai로 AI 문의 초안을 받습니다(최대 3분, 타임아웃은 HttpApi가 200초로 끊음).
 * 응답은 그대로 보관만 하고, source가 ai인지 template_fallback인지는 화면이 응답 값 그대로 보여 줍니다.
 * 실패하면 기존 템플릿 초안(base)은 그대로 두고 오류 문구만 남깁니다.
 * 처음 받은 템플릿 초안은 base로 그대로 있으므로, showTemplate()은 서버 요청 없이 화면만 템플릿으로 되돌립니다.
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
      setResult({ base, followUps, templateView: false });
    } catch (failure) {
      setError(errorMessage(failure));
    } finally {
      inFlight.current = false;
      setLoading(false);
    }
  }, [documentId, base]);

  const showTemplate = useCallback(() => {
    setResult((current) => (current ? { ...current, templateView: true } : current));
  }, []);

  // base가 바뀌면(항목 수정 뒤 follow-ups를 다시 불러옴) AI 응답은 옛 내용이라 버리고, 템플릿 초안은 새 base를 씁니다.
  const current = result && result.base === base ? result : null;
  return {
    /** 지금 보여 줄 AI 응답. 없거나 템플릿 초안을 보고 있으면 null입니다. */
    followUps: current && !current.templateView ? current.followUps : null,
    /** 이 base로 AI 응답을 받은 적이 있는지(템플릿으로 되돌린 뒤에도 true) */
    hasResult: current !== null,
    loading,
    error,
    request,
    showTemplate,
  };
}
