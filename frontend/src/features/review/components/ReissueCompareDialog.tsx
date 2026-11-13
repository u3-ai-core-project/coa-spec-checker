import { useState } from 'react';
import { api } from '../shared/api';
import { errorMessage } from '../shared/api/errors';
import type { DocumentDetail, ReissueVersion } from '../shared/api/types';
import { DispositionBadge, RecommendationBadge, StatusBadge } from '../shared/components/badges';
import { formatDateTime } from '../shared/domain/format';
import { dispositionOf } from '../shared/domain/recommendation';
import { useAsync } from '../shared/hooks/useAsync';
import { Modal } from './Modal';

interface ReissueCompareDialogProps {
  doc: DocumentDetail;
  onClose(): void;
  /** 서버가 기준 버전 선택을 저장했을 때(상세를 다시 불러올 차례) */
  onDone(): void;
}

function Cell({ children, head = false }: { children: React.ReactNode; head?: boolean }) {
  return <div className={`reissue-cell min-w-0 break-all px-2 py-1.5 text-[12px] ${head ? 'font-semibold' : ''}`}>{children}</div>;
}

/**
 * 버전 비교 다이얼로그. GET /reissue/{id}가 주는 같은 로트의 CoA들(versions)을 나란히 보여 주고(서버가 주는 필드만),
 * 하나를 기준 버전으로 골라 사유(필수)와 함께 POST /reissue/{id}/base로 선택합니다. 상태와 가능 여부는 서버가 정합니다.
 */
