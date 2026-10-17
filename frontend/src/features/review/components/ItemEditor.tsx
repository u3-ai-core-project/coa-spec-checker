import { useState } from 'react';
import type { ExtractionItem } from '../shared/api/types';
import { JudgementBadge } from '../shared/components/badges';
import { formatConverted, formatSpec, previewJudgement } from '../shared/domain/items';
import { parseValue } from '../lib/parseValue';

const SUB = 'col-start-2 col-span-3';

export interface ItemEditSubmit {
  value: number;
  /**
   * 수정 사유. API에 필드가 없어 서버로 보내지 않고 화면 쪽(목업)에만 저장합니다.
   * TODO(백엔드 협의): 사유 필드가 생기면 PATCH 요청에 포함합니다.
   */
  reason: string;
}

interface ItemEditorProps {
  item: ExtractionItem;
  busy: boolean;
  error: string | null;
  onCancel(): void;
  onSubmit(submit: ItemEditSubmit): void;
}

/** 항목 안에서 바로 여는 값 수정 박스 (시안 2-3). "수정 후 판정"은 참고용이고 실제 판정은 서버가 다시 계산합니다. */
export function ItemEditor({ item, busy, error, onCancel, onSubmit }: ItemEditorProps) {
  const initial = typeof item.converted_value === 'number' ? String(item.converted_value) : '';
  const [text, setText] = useState(initial);
  const [reason, setReason] = useState('');
  const value = parseValue(text);
  const reasonOk = reason.trim().length > 0;
  const canSubmit = value !== null && reasonOk && !busy;

  return (
    <div
      className={`item-edit ${SUB} flex flex-col gap-2 rounded-lg border border-[#C9D5F7] bg-white p-3`}
      onClick={(event) => event.stopPropagation()}
    >
      <div className="flex items-center justify-between text-[12px] text-[#5B616A]">
        <span>
          AI 추출값 <b className="font-semibold tabular-nums text-[#1F2328]">{formatConverted(item)}</b>
        </span>
        <span className="flex items-center gap-1.5">
          수정 후 판정
          {value === null ? (
            <span className="text-[#8A9099]">-</span>
          ) : (
            <JudgementBadge judgement={previewJudgement(value, item.spec_lsl, item.spec_usl)} />
          )}
        </span>
      </div>
      <div className="item-edit-controls flex items-center gap-2">
        <div className="relative">
          <input
            className="item-edit-input h-9 w-28 rounded-md border-2 border-[#2B4FCB] bg-white pl-3 pr-10 text-[14px] tabular-nums"
            value={text}
            inputMode="decimal"
            autoFocus
            aria-label="수정할 값"
            onChange={(event) => setText(event.target.value)}
          />
          {item.unit && <span className="absolute right-3 top-2 text-[12px] text-[#8A9099]">{item.unit}</span>}
        </div>
        <span className="item-edit-hint text-[12px] tabular-nums text-[#5B616A]">규격 {formatSpec(item)}</span>
      </div>
      <div className="item-edit-reason flex flex-col gap-1.5">
        <label className="text-[12px] font-semibold" htmlFor={`reason-${item.item_id}`}>
          수정 사유 <span className="text-[#C0342E]">*</span>{' '}
          <span className="font-normal text-[#8A9099]">필수 입력입니다.</span>
        </label>
        <textarea
          id={`reason-${item.item_id}`}
          className="item-edit-reason-input h-14 w-full resize-none rounded-md border border-[#D0D4DA] px-3 py-2 text-[13px]"
          value={reason}
          onChange={(event) => setReason(event.target.value)}
        />
      </div>
      {error && <p className="text-[12px] text-[#C0342E]">{error}</p>}
      <div className="item-edit-actions flex justify-end gap-2">
        <button
          type="button"
          onClick={onCancel}
          className="btn-cancel-edit h-9 rounded-md border border-[#D0D4DA] bg-white px-4 text-[13px] font-semibold"
        >
          취소
        </button>
        <button
          type="button"
          disabled={!canSubmit}
          onClick={() => value !== null && onSubmit({ value, reason: reason.trim() })}
          className={`btn-confirm h-9 rounded-md px-4 text-[13px] font-semibold ${
            canSubmit ? 'bg-[#2B4FCB] text-white' : 'cursor-not-allowed bg-[#E3E5E8] text-[#8A9099]'
          }`}
        >
          확정
        </button>
      </div>
    </div>
  );
}
