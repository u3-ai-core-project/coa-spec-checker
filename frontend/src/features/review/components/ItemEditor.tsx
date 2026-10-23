import { useEffect, useRef, useState } from 'react';
import type { ExtractionItem, ValueSource } from '../shared/api/types';
import { JudgementBadge } from '../shared/components/badges';
import { Icon } from '../shared/components/Icon';
import { RESOLUTION_ACTION_LABEL, VALUE_SOURCE_LABEL, VALUE_SOURCE_ORDER } from '../shared/domain/exceptions';
import { formatNumber } from '../shared/domain/format';
import { formatConverted, formatSpec, previewReply } from '../shared/domain/items';
import { JUDGEMENT_META } from '../shared/domain/judgement';
import { parseValue } from '../lib/parseValue';

const SUB = 'col-start-2 col-span-3';

export type EditQualifier = 'exact' | 'less_than' | 'not_detected';

export interface ItemEditSubmit {
  /** 값. not_detected이면 검출한계, less_than이면 "< 값"의 상한값입니다. */
  value: number;
  /** [v1.4] 입력값 출처 */
  valueSource: ValueSource;
  /** [v1.4] 값 종류. exact(정량값), less_than("< 값"으로 회신), not_detected(검출 안 됨, 이때 value가 검출한계) */
  qualifier: EditQualifier;
  /** 수정 사유(필수). PATCH 요청의 reason으로 보내고 review_logs에 남습니다(백엔드 확정 답변). */
  reason: string;
}

interface ItemEditorProps {
  item: ExtractionItem;
  busy: boolean;
  error: string | null;
  onCancel(): void;
  onSubmit(submit: ItemEditSubmit): void;
}

/** 해결 조건 종류에 맞춰 값 출처와 값 형식의 시작값을 정합니다(공급사 회신값, 자체 시험값, 검출한계 등). */
function defaultsFor(item: ExtractionItem): { source: ValueSource; qualifier: EditQualifier } {
  switch (item.resolution?.type) {
    case 'detection_limit':
      return { source: 'supplier_reply', qualifier: 'not_detected' };
    case 'actual_value':
    case 'single_value':
      return { source: 'supplier_reply', qualifier: 'exact' };
    case 'internal_test':
      return { source: 'internal_test', qualifier: 'exact' };
    default:
      return { source: 'correction', qualifier: 'exact' };
  }
}

const QUALIFIER_OPTIONS: Array<{ value: EditQualifier; label: string }> = [
  { value: 'exact', label: '정량값' },
  { value: 'less_than', label: '상한값 (<)' },
  { value: 'not_detected', label: '검출 안 됨' },
];

/** 입력칸 이름: 검출 안 됨이면 검출한계, "<"이면 상한값 */
function valueLabel(qualifier: EditQualifier): string {
  return qualifier === 'not_detected' ? '검출한계' : qualifier === 'less_than' ? '상한값' : '값';
}

/** 미리보기 문장에 쓰는 입력값 표기. 예: 5 ppm, < 5 ppm, 검출한계 2 ppm */
function valueText(qualifier: EditQualifier, value: number, unit: string | null): string {
  const text = `${formatNumber(value)}${unit ? ` ${unit}` : ''}`;
  return qualifier === 'not_detected' ? `검출한계 ${text}` : qualifier === 'less_than' ? `< ${text}` : text;
}

/**
 * 항목 안에서 바로 여는 값 수정, 회신값 입력 박스 (시안 2-3, 2-12). "수정 후 판정"과 재판정 미리보기는 참고용이고
 * 실제 판정은 서버가 PATCH 응답으로 돌려줍니다. 값을 받아야 하는 예외(resolution.type이 confirm이 아님)에서는
 * 해결 조건을 안내하고, 값 형식과 값 출처의 시작값을 해결 조건에 맞춰 채웁니다.
 */
