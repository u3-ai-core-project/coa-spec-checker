import { useState } from 'react';
import { api } from '../shared/api';
import { errorMessage, isApiError } from '../shared/api/errors';
import type { DocumentDetail } from '../shared/api/types';
import { Icon } from '../shared/components/Icon';
import { DISPOSITION_META } from '../shared/domain/recommendation';
import { Modal } from './Modal';

interface ApprovalCancelDialogProps {
  doc: DocumentDetail;
  onClose(): void;
  /** 승인 취소가 성공했을 때 */
  onDone(): void;
  /** 이미 취소됐거나 권한이 바뀐 것처럼 화면 상태가 서버와 다를 때(다시 불러오기) */
  onStale(): void;
}

/** 승인 취소 다이얼로그 (시안 2-6). 관리자만 열 수 있고 사유가 필수입니다. 취소하면 문서가 검수 단계로 돌아갑니다. */
export function ApprovalCancelDialog({ doc, onClose, onDone, onStale }: ApprovalCancelDialogProps) {
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const canSubmit = reason.trim().length > 0 && !busy;
  const decision = doc.final_decision ? DISPOSITION_META[doc.final_decision].label : null;

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      await api.cancelApproval(doc.document_id, { reason: reason.trim() });
      onDone();
    } catch (failure) {
      setError(errorMessage(failure));
      if (isApiError(failure, 'NOT_APPROVED') || isApiError(failure, 'FORBIDDEN')) onStale();
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal width={500} gap="gap-4" labelledBy="cancel-title" onClose={onClose}>
      <div className="modal-icon flex h-12 w-12 items-center justify-center rounded-full bg-[#FBEAE9] text-[#C0342E]">
        <Icon name="undo" size={24} />
      </div>
      <h4 id="cancel-title" className="modal-title text-[18px] font-bold">
        승인 취소
      </h4>
      <p className="modal-body text-[14px] leading-relaxed text-[#5B616A]">
        <b className="font-semibold text-[#1F2328]">검수 단계로 되돌립니다.</b>
        <br />
        승인 취소 후에는 값을 다시 수정할 수 있으며, 검수 완료를 다시 진행해야 합니다.
        {decision ? ` 기존 처분 결과(${decision})는 이력에 보존됩니다.` : ' 기존 처분 결과는 이력에 보존됩니다.'}
      </p>
      <div className="modal-field flex flex-col gap-1.5">
        <label className="modal-field-label flex items-center gap-1 text-[13px] font-semibold" htmlFor="cancel-reason">
          취소 사유 <span className="text-[#C0342E]">*</span>
          <span className="text-[12px] font-normal text-[#8A9099]">(필수)</span>
        </label>
        <textarea
          id="cancel-reason"
          className="modal-textarea h-24 w-full resize-none rounded-lg border border-[#D0D4DA] bg-white px-3 py-2.5 text-[14px] placeholder:text-[#8A9099]"
          placeholder="승인을 취소하는 사유를 입력해 주십시오."
          value={reason}
          autoFocus
          onChange={(event) => setReason(event.target.value)}
        />
        <div className="modal-field-help flex justify-between text-[12px] text-[#8A9099]">
          <span>사유는 승인 이력에 기록됩니다.</span>
        </div>
      </div>
      {error && <p className="text-[12px] text-[#C0342E]">{error}</p>}
      <div className="modal-actions flex justify-end gap-2 pt-1">
        <button
          type="button"
          onClick={onClose}
          className="btn-cancel h-10 rounded-lg border border-[#D0D4DA] bg-white px-5 text-[14px] font-semibold"
        >
          닫기
        </button>
        <button
          type="button"
          disabled={!canSubmit}
          onClick={() => void submit()}
          className={`btn-cancel-approval h-10 rounded-lg px-5 text-[14px] font-semibold ${
            canSubmit ? 'bg-[#C0342E] text-white' : 'btn-disabled cursor-not-allowed bg-[#E3E5E8] text-[#8A9099]'
          }`}
        >
          승인 취소
        </button>
      </div>
    </Modal>
  );
}
