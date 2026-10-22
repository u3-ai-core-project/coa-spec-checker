import type { DocumentStatus, FinalDecision, Judgement, LotRecommendation } from '../api/types';
import { JUDGEMENT_META } from '../domain/judgement';
import { DISPOSITION_META, type Disposition, RECOMMENDATION_META } from '../domain/recommendation';
import { STATUS_META, statusKey } from '../domain/status';
import { Icon } from './Icon';

/** 항목 판정 배지 5종. 색상과 텍스트를 함께 표시합니다. */
export function JudgementBadge({ judgement, fixedWidth = false }: { judgement: Judgement; fixedWidth?: boolean }) {
  const meta = JUDGEMENT_META[judgement];
  return (
    <span
      className={`status-badge status-badge-${judgement} inline-flex shrink-0 items-center whitespace-nowrap rounded-full px-2.5 py-1 text-[12px] font-semibold${fixedWidth ? ' w-[72px] justify-center' : ''}`}
      style={{ backgroundColor: meta.bg, color: meta.color }}
    >
      {meta.label}
    </span>
  );
}

/** 로트 권고(AI 권고) 배지 */
export function RecommendationBadge({
  recommendation,
  compact = false,
}: {
  recommendation: LotRecommendation;
  compact?: boolean;
}) {
  const meta = RECOMMENDATION_META[recommendation];
  return (
    <span
      className="lot-ai-rec inline-flex h-7 items-center gap-1.5 whitespace-nowrap rounded-full border bg-white px-2.5 text-[12px] font-semibold"
      style={{ borderColor: meta.color, color: meta.color }}
    >
      <Icon name="spark" size={13} />
      {!compact && <span className="font-normal text-[#5B616A]">AI 권고</span>}
      {meta.label}
    </span>
  );
}

/** 담당자 처분 배지. 처분이 없으면 "담당자 처분 대기"를 점선으로 표시합니다. */
export function DispositionBadge({
  disposition,
  compact = false,
}: {
  disposition: Disposition | FinalDecision | null;
  compact?: boolean;
}) {
  if (disposition === null) {
    return (
      <span className="lot-disposition lot-disposition-pending inline-flex h-7 items-center gap-1.5 whitespace-nowrap rounded-full border border-dashed border-[#B6BBC4] bg-white px-2.5 text-[12px] font-semibold text-[#5B616A]">
        <Icon name="user" size={13} />
        담당자 처분 대기
      </span>
    );
  }
  const meta = DISPOSITION_META[disposition];
  return (
    <span
      className="lot-disposition inline-flex h-7 items-center gap-1.5 whitespace-nowrap rounded-full px-2.5 text-[12px] font-semibold text-white"
      style={{ backgroundColor: meta.color }}
    >
      <Icon name="user" size={13} />
      {!compact && <span className="font-normal opacity-80">처분</span>}
      {meta.label}
    </span>
  );
}

/** 문서 상태 배지(대기, 처리 중, 검수 중, 보류, 완료, 오류) */
export function StatusBadge({ status }: { status: DocumentStatus }) {
  const key = statusKey(status);
  const meta = STATUS_META[key];
  return (
    <span
      className={`doc-status doc-status-${key} inline-flex h-6 items-center gap-1 whitespace-nowrap rounded-md px-2 text-[12px] font-semibold`}
      style={{ backgroundColor: meta.bg, color: meta.color }}
    >
      <Icon name={meta.icon} size={12} />
      {meta.label}
    </span>
  );
}

/** 항목명 매핑 출처 배지. AI가 추정한 매핑만 표시합니다(사전 매핑은 표시하지 않습니다). */
export function AiMappingBadge() {
  return (
    <span className="map-src map-src-ai shrink-0 rounded bg-[#F0ECFA] px-1 text-[10px] font-semibold leading-[14px] text-[#6B4FBB]">
      AI 추정
    </span>
  );
}
