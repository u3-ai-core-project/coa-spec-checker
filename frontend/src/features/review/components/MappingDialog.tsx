import { useMemo, useState } from 'react';
import { api } from '../shared/api';
import { errorMessage, isApiError } from '../shared/api/errors';
import type { DocumentDetail, ExtractionItem, SpecItem } from '../shared/api/types';
import { Chem } from '../shared/components/Chem';
import { Icon } from '../shared/components/Icon';
import { AiMappingBadge } from '../shared/components/badges';
import { mappingHint } from '../lib/mapping';
import { buildMappingOptions, EXTRA_MAPPING_OPTIONS } from '../lib/mappingOptions';
import { Modal } from './Modal';

interface MappingDialogProps {
  doc: DocumentDetail;
  item: ExtractionItem;
  /** 문서의 원자재 규격. 선택지는 이 항목명으로만 만듭니다. */
  specs: SpecItem[];
  /** 원본 문서에서 이 항목이 있는 쪽수 */
  page: number | null;
  onClose(): void;
  onDone(): void;
  onStale(): void;
}

/**
 * 항목 매핑 수정 다이얼로그 (시안 2-9). AI가 추정한 표준 항목을 규격 항목 중에서 다시 고릅니다.
 * 서버는 고친 항목명을 매핑 사전에 누적하고(manual), 이후 업로드 건부터 적용합니다.
 * (협력사별이 아니라 material_code + raw_name 기준이므로 "Chengxin의 동일 표기에만" 같은 문구는 쓰지 않습니다.)
 */
