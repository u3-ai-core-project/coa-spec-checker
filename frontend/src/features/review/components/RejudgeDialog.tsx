import { useState } from 'react';
import { api } from '../shared/api';
import { ApiError, errorMessage } from '../shared/api/errors';
import type { DocumentDetail, SpecSet } from '../shared/api/types';
import { Icon } from '../shared/components/Icon';
import { Modal } from './Modal';

interface RejudgeDialogProps {
  doc: DocumentDetail;
  /** 새로 적용할 규격 세트 */
  target: SpecSet;
  onClose(): void;
  /** 서버가 다시 판정을 마쳤을 때 */
  onDone(): void;
  /** 처분 완료(409) 등으로 화면 상태가 서버와 다를 때(다시 불러오기) */
  onStale(): void;
}

/** 서버가 보낸 메시지를 그대로 보여 줍니다. 서버 메시지가 없으면 화면 안내 문구를 씁니다. */
function serverMessage(failure: unknown): string {
  if (failure instanceof ApiError && failure.message.trim()) return failure.message;
  return errorMessage(failure);
}

/** 적용 규격 변경 확인 다이얼로그. 확인하면 서버가 문서를 새 규격 세트로 다시 판정하고, 이 화면은 그 결과만 보여 줍니다. */
export function RejudgeDialog({ doc, target, onClose, onDone, onStale }: RejudgeDialogProps) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      await api.rejudgeDocument(doc.document_id, target.code);
      onDone();
    } catch (failure) {
      setError(serverMessage(failure));
      // 처분이 끝난 문서 등 상태가 바뀐 경우(409)에는 최신 상태를 다시 불러옵니다.
      if (failure instanceof ApiError && failure.status === 409) onStale();
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal width={500} gap="gap-4" labelledBy="rejudge-title" onClose={busy ? () => undefined : onClose}>
      <div className="modal-icon flex h-12 w-12 items-center justify-center rounded-full bg-[#EAEFFC] text-[#2B4FCB]">
        <Icon name="pencil" size={24} />
      </div>
      <h4 id="rejudge-title" className="modal-title text-[18px] font-bold">
        적용 규격 변경
      </h4>
      <p className="modal-body text-[14px] leading-relaxed text-[#5B616A]">
        이 문서의 적용 규격을{' '}
        <b className="font-semibold text-[#1F2328]">{doc.spec_set_code ?? '지정되지 않음'}</b> 에서{' '}
        <b className="font-semibold text-[#1F2328]">{target.code}</b>
        (으)로 바꾸고 서버가 판정을 다시 계산합니다.
        <br />
        항목 판정과 로트 권고가 달라질 수 있습니다.
      </p>
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
          {error ? '닫기' : '취소'}
        </button>
        {!error && (
          <button
            type="button"
            onClick={() => void submit()}
            disabled={busy}
            className={`btn-rejudge h-10 rounded-lg px-5 text-[14px] font-semibold ${
              busy ? 'btn-disabled cursor-not-allowed bg-[#E3E5E8] text-[#8A9099]' : 'bg-[#2B4FCB] text-white'
            }`}
          >
            {busy ? '다시 판정 중…' : '다시 판정'}
          </button>
        )}
      </div>
    </Modal>
  );
}
