import { useState } from 'react';
import { api } from '../shared/api';
import { ApiError, errorMessage } from '../shared/api/errors';
import type { DocumentDetail, Judgement, LotRecommendation, RejudgeResult, SpecSet, SpecSetRef } from '../shared/api/types';
import { Icon } from '../shared/components/Icon';
import { JUDGEMENT_META, JUDGEMENT_ORDER } from '../shared/domain/judgement';
import { RECOMMENDATION_META } from '../shared/domain/recommendation';
import { specSetName } from '../shared/domain/specSets';
import { isEditableStatus } from '../shared/domain/status';
import { useAsync } from '../shared/hooks/useAsync';
import { Modal } from './Modal';

interface RejudgeDialogProps {
  doc: DocumentDetail;
  /** 드롭다운에서 고른 규격 세트 */
  target: SpecSet;
  onClose(): void;
  /** 서버가 규격 세트 변경을 저장했을 때(새 결과를 불러올 차례) */
  onDone(): void;
  /** 처분 완료(409) 등으로 화면 상태가 서버와 다를 때(다시 불러오기) */
  onStale(): void;
}

/** 서버가 보낸 메시지를 그대로 보여 줍니다. 서버 메시지가 없으면 화면 안내 문구를 씁니다. */
function serverMessage(failure: unknown): string {
  if (failure instanceof ApiError && failure.message.trim()) return failure.message;
  return errorMessage(failure);
}

/** 이름 맵에 있으면 화면 이름, 없으면 서버 코드(와 버전)를 그대로 보여 줍니다. */
const specLabel = (ref: SpecSetRef | null) =>
  ref ? (specSetName(ref.code) ?? `${ref.code}${ref.version ? ` (${ref.version})` : ''}`) : '-';
const recommendationLabel = (value: LotRecommendation | null) => (value ? RECOMMENDATION_META[value].label : '-');
const judgementLabel = (value: Judgement | null) => (value ? JUDGEMENT_META[value].label : '없음');

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="rejudge-row grid grid-cols-[88px_1fr] items-start gap-x-3 text-[13px]">
      <span className="text-[12px] leading-5 text-[#8A9099]">{label}</span>
      <span className="font-semibold leading-5">{children}</span>
    </div>
  );
}

