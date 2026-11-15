import { useState } from 'react';
import { api } from '../shared/api';
import { errorMessage, isApiError } from '../shared/api/errors';
import type { DocumentDetail, ExtractionResult, HoldFollowUp, LotRecommendation } from '../shared/api/types';
import { Icon } from '../shared/components/Icon';
import { RecommendationBadge } from '../shared/components/badges';
import { DOCUMENT_ISSUE_LABEL } from '../shared/domain/exceptions';
import { sumSummary, JUDGEMENT_META, JUDGEMENT_ORDER } from '../shared/domain/judgement';
import {
  DISPOSITION_META,
  DISPOSITION_ORDER,
  type Disposition,
  FOLLOW_UP_LABEL,
  FOLLOW_UP_ORDER,
  dispositionForRecommendation,
} from '../shared/domain/recommendation';
import { isDispositionLocked, isReasonRequired, suggestRejectReason, withEuro } from '../lib/completion';
import { Modal } from './Modal';

interface CompleteDialogProps {
  doc: DocumentDetail;
  extraction: ExtractionResult;
  /** 수정 또는 확인하지 않은 신뢰도 낮음 항목 수 */
  pending: number;
  /** 후속 조치 버튼에서 열 때의 시작 값(보류 + 후속 조치 선택) */
  initialFollowUp?: HoldFollowUp;
  /** [v1.4] 서버가 추천한 보류 후속 조치(GET follow-ups의 suggested_follow_up). 보류를 고르면 기본으로 선택합니다. */
  suggestedFollowUp?: HoldFollowUp | null;
  onClose(): void;
  /** 처분 또는 보류가 성공했을 때. 완료한 처분(보류 포함)을 알려 줍니다. */
  onDone(completed: Disposition): void;
  /** 서버 응답으로 화면 상태가 바뀐 것을 알게 됐을 때(다시 불러오기) */
  onStale(): void;
}

/**
 * [v1.4안] 문서 수준 문제(document_issues)가 있으면 항목에 문제가 없어도 보류 권고입니다.
 * issueCount는 문서 수준 문제 수, itemIssues는 판정 불가, 누락, 확인 필요 항목이 있는지입니다.
 */
function ResultText({ recommendation, issueCount, itemIssues }: { recommendation: LotRecommendation; issueCount: number; itemIssues: boolean }) {
  if (recommendation === 'reject') {
    return (
      <>
        부적합 항목이 있어 이 로트는 <b className="font-semibold text-[#C0342E]">불합격</b>을 권고합니다.
      </>
    );
  }
  if (recommendation === 'hold') {
    const cause =
      issueCount > 0 && !itemIssues
        ? '문서 수준 문제가 있어'
        : issueCount > 0
          ? '판정 불가, 누락 또는 확인 필요 항목과 문서 수준 문제가 있어'
          : '판정 불가, 누락 또는 확인 필요 항목이 있어';
    return (
      <>
        {cause} 이 로트는 <b className="font-semibold text-[#5B616A]">보류</b>를 권고합니다.
      </>
    );
  }
  return (
    <>
      모든 항목이 적합하여 이 로트는 <b className="font-semibold text-[#177A46]">승인</b>을 권고합니다.
    </>
  );
}

function followUpSentence(undetermined: number, missing: number): string | null {
  if (undetermined > 0 && missing > 0) {
    return `판정 불가 ${undetermined}건과 누락 ${missing}건은 후속 조치(실측값 요청, 자체 시험 요청)가 필요합니다.`;
  }
  if (undetermined > 0) return `판정 불가 ${undetermined}건은 후속 조치(실측값 요청)가 필요합니다.`;
  if (missing > 0) return `누락 ${missing}건은 후속 조치(자체 시험 요청)가 필요합니다.`;
  return null;
}

/**
 * 검수 완료 확인 다이얼로그 (시안 2-2, 2-2b, 2-2c).
 * 판정 집계와 AI 권고는 서버 응답을 그대로 보여 주고, 담당자가 처분(승인, 조건부 승인, 불합격) 또는 보류를 선택합니다.
 */
