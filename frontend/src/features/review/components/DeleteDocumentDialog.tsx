import { useState } from 'react';
import { api } from '../shared/api';
import { ApiError, errorMessage } from '../shared/api/errors';
import type { DocumentListItem } from '../shared/api/types';
import { Icon } from '../shared/components/Icon';
import { Modal } from './Modal';

interface DeleteDocumentDialogProps {
  doc: DocumentListItem;
  onClose(): void;
  /** 삭제가 성공했을 때 */
  onDone(): void;
  /** 서버가 거절했을 때(이미 처분됨, 권한 없음, 이미 지워짐 등). 목록이 서버와 다를 수 있으니 다시 불러옵니다. */
  onStale(): void;
}

/** 서버가 준 메시지를 그대로 보여 줍니다. 서버 메시지가 없거나 연결 오류면 공통 안내 문구를 씁니다. */
function serverMessage(failure: unknown): string {
  return failure instanceof ApiError && failure.message ? failure.message : errorMessage(failure);
}

/** 문서 삭제 확인 창. 삭제하면 추출 결과와 검수 이력, 원본 파일이 함께 지워지고 되돌릴 수 없습니다. */
export function DeleteDocumentDialog({ doc, onClose, onDone, onStale }: DeleteDocumentDialogProps) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      await api.deleteDocument(doc.document_id);
      onDone();
    } catch (failure) {
      setError(serverMessage(failure));
      if (failure instanceof ApiError && failure.status !== 0) onStale();
      setBusy(false);
    }
  }

  return (
    <Modal width={500} gap="gap-4" labelledBy="delete-title" onClose={busy ? () => undefined : onClose}>
      <div className="modal-icon flex h-12 w-12 items-center justify-center rounded-full bg-[#FBEAE9] text-[#C0342E]">
        <Icon name="trash" size={24} />
      </div>
      <h4 id="delete-title" className="modal-title text-[18px] font-bold">
        문서 삭제
      </h4>
      <p className="modal-body text-[14px] leading-relaxed text-[#5B616A]">
        <b className="font-semibold text-[#1F2328] break-all">{doc.file_name}</b> 문서를 삭제합니다.
        <br />
        추출 결과, 검수 이력, 원본 파일이 함께 지워지며 <b className="font-semibold text-[#C0342E]">되돌릴 수 없습니다.</b>
      </p>
      {error && (
        <p className="delete-error text-[12px] text-[#C0342E]" role="alert">
          {error}
        </p>
      )}
      <div className="modal-actions flex justify-end gap-2 pt-1">
        <button
          type="button"
          disabled={busy}
          onClick={onClose}
          className="btn-cancel h-10 rounded-lg border border-[#D0D4DA] bg-white px-5 text-[14px] font-semibold"
        >
          닫기
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={() => void submit()}
          className={`btn-delete-confirm h-10 rounded-lg px-5 text-[14px] font-semibold ${
            busy ? 'btn-disabled cursor-not-allowed bg-[#E3E5E8] text-[#8A9099]' : 'bg-[#C0342E] text-white'
          }`}
        >
          {busy ? '삭제 중' : '삭제'}
        </button>
      </div>
    </Modal>
  );
}