export function MappingDialog({ doc, item, specs, page, onClose, onDone, onStale }: MappingDialogProps) {
  const [query, setQuery] = useState('');
  const [selected, setSelected] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // 항목명만 수정할 때 수정 사유는 선택입니다(백엔드 확정 답변).
  const [reason, setReason] = useState('');

  const options = useMemo(() => buildMappingOptions(specs, query), [specs, query]);
  const hint = mappingHint(item.raw_name, [...specs, ...EXTRA_MAPPING_OPTIONS.map((option) => ({ item_name: option.name }))]);
  const canApply = selected !== null && selected !== item.normalized_name && !busy;

  async function apply() {
    if (!selected) return;
    setBusy(true);
    setError(null);
    try {
      const note = reason.trim();
      await api.patchItem(doc.document_id, item.item_id, note ? { normalized_name: selected, reason: note } : { normalized_name: selected });
      onDone();
    } catch (failure) {
      setError(errorMessage(failure));
      if (isApiError(failure, 'ALREADY_APPROVED')) onStale();
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal width={560} labelledBy="mapping-title" onClose={onClose}>
      <div className="flex items-center gap-3">
        <div className="modal-icon flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-[#F0ECFA] text-[#6B4FBB]">
          <Icon name="link" size={20} />
        </div>
        <div className="flex flex-col">
          <h4 id="mapping-title" className="modal-title text-[18px] font-bold">
            항목 매핑 수정
          </h4>
          <span className="text-[12px] tabular-nums text-[#8A9099]">
            {doc.file_name}
            {page ? ` · ${page}페이지` : ''}
          </span>
        </div>
      </div>

      <div className="map-current grid grid-cols-2 gap-3 text-[13px]">
        <div className="flex flex-col gap-1 rounded-lg border border-[#E3E5E8] bg-[#F9FAFB] px-3 py-2.5">
          <span className="text-[11px] text-[#8A9099]">원문 표기</span>
          <b className="font-semibold">{item.raw_name ? <Chem text={item.raw_name} /> : '-'}</b>
        </div>
        <div className="flex flex-col gap-1 rounded-lg border border-[#E3E5E8] bg-[#F9FAFB] px-3 py-2.5">
          <span className="flex items-center gap-1.5 text-[11px] text-[#8A9099]">
            현재 매핑 {item.mapping_source === 'ai' && <AiMappingBadge />}
          </span>
          <b className="font-semibold">{item.normalized_name}</b>
        </div>
      </div>

      <div className="flex flex-col gap-1.5">
        <label className="text-[13px] font-semibold" htmlFor="mapping-search">
          표준 항목 다시 선택
        </label>
        <div className="map-search flex h-9 items-center gap-2 rounded-lg border-2 border-[#2B4FCB] px-3 text-[13px]">
          <span className="text-[#8A9099]">
            <Icon name="search" size={14} />
          </span>
          <input
            id="mapping-search"
            className="min-w-0 flex-1 bg-transparent outline-none"
            placeholder="항목명으로 찾습니다."
            value={query}
            autoFocus
            onChange={(event) => setQuery(event.target.value)}
          />
        </div>
        <ul className="map-options flex max-h-[200px] flex-col gap-1.5 overflow-y-auto" role="radiogroup" aria-label="표준 항목">
          {options.map((option) => {
            const on = selected === option.name;
            const current = option.name === item.normalized_name;
            return (
              <li key={option.name}>
                <button
                  type="button"
                  role="radio"
                  aria-checked={on}
                  onClick={() => setSelected(option.name)}
                  className={`map-option flex w-full items-center gap-2.5 rounded-lg border px-3 py-2 text-left text-[13px] ${
                    on ? 'border-[#2B4FCB] bg-[#F3F6FE]' : 'border-[#E3E5E8] bg-white'
                  }`}
                >
                  {on ? (
                    <span className="flex h-4 w-4 items-center justify-center rounded-full border-2 border-[#2B4FCB]">
                      <span className="h-2 w-2 rounded-full bg-[#2B4FCB]" />
                    </span>
                  ) : (
                    <span className="h-4 w-4 rounded-full border-2 border-[#B6BBC4]" />
                  )}
                  <span className="font-semibold">{option.name}</span>
                  <span className="text-[#8A9099]">{option.note}</span>
                  {current && (
                    <span className="rounded bg-[#F0ECFA] px-1 text-[10px] font-semibold text-[#6B4FBB]">현재 매핑</span>
                  )}
                </button>
              </li>
            );
          })}
          {options.length === 0 && (
            <li className="rounded-lg border border-dashed border-[#D0D4DA] px-3 py-3 text-[12px] text-[#8A9099]">
              사내 규격에 있는 항목만 선택할 수 있습니다. 찾는 항목이 없습니다.
            </li>
          )}
        </ul>
      </div>

      {hint && (
        <div className="map-hint flex items-start gap-2 rounded-lg bg-[#F0ECFA] px-3 py-2 text-[12px] text-[#4A3585]">
          <span className="mt-px shrink-0">
            <Icon name="info" size={14} />
          </span>
          <span>{hint}</span>
        </div>
      )}

      <div className="map-reason flex flex-col gap-1.5">
        <label className="text-[13px] font-semibold" htmlFor="mapping-reason">
          수정 사유 <span className="text-[12px] font-normal text-[#8A9099]">선택 입력입니다.</span>
        </label>
        <input
          id="mapping-reason"
          className="map-reason-input h-9 w-full rounded-lg border border-[#D0D4DA] bg-white px-3 text-[13px]"
          placeholder="수정 사유를 입력합니다."
          value={reason}
          onChange={(event) => setReason(event.target.value)}
        />
      </div>

      <p className="map-accumulate text-[12px] text-[#5B616A]">다음 문서부터 자동 매핑됩니다. 잘못 매핑되면 매핑 사전에서 삭제할 수 있습니다.</p>

      {error && <p className="text-[12px] text-[#C0342E]">{error}</p>}

      <div className="modal-actions flex justify-end gap-2 pt-1">
        <button
          type="button"
          onClick={onClose}
          className="btn-cancel h-10 rounded-lg border border-[#D0D4DA] bg-white px-5 text-[14px] font-semibold"
        >
          취소
        </button>
        <button
          type="button"
          disabled={!canApply}
          onClick={() => void apply()}
          className={`btn-map-apply h-10 rounded-lg px-5 text-[14px] font-semibold ${
            canApply ? 'bg-[#2B4FCB] text-white' : 'cursor-not-allowed bg-[#E3E5E8] text-[#8A9099]'
          }`}
        >
          매핑 적용
        </button>
      </div>
    </Modal>
  );
}
