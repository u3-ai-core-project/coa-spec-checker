import { useState } from 'react';
import { Modal } from '../../review/components/Modal';
import { api } from '../../review/shared/api';
import { errorMessage } from '../../review/shared/api/errors';
import type { PatchSpecResult, SpecItem } from '../../review/shared/api/types';
import { Icon } from '../../review/shared/components/Icon';

interface SpecRevertDialogProps {
  spec: SpecItem;
  onClose(): void;
  /** 서버가 되돌리기를 마쳤을 때. 재판정을 켰다면 응답의 rejudged_documents에 서버가 다시 판정한 문서가 있습니다. */
  onDone(result: PatchSpecResult, rejudge: boolean): void;
}

/**
 * 규격 항목 되돌리기 다이얼로그(POST /specs/{id}/revert). 가장 최근 변경을 이전 값으로 되돌리고, 사유가 필수이며 변경 이력으로 남습니다.
 * 되돌릴 이력이 없으면 서버가 409 NOTHING_TO_REVERT를 주고, 화면은 준비해 둔 문구를 보여 줍니다(이력이 있는지는 화면이 판단하지 않습니다).
 */
export function SpecRevertDialog({ spec, onClose, onDone }: SpecRevertDialogProps) {
  const [reason, setReason] = useState('');
  const [rejudge, setRejudge] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const canSubmit = reason.trim().length > 0 && !busy;

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      const result = await api.revertSpec(spec.id, { reason: reason.trim(), ...(rejudge ? { rejudge: true } : {}) });
      onDone(result, rejudge);
    } catch (failure) {
      setError(errorMessage(failure));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal width={500} gap="gap-4" labelledBy="spec-revert-title" onClose={busy ? () => undefined : onClose}>
      <div className="modal-icon flex h-12 w-12 items-center justify-center rounded-full bg-[#FBF0DF] text-[#9A5B00]">
        <Icon name="undo" size={24} />
      </div>
      <h4 id="spec-revert-title" className="modal-title text-[18px] font-bold">
        {spec.item_name} 되돌리기
      </h4>
      <p className="modal-body text-[14px] leading-relaxed text-[#5B616A]">
        이 항목의 <b className="font-semibold text-[#1F2328]">가장 최근 변경</b>을 이전 값으로 되돌립니다. 되돌리기도 변경 이력으로 남고, 한 번 더 되돌리면 되돌리기 전 값으로 돌아갑니다.
      </p>
      <div className="modal-field flex flex-col gap-1.5">
        <label className="modal-field-label flex items-center gap-1 text-[13px] font-semibold" htmlFor="spec-revert-reason">
          되돌리는 사유 <span className="text-[#C0342E]">*</span>
          <span className="text-[12px] font-normal text-[#8A9099]">(필수)</span>
        </label>
        <textarea
          id="spec-revert-reason"
          className="modal-textarea h-20 w-full resize-none rounded-lg border border-[#D0D4DA] bg-white px-3 py-2 text-[14px] placeholder:text-[#8A9099]"
          placeholder="되돌리는 사유를 입력해 주십시오."
          value={reason}
          disabled={busy}
          autoFocus
          onChange={(event) => setReason(event.target.value)}
        />
      </div>
      <label className="spec-revert-rejudge flex cursor-pointer items-start gap-2 text-[13px]">
        <input type="checkbox" className="mt-0.5 h-4 w-4" checked={rejudge} disabled={busy} onChange={(event) => setRejudge(event.target.checked)} />
        <span>
          <b className="font-semibold">되돌린 뒤 재판정</b>
          <span className="block text-[12px] text-[#5B616A]">이 규격 세트로 판정한 처분 전 문서를 되돌린 규격으로 서버가 다시 판정합니다.</span>
        </span>
      </label>
      {error && (
        <p role="alert" className="modal-error text-[12px] text-[#C0342E]">
          {error}
        </p>
      )}
      <div className="modal-actions flex justify-end gap-2 pt-1">
        <button type="button" onClick={onClose} disabled={busy} className="btn-cancel h-10 rounded-lg border border-[#D0D4DA] bg-white px-5 text-[14px] font-semibold">
          {error ? '닫기' : '취소'}
        </button>
        <button
          type="button"
          onClick={() => void submit()}
          disabled={!canSubmit}
          className={`btn-revert h-10 rounded-lg px-5 text-[14px] font-semibold ${canSubmit ? 'bg-[#9A5B00] text-white' : 'btn-disabled cursor-not-allowed bg-[#E3E5E8] text-[#8A9099]'}`}
        >
          {busy ? '되돌리는 중…' : '되돌리기'}
        </button>
      </div>
    </Modal>
  );
}