export function CompleteDialog({ doc, extraction, pending, initialFollowUp, suggestedFollowUp = null, onClose, onDone, onStale }: CompleteDialogProps) {
  const recommendation = extraction.lot_recommendation;
  const aiDisposition = dispositionForRecommendation(recommendation);
  /** 신뢰도 낮음 항목이 남아 있으면 처분(/approve)은 서버가 거절합니다. 보류(/hold)에는 이 제한이 없습니다. */
  const blocked = pending > 0;

  const [disposition, setDisposition] = useState<Disposition>(initialFollowUp ? 'hold' : aiDisposition);
  const [followUp, setFollowUp] = useState<HoldFollowUp | null>(initialFollowUp ?? (aiDisposition === 'hold' ? suggestedFollowUp : null));
  const [reason, setReason] = useState(() => (!initialFollowUp && !blocked && aiDisposition === 'reject' ? suggestRejectReason(extraction.items) : ''));
  const [reasonTouched, setReasonTouched] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const { summary } = extraction;
  const total = extraction.items.length;
  const isHold = disposition === 'hold';
  const reasonRequired = isReasonRequired(disposition, recommendation);
  const reasonOk = !reasonRequired || reason.trim().length > 0;
  // 처분은 확인 필요가 남아 있으면 막고, 보류는 그대로 할 수 있습니다.
  const approvalLocked = blocked && !isHold;
  const canSubmit = !approvalLocked && !busy && reasonOk && (!isHold || followUp !== null);
  const meta = DISPOSITION_META[disposition];
  const sentence = followUpSentence(summary.undetermined, summary.missing);
  const issues = extraction.document_issues ?? [];
  const itemIssues = summary.undetermined + summary.missing + summary.check > 0;

  /** 확인 필요 항목이 남아 있으면 "승인"만 고를 수 없습니다. 조건부 승인, 불합격, 보류는 어떤 순서로든 바꿀 수 있습니다(완료는 막힘). */
  const isChoiceBlocked = (candidate: Disposition) => blocked && candidate === 'accept';

  function choose(next: Disposition) {
    if (isChoiceBlocked(next) || isDispositionLocked(next, recommendation)) return;
    setDisposition(next);
    // 보류를 고르고 후속 조치를 아직 정하지 않았으면 서버가 추천한 것을 기본으로 선택합니다.
    if (next === 'hold' && followUp === null && suggestedFollowUp) setFollowUp(suggestedFollowUp);
    // 사용자가 직접 쓰지 않은 사유는 제안 문구이므로, 처분을 바꾸면 그에 맞게 다시 채우거나 비웁니다.
    // 확인 필요가 남은 동안에는 처음 열 때와 같게 비워 둡니다.
    if (!reasonTouched) setReason(next === 'reject' && !blocked ? suggestRejectReason(extraction.items) : '');
  }

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      if (disposition === 'hold') {
        if (followUp === null) return;
        await api.hold(doc.document_id, { follow_up: followUp, reason: reason.trim() });
      } else {
        await api.approve(doc.document_id, { decision: disposition, reason: reason.trim() || null });
      }
      onDone(disposition);
    } catch (failure) {
      setError(errorMessage(failure));
      if (isApiError(failure, 'PENDING_LOW_CONFIDENCE_ITEMS') || isApiError(failure, 'ALREADY_APPROVED') || isApiError(failure, 'INVALID_DECISION')) {
        onStale();
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal width={560} labelledBy="complete-title" onClose={onClose}>
      <div className="flex items-center gap-3">
        <div className="modal-icon flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-[#EAEFFC] text-[#2B4FCB]">
          <Icon name="info" size={20} />
        </div>
        <div className="flex flex-col">
          <h4 id="complete-title" className="modal-title text-[18px] font-bold">
            검수 완료 확인
          </h4>
          <span className="text-[12px] tabular-nums text-[#8A9099]">{doc.file_name}</span>
        </div>
      </div>

      <div className="modal-summary-wrap flex flex-col gap-1">
        <div className="modal-summary grid grid-cols-5 divide-x divide-[#E3E5E8] rounded-lg border border-[#E3E5E8] bg-[#F9FAFB]">
          {JUDGEMENT_ORDER.map((judgement) => (
            <div key={judgement} className={`summary-cell summary-${judgement} flex flex-col items-center gap-0.5 py-2.5`}>
              <span className="text-[12px] text-[#5B616A]">{JUDGEMENT_META[judgement].label}</span>
              <span
                className="text-[22px] font-bold leading-none tabular-nums"
                style={{ color: JUDGEMENT_META[judgement].color }}
              >
                {summary[judgement]}
              </span>
            </div>
          ))}
        </div>
        <span className="modal-summary-total text-right text-[11px] text-[#8A9099]">
          판정 합계 {`${sumSummary(summary)}개`} = 전체 항목 {`${total}개`}
        </span>
      </div>

      {blocked && (
        <div className="modal-blocker flex items-start gap-2 rounded-lg border border-[#9A5B00]/30 bg-[#FBF0DF] px-3 py-2.5 text-[13px] text-[#9A5B00]">
          <span className="mt-0.5 shrink-0">
            <Icon name="info" />
          </span>
          <div className="flex flex-col gap-0.5">
            <span className="modal-blocker-count font-semibold">{`신뢰도 낮음 항목 ${pending}건이 남아 있습니다.`}</span>
            <span className="modal-blocker-msg">남은 항목을 모두 확인한 뒤에 검수를 완료할 수 있습니다.</span>
          </div>
        </div>
      )}

      <div className="modal-ai flex flex-col gap-1.5 rounded-lg border border-[#E3E5E8] px-3 py-2.5 text-[13px]">
        <div className="flex items-center gap-2">
          <RecommendationBadge recommendation={recommendation} />
        </div>
        <p className="modal-result text-[#1F2328]">
          <ResultText recommendation={recommendation} issueCount={issues.length} itemIssues={itemIssues} />
        </p>
        {sentence && <p className="modal-followup text-[12px] text-[#5B616A]">{sentence}</p>}
        {issues.length > 0 && (
          <p className="modal-issues text-[12px] text-[#5B616A]">
            {`문서 수준 문제 ${issues.length}건: ${issues.map((issue) => DOCUMENT_ISSUE_LABEL[issue.code] ?? issue.code).join(', ')}`}
          </p>
        )}
      </div>

      <div className={`modal-disposition flex flex-col gap-1.5`}>
        <span className="text-[13px] font-semibold" id="disposition-label">
          담당자 처분 선택
        </span>
        <div className="disp-cards grid grid-cols-4 gap-2" role="radiogroup" aria-labelledby="disposition-label">
          {DISPOSITION_ORDER.map((candidate) => {
            const candidateMeta = DISPOSITION_META[candidate];
            // 선택할 수 없는 카드(불합격 권고 로트의 승인, 확인 필요가 남은 로트의 승인)만 회색으로 막고,
            // 나머지 카드는 회색 없이 누를 수 있습니다. 확인 필요가 남았을 때 완료 버튼은 아래에서 비활성으로 둡니다.
            const locked = isDispositionLocked(candidate, recommendation) || isChoiceBlocked(candidate);
            const on = candidate === disposition && !locked;
            let cardClass = 'border-[#D0D4DA] bg-white';
            if (locked) cardClass = 'border-[#E3E5E8] bg-[#F4F5F7] cursor-not-allowed';
            return (
              <button
                key={candidate}
                type="button"
                role="radio"
                aria-checked={on}
                aria-disabled={locked}
                disabled={isChoiceBlocked(candidate)}
                onClick={() => choose(candidate)}
                className={`disp-card disp-card-${candidate} flex h-[58px] flex-col items-start justify-center gap-1 rounded-lg border px-3 text-left ${cardClass}`}
                style={on ? { borderColor: candidateMeta.color, boxShadow: `0 0 0 1px ${candidateMeta.color}` } : undefined}
              >
                <span className={`flex items-center gap-2 text-[13px] font-semibold leading-4${locked ? ' text-[#B6BBC4]' : ''}`}>
                  {locked ? (
                    <span className="h-4 w-4 rounded-full border-2 border-[#D0D4DA] bg-[#EEF0F3]" />
                  ) : on ? (
                    <span className="flex h-4 w-4 items-center justify-center rounded-full border-2" style={{ borderColor: candidateMeta.color }}>
                      <span className="h-2 w-2 rounded-full" style={{ backgroundColor: candidateMeta.color }} />
                    </span>
                  ) : (
                    <span className="h-4 w-4 rounded-full border-2 border-[#B6BBC4]" />
                  )}
                  {candidateMeta.label}
                </span>
                <span className="flex h-[14px] items-center">
                  {locked ? (
                    <span className="inline-block rounded bg-[#E3E5E8] px-1 text-[10px] font-semibold leading-[14px] text-[#8A9099]">선택 불가</span>
                  ) : candidate === aiDisposition ? (
                    <span className="inline-block rounded bg-[#EAEFFC] px-1 text-[10px] font-semibold leading-[14px] text-[#2B4FCB]">AI 권고</span>
                  ) : null}
                </span>
              </button>
            );
          })}
        </div>
        <div className="disp-hints flex flex-col gap-1 pt-0.5 text-[12px] leading-4 text-[#5B616A]">
          {recommendation === 'reject' && (
            <p className="disp-hint-locked flex items-center gap-1.5">
              <span className="shrink-0">
                <Icon name="info" size={13} />
              </span>
              부적합 항목이 있어 승인할 수 없습니다.
            </p>
          )}
          <p className="disp-hint-reason flex items-center gap-1.5">
            <span className="shrink-0">
              <Icon name="info" size={13} />
            </span>
            AI 권고와 다른 처분을 선택하면 사유 입력이 필수입니다.
          </p>
        </div>
      </div>

      {isHold && (
        <div className={`modal-hold flex flex-col gap-1.5`}>
          <span className="modal-field-label text-[13px] font-semibold" id="followup-label">
            후속 조치 <span className="text-[#C0342E]">*</span>{' '}
            <span className="text-[12px] font-normal text-[#8A9099]">필수 선택입니다.</span>
          </span>
          <div className="hold-options grid grid-cols-4 gap-2" role="radiogroup" aria-labelledby="followup-label">
            {FOLLOW_UP_ORDER.map((option) => {
              const on = followUp === option;
              return (
                <button
                  key={option}
                  type="button"
                  role="radio"
                  aria-checked={on}
                  onClick={() => setFollowUp(option)}
                  className={`hold-option flex h-9 items-center justify-center rounded-lg border px-2 text-[13px] font-semibold leading-4 ${
                    on ? 'border-[#2B4FCB] bg-[#EAEFFC] text-[#2B4FCB]' : 'border-[#D0D4DA] bg-white text-[#1F2328]'
                  }`}
                >
                  {FOLLOW_UP_LABEL[option]}
                  {option === suggestedFollowUp && <span className="ml-1 text-[10px] font-semibold text-[#2B4FCB]">추천</span>}
                </button>
              );
            })}
          </div>
        </div>
      )}

      <div className={`modal-field flex flex-col gap-1.5`}>
        <label className="modal-field-label text-[13px] font-semibold" htmlFor="complete-reason">
          처분 사유 <span className="text-[#C0342E]">*</span>{' '}
          <span className="text-[12px] font-normal text-[#8A9099]">
            {isHold ? '필수 입력입니다.' : '조건부 승인과 불합격은 필수 입력입니다.'}
          </span>
        </label>
        <textarea
          id="complete-reason"
          className="modal-textarea h-14 w-full resize-none rounded-lg border border-[#D0D4DA] bg-white px-3 py-2 text-[13px]"
          placeholder={isHold ? '보류 사유를 입력해 주십시오.' : '처분 사유를 입력해 주십시오.'}
          value={reason}
          onChange={(event) => {
            setReason(event.target.value);
            setReasonTouched(true);
          }}
        />
      </div>

      {approvalLocked && (
        <p className="modal-locked-reason text-[12px] font-semibold text-[#9A5B00]">
          {`신뢰도 낮음 항목 ${pending}건이 남아 있어 ${withEuro(meta.label)}는 완료할 수 없습니다. 남은 항목을 확인하거나, 보류로 완료해 주십시오.`}
        </p>
      )}
      <p className="modal-warning text-[12px] text-[#5B616A]">완료 후에는 값을 수정할 수 없습니다.</p>
      {error && <p className="text-[12px] text-[#C0342E]">{error}</p>}

      <div className="modal-actions flex justify-end gap-2">
        <button
          type="button"
          onClick={onClose}
          className="btn-cancel h-10 rounded-lg border border-[#D0D4DA] bg-white px-5 text-[14px] font-semibold"
        >
          취소
        </button>
        <button
          type="button"
          disabled={!canSubmit}
          onClick={() => void submit()}
          className={`btn-approve h-10 rounded-lg px-5 text-[14px] font-semibold ${
            canSubmit ? 'text-white' : 'btn-disabled cursor-not-allowed bg-[#E3E5E8] text-[#8A9099]'
          }`}
          style={canSubmit ? { backgroundColor: meta.color } : undefined}
        >
          {withEuro(meta.label)} 검수 완료
        </button>
      </div>
    </Modal>
  );
}
