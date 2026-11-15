import { isResolved, type ReplyResult } from '../lib/replyResult';
import { Icon } from '../shared/components/Icon';
import { JUDGEMENT_META } from '../shared/domain/judgement';
import { REASON_CODE_LABEL } from '../shared/domain/exceptions';
import { RECOMMENDATION_META } from '../shared/domain/recommendation';

/** 시안 2-12b: 회신값을 넣은 뒤 서버가 다시 판정한 결과 줄. 항목 판정, 로트 권고, 판정별 건수의 변화를 응답 그대로 보여 줍니다. */
export function ReplyResultStrip({ result, onClose }: { result: ReplyResult; onClose(): void }) {
  const resolved = isResolved(result);
  const before = JUDGEMENT_META[result.beforeJudgement];
  const after = JUDGEMENT_META[result.after.judgement];
  const recBefore = RECOMMENDATION_META[result.beforeRecommendation];
  const recAfter = RECOMMENDATION_META[result.afterRecommendation];
  const sameRecommendation = result.beforeRecommendation === result.afterRecommendation;
  const reasonCode = result.after.reason_code ?? null;
  const tone = resolved ? 'bg-[#F1FAF4]' : 'bg-[#FFF7E6]';

  return (
    <div className={`reply-result flex flex-col gap-1 border-b border-[#E3E5E8] ${tone} px-5 py-2 text-[12px]`}>
      <div className="flex items-start justify-between gap-2">
        <span className={`flex items-center gap-1.5 font-semibold ${resolved ? 'text-[#177A46]' : 'text-[#8A5A00]'}`}>
          <Icon name={resolved ? 'check' : 'warn'} size={13} />
          {resolved ? '재판정 결과 · 예외가 해제되었습니다.' : '재판정 결과 · 예외가 남아 있습니다.'}
        </span>
        <button type="button" aria-label="재판정 결과 닫기" onClick={onClose} className="btn-close-result -mr-1 flex h-5 w-5 shrink-0 items-center justify-center rounded text-[#8A9099]">
          <Icon name="x" size={13} />
        </button>
      </div>
      <span className="flex flex-wrap items-center gap-x-3 gap-y-0.5 text-[#5B616A]">
        <span>
          {result.name} <b className="font-semibold" style={{ color: before.color }}>{before.label}</b> →{' '}
          <b className="font-semibold" style={{ color: after.color }}>{after.label}</b>
        </span>
        <span>
          로트 권고{' '}
          {sameRecommendation ? (
            <b className="font-semibold" style={{ color: recAfter.color }}>{`${recAfter.label} 유지`}</b>
          ) : (
            <>
              <b className="font-semibold" style={{ color: recBefore.color }}>{recBefore.label}</b> →{' '}
              <b className="font-semibold" style={{ color: recAfter.color }}>{recAfter.label}</b>
            </>
          )}
        </span>
        <span className="tabular-nums">
          {`적합 ${result.beforeSummary.pass} → ${result.afterSummary.pass}개 · ${before.label} ${result.beforeSummary[result.beforeJudgement]} → ${result.afterSummary[result.beforeJudgement]}개`}
        </span>
      </span>
      {!resolved && (
        <span className="text-[#5B616A]">
          {`사유: ${reasonCode ? (REASON_CODE_LABEL[reasonCode] ?? reasonCode) : '-'}${result.after.judgement_reason ? ` · ${result.after.judgement_reason}` : ''}`}
        </span>
      )}
    </div>
  );
}

/** 시안 2-12b: 해결된 항목 줄 아래의 "해결됨" 표시 */
export function ResolvedNote({ result }: { result: ReplyResult }) {
  const before = JUDGEMENT_META[result.beforeJudgement];
  return (
    <div className="item-resolved col-start-2 col-span-3 flex items-center gap-1 rounded-md bg-[#E7F5EC] px-2 py-1 text-[11px] font-semibold leading-snug text-[#177A46]">
      <Icon name="check" size={12} />
      {`해결됨 · ${before.label} → 적합${result.after.judgement_reason ? ` · ${result.after.judgement_reason}` : ''}`}
    </div>
  );
}