export function ReissueCompareDialog({ doc, onClose, onDone }: ReissueCompareDialogProps) {
  const query = useAsync(() => api.getReissue(doc.document_id), [doc.document_id]);
  const info = query.data;
  const versions: ReissueVersion[] = info?.versions ?? [];
  const [picked, setPicked] = useState<string | null>(null);
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // 이미 기준 버전이 정해져 있으면 그것이 처음 선택된 상태입니다.
  const selected = picked ?? info?.base_document_id ?? null;
  const canSubmit = selected !== null && reason.trim().length > 0 && !busy;

  async function submit() {
    if (!selected) return;
    setBusy(true);
    setError(null);
    try {
      await api.setReissueBase(doc.document_id, { base_document_id: selected, reason: reason.trim() });
      onDone();
    } catch (failure) {
      setError(errorMessage(failure));
    } finally {
      setBusy(false);
    }
  }

  // 같은 로트의 CoA가 많아도(예: 10개) 열이 좁아지지 않게 열마다 최소 폭을 주고, 넘치면 가로로 스크롤합니다.
  const columns = `88px repeat(${Math.max(versions.length, 1)}, minmax(150px, 1fr))`;
  const rows: Array<{ label: string; render(version: ReissueVersion): React.ReactNode }> = [
    {
      label: '파일명',
      render: (version) => (
        <>
          <span className="font-semibold">{version.file_name}</span>
          {version.document_id === doc.document_id && <span className="ml-1 rounded bg-[#EAEFFC] px-1 text-[10px] font-semibold text-[#2B4FCB]">현재 문서</span>}
        </>
      ),
    },
    { label: '업로드 시각', render: (version) => <span className="tabular-nums">{formatDateTime(version.uploaded_at)}</span> },
    { label: '상태', render: (version) => <StatusBadge status={version.status} /> },
    {
      label: 'AI 권고',
      render: (version) => (version.lot_recommendation ? <RecommendationBadge recommendation={version.lot_recommendation} compact /> : <span className="text-[#B6BBC4]">-</span>),
    },
    {
      label: '담당자 처분',
      render: (version) => {
        const disposition = dispositionOf(version);
        return disposition ? <DispositionBadge disposition={disposition} compact /> : <span className="text-[#B6BBC4]">-</span>;
      },
    },
    { label: '처분 일시', render: (version) => <span className="tabular-nums">{version.approved_at ? formatDateTime(version.approved_at) : '-'}</span> },
  ];

  return (
    <Modal width={760} gap="gap-3.5" labelledBy="reissue-title" onClose={busy ? () => undefined : onClose}>
      <h4 id="reissue-title" className="modal-title text-[18px] font-bold">
        버전 비교 · 같은 로트의 CoA
      </h4>
      <p className="modal-body text-[13px] leading-relaxed text-[#5B616A]">
        기준 버전을 고르면 그 문서만 처분할 수 있습니다. 보류는 기준 버전을 고르기 전에도 할 수 있습니다.
      </p>
      {query.loading && !info && <p className="text-[13px] text-[#5B616A]">불러오는 중입니다.</p>}
      {query.error != null && !info && <p role="alert" className="text-[12px] text-[#C0342E]">{errorMessage(query.error)}</p>}
      {info && versions.length === 0 && <p className="text-[13px] text-[#5B616A]">같은 로트의 다른 CoA가 없습니다.</p>}
      {info && versions.length > 0 && (
        <div className="reissue-compare max-h-[360px] overflow-auto rounded-lg border border-[#E3E5E8]" role="radiogroup" aria-label="기준 버전 선택">
          <div className="grid" style={{ gridTemplateColumns: columns }}>
            <div className="sticky left-0 z-[1] bg-white">
              <Cell head>
                <span className="text-[#8A9099]">로트 {info.lot_no ?? '-'}</span>
              </Cell>
            </div>
            {versions.map((version) => (
              <label
                key={version.document_id}
                className={`reissue-pick flex cursor-pointer items-center gap-1.5 border-l border-[#E3E5E8] px-2 py-1.5 text-[12px] font-semibold ${
                  selected === version.document_id ? 'bg-[#EAEFFC] text-[#2B4FCB]' : ''
                }`}
              >
                <input type="radio" name="reissue-base" value={version.document_id} checked={selected === version.document_id} disabled={busy} onChange={() => setPicked(version.document_id)} />
                {version.is_base ? '기준 버전' : '기준으로 선택'}
              </label>
            ))}
            {rows.map((row) => (
              <div key={row.label} className="contents">
                <div className="reissue-label sticky left-0 z-[1] border-t border-[#E3E5E8] bg-[#F9FAFB] px-2 py-1.5 text-[12px] text-[#8A9099]">{row.label}</div>
                {versions.map((version) => (
                  <div key={version.document_id} className="reissue-version border-l border-t border-[#E3E5E8]">
                    <Cell>{row.render(version)}</Cell>
                  </div>
                ))}
              </div>
            ))}
          </div>
        </div>
      )}
      {info?.status === 'resolved' && info.decided_reason && (
        <p className="reissue-decided text-[12px] text-[#5B616A]">
          선택 사유: <span className="font-semibold text-[#1F2328]">{info.decided_reason}</span>
        </p>
      )}
      {info && versions.length > 0 && (
        <div className="modal-field flex flex-col gap-1.5">
          <label className="modal-field-label flex items-center gap-1 text-[13px] font-semibold" htmlFor="reissue-reason">
            선택 사유 <span className="text-[#C0342E]">*</span>
            <span className="text-[12px] font-normal text-[#8A9099]">(필수)</span>
          </label>
          <textarea
            id="reissue-reason"
            className="modal-textarea h-16 w-full resize-none rounded-lg border border-[#D0D4DA] bg-white px-3 py-2 text-[14px] placeholder:text-[#8A9099]"
            placeholder="이 문서를 기준 버전으로 선택하는 사유를 입력해 주십시오."
            value={reason}
            disabled={busy}
            onChange={(event) => setReason(event.target.value)}
          />
        </div>
      )}
      {error && (
        <p role="alert" className="modal-error text-[12px] text-[#C0342E]">
          {error}
        </p>
      )}
      <div className="modal-actions flex justify-end gap-2 pt-1">
        <button type="button" onClick={onClose} disabled={busy} className="btn-cancel h-10 rounded-lg border border-[#D0D4DA] bg-white px-5 text-[14px] font-semibold">
          닫기
        </button>
        {info && versions.length > 0 && (
          <button
            type="button"
            onClick={() => void submit()}
            disabled={!canSubmit}
            className={`btn-reissue-base h-10 rounded-lg px-5 text-[14px] font-semibold ${canSubmit ? 'bg-[#2B4FCB] text-white' : 'btn-disabled cursor-not-allowed bg-[#E3E5E8] text-[#8A9099]'}`}
          >
            {busy ? '선택 중…' : '기준 버전으로 선택'}
          </button>
        )}
      </div>
    </Modal>
  );
}