export function ItemEditor({ item, busy, error, onCancel, onSubmit }: ItemEditorProps) {
  const defaults = defaultsFor(item);
  const [qualifier, setQualifier] = useState<EditQualifier>(defaults.qualifier);
  const notDetected = qualifier === 'not_detected';
  const [source, setSource] = useState<ValueSource>(defaults.source);
  const initial = typeof item.converted_value === 'number' && !notDetected ? String(item.converted_value) : '';
  const [text, setText] = useState(initial);
  const [reason, setReason] = useState('');
  const value = parseValue(text);
  const reasonOk = reason.trim().length > 0;
  const canSubmit = value !== null && reasonOk && !busy;

  // 박스가 열리면 목록을 스크롤해 박스 전체가 보이게 합니다(회신값 박스는 항목 아래로 길게 열립니다).
  const boxRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    boxRef.current?.scrollIntoView({ block: 'nearest' });
  }, []);

  const resolution = item.resolution;
  const replying = resolution != null && resolution.type !== 'confirm';
  const preview = value === null ? null : previewReply(qualifier, value, item.spec_lsl, item.spec_usl);
  const previewMeta = preview ? JUDGEMENT_META[preview] : null;
  const unit = item.unit;
  const limit = item.spec_usl ?? item.spec_lsl;

  let previewText = '';
  if (value !== null && preview) {
    const entered = valueText(qualifier, value, unit);
    if (preview === 'pass') {
      previewText = `${entered}${item.spec_usl !== null ? ` ≤ 사내 상한 ${formatNumber(item.spec_usl)}${unit ? ` ${unit}` : ''}` : ''} → 적합${item.reason_code ? ', 예외 해제' : ''}`;
    } else if (preview === 'fail') {
      previewText = `${entered}, 사내 규격 ${formatSpec(item)}을 벗어납니다 → 부적합`;
    } else {
      previewText =
        item.spec_lsl !== null
          ? `${entered}만으로는 사내 하한 ${formatNumber(item.spec_lsl)}${unit ? ` ${unit}` : ''} 충족 여부를 알 수 없습니다 → 판정 불가`
          : `${entered}: 사내 상한 ${limit !== null ? formatNumber(limit) : '-'}${unit ? ` ${unit}` : ''}보다 큽니다 → 판정 불가`;
    }
  }

  return (
    <div
      ref={boxRef}
      className={`item-edit ${SUB} flex flex-col gap-1.5 rounded-lg border border-[#C9D5F7] bg-white p-3`}
      onClick={(event) => event.stopPropagation()}
    >
      <div className="flex items-center justify-between text-[12px] text-[#5B616A]">
        <span>
          AI 추출값 <b className="font-semibold tabular-nums text-[#1F2328]">{formatConverted(item)}</b>
          {item.value_qualifier === 'not_detected' && item.detection_limit === null && <span className="text-[#8A9099]"> (검출한계 없음)</span>}
        </span>
        <span className="flex items-center gap-1.5">
          수정 후 판정
          {preview ? <JudgementBadge judgement={preview} /> : <span className="text-[#8A9099]">-</span>}
        </span>
      </div>
      {replying && resolution.condition && (
        <div className="item-reply-condition flex items-start gap-1.5 rounded-md bg-[#F4F5F7] px-2.5 py-1.5 text-[12px] leading-snug text-[#5B616A]">
          <span className="mt-px shrink-0 text-[#2B4FCB]">
            <Icon name="info" size={13} />
          </span>
          <span>
            해결 조건 <b className="font-semibold tabular-nums text-[#1F2328]">{resolution.condition}</b>{' '}
            <span className="text-[11px] text-[#8A9099]">({RESOLUTION_ACTION_LABEL[resolution.type]})</span>
          </span>
        </div>
      )}
      <div className="item-edit-kind flex items-center gap-2 text-[12px] text-[#5B616A]">
        <span className="w-12 shrink-0">값 형식</span>
        <div className="seg inline-flex gap-0.5 rounded-md border border-[#D0D4DA] p-0.5" role="group" aria-label="값 형식">
          {QUALIFIER_OPTIONS.map((option) => (
            <button
              key={option.value}
              type="button"
              aria-pressed={qualifier === option.value}
              onClick={() => setQualifier(option.value)}
              className={`seg-option h-7 rounded px-2.5 text-[12px] ${
                qualifier === option.value ? 'seg-option-on bg-[#EAEFFC] font-semibold text-[#2B4FCB]' : 'text-[#5B616A]'
              }`}
            >
              {option.label}
            </button>
          ))}
        </div>
      </div>
      <div className="item-edit-controls flex items-center gap-2">
        <span className="w-12 shrink-0 text-[12px] text-[#5B616A]">{valueLabel(qualifier)}</span>
        <div className="relative">
          <input
            className={`item-edit-input h-9 w-28 rounded-md border-2 border-[#2B4FCB] bg-white pr-10 ${qualifier === 'less_than' ? 'pl-7' : 'pl-3'} text-[14px] tabular-nums`}
            value={text}
            inputMode="decimal"
            autoFocus
            aria-label={notDetected ? '검출한계' : qualifier === 'less_than' ? '상한값 (< 값)' : '수정할 값'}
            onChange={(event) => setText(event.target.value)}
          />
          {qualifier === 'less_than' && <span className="absolute left-3 top-2 text-[14px] text-[#5B616A]">&lt;</span>}
          {unit && <span className="absolute right-3 top-2 text-[12px] text-[#8A9099]">{unit}</span>}
        </div>
        <span className="item-edit-hint text-[12px] tabular-nums text-[#5B616A]">규격 {formatSpec(item)}</span>
      </div>
      <div className="item-edit-source flex items-center gap-2 text-[12px] text-[#5B616A]">
        <label htmlFor={`source-${item.item_id}`} className="w-12 shrink-0">
          값 출처
        </label>
        <select
          id={`source-${item.item_id}`}
          className="item-edit-source-select h-8 rounded-md border border-[#D0D4DA] bg-white px-2 text-[12px] text-[#1F2328]"
          value={source}
          onChange={(event) => setSource(event.target.value as ValueSource)}
        >
          {VALUE_SOURCE_ORDER.map((option) => (
            <option key={option} value={option}>
              {VALUE_SOURCE_LABEL[option]}
            </option>
          ))}
        </select>
      </div>
      {unit && (
        <p className="item-edit-unit pl-14 text-[11px] leading-snug text-[#8A9099]">
          {`사내 규격 단위(${unit})로 입력합니다. 공급사가 다른 단위로 회신하면 환산해 주십시오.${unit === 'ppm' ? ' (예: 0.0002 % → 2 ppm)' : ''}`}
        </p>
      )}
      {previewMeta && (
        <div
          className="item-reply-preview flex flex-col gap-0.5 rounded-md px-2.5 py-1.5 text-[12px] leading-snug"
          style={{ backgroundColor: previewMeta.bg, color: previewMeta.color }}
        >
          <span className="flex items-start gap-1 font-semibold">
            <span className="mt-px shrink-0">
              <Icon name={preview === 'pass' ? 'check' : 'warn'} size={13} />
            </span>
            {`재판정 결과 · ${previewText}`}
          </span>
          <span className="text-[11px] font-normal text-[#5B616A]">참고용입니다. 확정하면 서버가 다시 판정하며, 조건을 만족하지 않으면 예외로 남습니다.</span>
        </div>
      )}
      <div className="item-edit-reason flex flex-col gap-1">
        <label className="text-[12px] font-semibold" htmlFor={`reason-${item.item_id}`}>
          수정 사유 <span className="text-[#C0342E]">*</span>{' '}
          <span className="font-normal text-[#8A9099]">필수 입력입니다.</span>
        </label>
        <textarea
          id={`reason-${item.item_id}`}
          className="item-edit-reason-input h-12 w-full resize-none rounded-md border border-[#D0D4DA] px-3 py-1.5 text-[13px]"
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
          onClick={() => value !== null && onSubmit({ value, reason: reason.trim(), valueSource: source, qualifier })}
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
