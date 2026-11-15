import { useState } from 'react';
import { api } from '../shared/api';
import { ApiError, errorMessage } from '../shared/api/errors';
import type { DocumentListItem } from '../shared/api/types';
import { Icon } from '../shared/components/Icon';
import { DELETE_REASON_MAX_LENGTH, DELETE_REASON_MIN_LENGTH, cleanDeleteReason, isDeleteReasonValid } from '../shared/domain/deletion';
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

/**
 * 문서 삭제 확인 창. 삭제하면 추출 결과와 검수 이력, 원본 파일이 함께 지워지고 되돌릴 수 없습니다.
 * 삭제 사유(필수, 앞뒤 공백을 뺀 2~500자)를 입력해야 삭제할 수 있고, 서버가 삭제 기록(누가, 언제, 왜)을 남깁니다(백엔드 #65).
 */
export function DeleteDocumentDialog({ doc, onClose, onDone, onStale }: DeleteDocumentDialogProps) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [text, setText] = useState('');
  const { reason, length } = cleanDeleteReason(text);
  const reasonValid = isDeleteReasonValid(length);
  const canDelete = reasonValid && !busy;

  async function submit() {
    if (!reasonValid) return;
    setBusy(true);
    setError(null);
    try {
      await api.deleteDocument(doc.document_id, reason);
      onDone();
    } catch (failure) {
      setError(serverMessage(failure));
      // 사유가 서버 조건에 안 맞는 경우(400 REASON_REQUIRED)는 문서 상태가 바뀐 것이 아니라서 목록을 다시 불러오지 않습니다.
      if (failure instanceof ApiError && failure.status !== 0 && !(failure.status === 400 && failure.code === 'REASON_REQUIRED')) onStale();
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
        <br />
        삭제 기록(누가·언제·왜)이 남습니다.
      </p>
      <div className="modal-field flex flex-col gap-1.5">
        <label className="modal-field-label flex items-center gap-1 text-[13px] font-semibold" htmlFor="delete-reason">
          삭제 사유 <span className="text-[#C0342E]">*</span>
          <span className="text-[12px] font-normal text-[#8A9099]">(필수, {DELETE_REASON_MIN_LENGTH}~{DELETE_REASON_MAX_LENGTH}자)</span>
        </label>
        <textarea
          id="delete-reason"
          className="modal-textarea h-20 w-full resize-none rounded-lg border border-[#D0D4DA] bg-white px-3 py-2 text-[14px] placeholder:text-[#8A9099]"
          placeholder="삭제하는 사유를 입력해 주십시오."
          value={text}
          disabled={busy}
          autoFocus
          onChange={(event) => setText(event.target.value)}
        />
        <div className="modal-field-help flex justify-between text-[12px] text-[#8A9099]">
          <span>사유는 삭제 기록에 남습니다.</span>
          <span className={`delete-reason-count tabular-nums ${length > 0 && !reasonValid ? 'font-semibold text-[#C0342E]' : ''}`} aria-live="polite">
            {length} / {DELETE_REASON_MAX_LENGTH}자
          </span>
        </div>
      </div>
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
          disabled={!canDelete}
          onClick={() => void submit()}
          className={`btn-delete-confirm h-10 rounded-lg px-5 text-[14px] font-semibold ${
            !canDelete ? 'btn-disabled cursor-not-allowed bg-[#E3E5E8] text-[#8A9099]' : 'bg-[#C0342E] text-white'
          }`}
        >
          {busy ? '삭제 중' : '삭제'}
        </button>
      </div>
    </Modal>
  );
}
