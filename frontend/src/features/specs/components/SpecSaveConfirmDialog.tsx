import { Modal } from '../../review/components/Modal';
import type { SpecItem, SpecPreview } from '../../review/shared/api/types';
import { Icon } from '../../review/shared/components/Icon';
import { RECOMMENDATION_META } from '../../review/shared/domain/recommendation';

/** 저장 전 미리보기 결과 1건: 바꾸려는 규격 항목과 서버(POST /specs/{id}/preview)가 계산한 영향 */
export interface SpecPreviewEntry {
  spec: SpecItem;
  preview: SpecPreview;
}

interface SpecSaveConfirmDialogProps {
  entries: SpecPreviewEntry[];
  /** "저장 후 재판정" 체크박스 상태. 문구만 달라지고 숫자는 서버가 계산한 그대로입니다. */
  rejudge: boolean;
  busy: boolean;
  onCancel(): void;
  onConfirm(): void;
}

/** 서버가 알려 준 바뀌는 필드(lsl, usl, unit)의 화면 이름. 모르는 값은 그대로 보여 줍니다. */
const FIELD_LABEL: Record<string, string> = { lsl: '하한(LSL)', usl: '상한(USL)', unit: '단위' };

const recommendationText = (value: keyof typeof RECOMMENDATION_META | null) => (value ? RECOMMENDATION_META[value].label : '-');

/**
 * 규격 저장 전 확인 다이얼로그. 저장 버튼을 누르면 먼저 서버가 저장하지 않고 영향 범위를 계산(preview)하고,
 * 이 다이얼로그가 "영향 문서 N건, 권고 변경 M건"을 서버 값 그대로 보여 줍니다. 영향이 0건이어도 같은 흐름입니다.
 * 항목마다 따로 계산한 값이라 항목 사이의 수치는 합치지 않습니다. 확인을 누르면 기존 저장(PATCH)을 합니다.
 */
export function SpecSaveConfirmDialog({ entries, rejudge, busy, onCancel, onConfirm }: SpecSaveConfirmDialogProps) {
  return (
    <Modal width={560} gap="gap-3.5" labelledBy="spec-save-title" onClose={busy ? () => undefined : onCancel}>
      <div className="modal-icon flex h-12 w-12 items-center justify-center rounded-full bg-[#EAEFFC] text-[#2B4FCB]">
        <Icon name="info" size={24} />
      </div>
      <h4 id="spec-save-title" className="modal-title text-[18px] font-bold">
        저장 전 영향 확인
      </h4>
      <p className="modal-body text-[13px] leading-relaxed text-[#5B616A]">
        서버가 저장하지 않고 계산한 결과입니다. 영향 범위는 이 규격 세트로 판정한 처분 전 문서(추출됨, 검수 중, 보류)입니다.
      </p>
      <ul className="spec-preview-list flex max-h-[300px] flex-col gap-2 overflow-y-auto">
        {entries.map(({ spec, preview }) => (
          <li key={spec.id} className="spec-preview-entry flex flex-col gap-1.5 rounded-lg border border-[#E3E5E8] px-3 py-2.5">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="spec-preview-name text-[14px] font-bold">{spec.item_name}</span>
              <span className="spec-preview-fields text-[12px] text-[#5B616A]">
                {preview.changed_fields.length > 0
                  ? `바뀌는 값: ${preview.changed_fields.map((field) => FIELD_LABEL[field] ?? field).join(', ')}`
                  : '바뀌는 값 없음'}
              </span>
            </div>
            <div className="spec-preview-counts flex flex-wrap items-center gap-x-3 gap-y-1 text-[13px]">
              <span>
                영향 문서 <b className="tabular-nums">{preview.affected_documents}건</b>
              </span>
              <span>
                권고 변경 <b className="tabular-nums">{preview.recommendation_changed_documents}건</b>
              </span>
              <span className="text-[12px] text-[#8A9099]">
                처분 전 대상 문서 <span className="tabular-nums">{preview.target_documents}건</span>
              </span>
            </div>
            {preview.documents.length > 0 && (
              <ul className="spec-preview-docs flex max-h-28 flex-col divide-y divide-[#E3E5E8] overflow-y-auto rounded-md bg-[#F9FAFB]">
                {preview.documents.map((doc) => (
                  <li key={doc.document_id} className="spec-preview-doc flex flex-col gap-0.5 px-2.5 py-1.5 text-[12px]">
                    <span className="flex flex-wrap items-center gap-x-2">
                      <span className="font-semibold tabular-nums">{doc.document_id}</span>
                      <span className="tabular-nums text-[#5B616A]">
                        로트 권고 {recommendationText(doc.lot_recommendation_before)} → {recommendationText(doc.lot_recommendation_after)}
                      </span>
                    </span>
                    <span className="text-[#5B616A]">
                      {doc.changed_items.length > 0 ? `판정이 바뀐 항목: ${doc.changed_items.join(', ')}` : '판정이 바뀐 항목 없음'}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </li>
        ))}
      </ul>
      <p className="spec-preview-apply text-[12px] font-semibold text-[#2B4FCB]">
        {rejudge
          ? '저장하면 이 규격 세트로 판정한 처분 전 문서를 서버가 다시 판정합니다.'
          : '"저장 후 재판정"이 꺼져 있어 이미 업로드된 문서는 그대로이고, 이후 업로드되는 문서부터 적용됩니다.'}
      </p>
      <div className="modal-actions flex justify-end gap-2 pt-1">
        <button type="button" onClick={onCancel} disabled={busy} className="btn-cancel h-10 rounded-lg border border-[#D0D4DA] bg-white px-5 text-[14px] font-semibold">
          취소
        </button>
        <button
          type="button"
          onClick={onConfirm}
          disabled={busy}
          className={`btn-confirm-save h-10 rounded-lg px-5 text-[14px] font-semibold ${busy ? 'cursor-not-allowed bg-[#E3E5E8] text-[#8A9099]' : 'bg-[#2B4FCB] text-white'}`}
        >
          {busy ? '저장 중…' : '저장'}
        </button>
      </div>
    </Modal>
  );
}