/** 서버가 계산한 미리보기(이전 → 이후)를 값 그대로 보여 줍니다. 화면에서 판정을 다시 계산하지 않습니다. */
function PreviewBody({ preview }: { preview: RejudgeResult }) {
  return (
    <div className="rejudge-preview flex flex-col gap-2.5">
      <Row label="적용 규격">
        {specLabel(preview.previous_spec_set)} → {specLabel(preview.spec_set)}
      </Row>
      <Row label="로트 권고">
        {recommendationLabel(preview.lot_recommendation_before)} → {recommendationLabel(preview.lot_recommendation_after)}
      </Row>
      <div className="rejudge-summary flex flex-wrap gap-1.5" aria-label="판정 집계 이전과 이후">
        {JUDGEMENT_ORDER.map((judgement) => {
          const meta = JUDGEMENT_META[judgement];
          const before = preview.summary_before[judgement];
          const after = preview.summary_after[judgement];
          return (
            <span
              key={judgement}
              className={`rejudge-count rejudge-count-${judgement} inline-flex items-center gap-1 whitespace-nowrap rounded-full px-2 py-1 text-[11px] font-semibold${
                before === after ? ' opacity-60' : ''
              }`}
              style={{ backgroundColor: meta.bg, color: meta.color }}
            >
              {meta.label}
              <b className="tabular-nums">
                {before} → {after}
              </b>
            </span>
          );
        })}
      </div>
      <div className="rejudge-changes flex flex-col gap-1">
        <span className="text-[12px] font-semibold text-[#8A9099]">
          판정이 바뀐 항목 · <span className="tabular-nums">{preview.changed_items.length}건</span>
        </span>
        {preview.changed_items.length === 0 ? (
          <p className="text-[13px] text-[#5B616A]">판정이 바뀐 항목이 없습니다.</p>
        ) : (
          <ul className="rejudge-change-list flex max-h-36 flex-col divide-y divide-[#E3E5E8] overflow-y-auto rounded-md border border-[#E3E5E8]">
            {preview.changed_items.map((change) => (
              <li key={change.item_name} className="rejudge-change flex items-center justify-between gap-3 px-3 py-1.5 text-[13px]">
                <span className="font-semibold">{change.item_name}</span>
                <span className="tabular-nums text-[#5B616A]">
                  {judgementLabel(change.before)} → {judgementLabel(change.after)}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

/**
 * 적용 규격 변경 다이얼로그. 열리면 서버에 미리보기(apply=false)를 요청해 규격 세트, 로트 권고, 판정 집계의 이전 → 이후와
 * 판정이 바뀐 항목을 서버 값 그대로 보여 줍니다. 처분 전 문서는 변경 사유(필수)를 적고 "적용"하면 서버가 저장합니다(apply=true).
 * 처분 완료 문서는 미리보기만 되고 "적용"은 비활성입니다.
 */
export function RejudgeDialog({ doc, target, onClose, onDone, onStale }: RejudgeDialogProps) {
  const previewQuery = useAsync(() => api.rejudgeDocument(doc.document_id, { spec_set_code: target.code }), [doc.document_id, target.code]);
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const [applyError, setApplyError] = useState<string | null>(null);

  const preview = previewQuery.data;
  const previewError = previewQuery.error && !preview ? serverMessage(previewQuery.error) : null;
  const applicable = isEditableStatus(doc.status);
  const canApply = applicable && preview !== null && reason.trim().length > 0 && !busy;
  const error = applyError ?? previewError;

  async function apply() {
    setBusy(true);
    setApplyError(null);
    try {
      await api.rejudgeDocument(doc.document_id, { spec_set_code: target.code, apply: true, reason: reason.trim() });
      onDone();
    } catch (failure) {
      setApplyError(serverMessage(failure));
      // 처분이 끝난 문서 등 상태가 바뀐 경우(409)에는 최신 상태를 다시 불러옵니다.
      if (failure instanceof ApiError && failure.status === 409) onStale();
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal width={560} gap="gap-3.5" labelledBy="rejudge-title" onClose={busy ? () => undefined : onClose}>
      <div className="modal-icon flex h-12 w-12 items-center justify-center rounded-full bg-[#EAEFFC] text-[#2B4FCB]">
        <Icon name="pencil" size={24} />
      </div>
      <h4 id="rejudge-title" className="modal-title text-[18px] font-bold">
        적용 규격 변경
      </h4>
      <p className="modal-body text-[13px] leading-relaxed text-[#5B616A]">
        <b className="font-semibold text-[#1F2328]">{specSetName(target.code) ?? target.code}</b> 기준으로 서버가 다시 판정한 결과를 미리 보여 줍니다. 적용하기 전에는 문서가 바뀌지 않습니다.
      </p>
      {!preview && !previewError && <p className="rejudge-loading text-[13px] text-[#5B616A]">서버가 미리보기를 계산하는 중입니다.</p>}
      {preview && <PreviewBody preview={preview} />}
      {preview && applicable && (
        <div className="modal-field flex flex-col gap-1.5">
          <label className="modal-field-label flex items-center gap-1 text-[13px] font-semibold" htmlFor="rejudge-reason">
            변경 사유 <span className="text-[#C0342E]">*</span>
            <span className="text-[12px] font-normal text-[#8A9099]">(필수)</span>
          </label>
          <textarea
            id="rejudge-reason"
            className="modal-textarea h-20 w-full resize-none rounded-lg border border-[#D0D4DA] bg-white px-3 py-2 text-[14px] placeholder:text-[#8A9099]"
            placeholder="적용 규격을 바꾸는 사유를 입력해 주십시오."
            value={reason}
            disabled={busy}
            onChange={(event) => setReason(event.target.value)}
          />
          <span className="modal-field-help text-[12px] text-[#8A9099]">사유는 검수 이력에 기록됩니다.</span>
        </div>
      )}
      {preview && !applicable && (
        <p className="rejudge-readonly-note text-[12px] font-semibold text-[#9A5B00]">처분이 끝난 문서는 미리보기만 볼 수 있고 적용할 수 없습니다.</p>
      )}
      {error && (
        <p role="alert" className="modal-error text-[12px] text-[#C0342E]">
          {error}
        </p>
      )}
      <div className="modal-actions flex justify-end gap-2 pt-1">
        <button
          type="button"
          onClick={onClose}
          disabled={busy}
          className="btn-cancel h-10 rounded-lg border border-[#D0D4DA] bg-white px-5 text-[14px] font-semibold"
        >
          {applicable && preview ? '취소' : '닫기'}
        </button>
        {preview && (
          <button
            type="button"
            onClick={() => void apply()}
            disabled={!canApply}
            title={applicable ? undefined : '처분이 끝난 문서는 규격 세트를 바꿔 적용할 수 없습니다.'}
            className={`btn-rejudge h-10 rounded-lg px-5 text-[14px] font-semibold ${
              canApply ? 'bg-[#2B4FCB] text-white' : 'btn-disabled cursor-not-allowed bg-[#E3E5E8] text-[#8A9099]'
            }`}
          >
            {busy ? '적용 중…' : '적용'}
          </button>
        )}
      </div>
    </Modal>
  );
}
