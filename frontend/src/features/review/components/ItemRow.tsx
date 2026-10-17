import type { ReactNode } from 'react';
import type { ExtractionItem, ReviewLog } from '../shared/api/types';
import { Chem } from '../shared/components/Chem';
import { Icon } from '../shared/components/Icon';
import { AiMappingBadge, JudgementBadge } from '../shared/components/badges';
import { formatDateTime } from '../shared/domain/format';
import {
  confidenceLevel,
  formatConverted,
  formatSpec,
  isLowConfidence,
  lastLog,
  processedKind,
  rawDifferent,
} from '../shared/domain/items';

const SUB = 'col-start-2 col-span-3';
const GRID = 'item-row-grid grid grid-cols-[104px_1fr_28px_72px] items-center gap-x-3 gap-y-0';

export interface ItemRowProps {
  item: ExtractionItem;
  logs: ReviewLog[];
  /** 처분된 문서는 읽기 전용입니다(수정 아이콘과 값 확인 버튼을 숨깁니다). */
  readonly: boolean;
  /** 이 항목에 붙는 이상 패턴 경고 문구 */
  flags: string[];
  /** 수정 편집 박스가 열려 있으면 그 내용 */
  editor?: ReactNode;
  /** 판정 불가·누락 항목의 후속 조치 줄 */
  followUp?: ReactNode;
  onSelect(): void;
  onEdit?(): void;
  onVerify?(): void;
  onMap?(): void;
}

function SubAction({ children, button, className = '' }: { children: ReactNode; button?: ReactNode; className?: string }) {
  return (
    <div className={`item-sub item-sub-action ${SUB} flex min-h-[26px] items-center justify-between gap-2 text-[12px] ${className}`}>
      <span className="flex min-w-0 items-center gap-1">{children}</span>
      {button}
    </div>
  );
}

function NameCell({ item }: { item: ExtractionItem }) {
  return (
    <div className="item-name flex min-w-0 flex-col leading-tight">
      <span className="flex items-center justify-between gap-1">
        <span className="item-name-label truncate text-[14px] font-semibold">{item.normalized_name}</span>
        {item.mapping_source === 'ai' && <AiMappingBadge />}
      </span>
      <span className="item-name-original truncate text-[11px] text-[#8A9099]">
        원문: {item.raw_name ? <Chem text={item.raw_name} /> : '-'}
      </span>
    </div>
  );
}

/** 신뢰도 낮음 문구. 낮음이고 아직 처리하지 않았으면 강조합니다. */
function ConfidenceText({ item, resolved }: { item: ExtractionItem; resolved: boolean }) {
  const level = confidenceLevel(item.confidence);
  if (!level) return null;
  const warn = level === '낮음' && !resolved;
  return (
    <span
      className={`item-confidence item-confidence-${level} whitespace-nowrap text-[10px] ${
        warn ? 'font-semibold text-[#9A5B00]' : 'text-[#8A9099]'
      }`}
    >
      신뢰도 {level}
    </span>
  );
}

/** 시험 항목 한 줄 (시안 2-1 등). 판정과 이탈 폭은 서버 응답을 그대로 표시합니다. */
export function ItemRow({ item, logs, readonly, flags, editor, followUp, onSelect, onEdit, onVerify, onMap }: ItemRowProps) {
  const kind = processedKind(item.item_id, logs);
  const resolved = kind !== null;
  const lowPending = item.judgement === 'check' && isLowConfidence(item) && !resolved;
  const editLog = lastLog(item.item_id, logs, 'edit');
  const confirmLog = lastLog(item.item_id, logs, 'confirm');
  const editing = editor !== undefined;
  const raw = rawDifferent(item);
  const converted = formatConverted(item);
  // 이상 패턴 경고가 판정 근거와 같은 말로 시작하면(예: 결과 칸이 규격 문구와 같음) 근거 줄을 따로 보이지 않습니다.
  const reason = item.judgement_reason;
  const reasonCovered = reason !== null && flags.some((message) => message.startsWith(reason));

  let rowClass = '';
  if (lowPending) rowClass += ' item-row-low-confidence border-l-[3px] border-[#9A5B00] pl-[17px]';
  if (editing) rowClass += ' bg-[#F3F6FE]';

  const measured = editLog ? (
    <>
      <b className="item-measured font-semibold tabular-nums">{converted}</b>{' '}
      <span className="item-measured-note text-[11px] font-normal text-[#8A9099]">(AI {editLog.before_value} → 수정됨)</span>
    </>
  ) : raw ? (
    <>
      <span className="item-raw text-[11px] text-[#8A9099]">원문 {raw} →</span>{' '}
      <b className="item-measured font-semibold tabular-nums">{converted}</b>
    </>
  ) : (
    <b className="item-measured font-semibold tabular-nums">{converted}</b>
  );

  return (
    <li className={`item-row item-row-${item.judgement} px-5 py-1${rowClass}`} onClick={onSelect}>
      <div className={GRID}>
        <NameCell item={item} />
        <div className="item-values flex min-w-0 flex-col gap-0.5 text-[13px] leading-snug">
          <span className="item-measured-line">{measured}</span>
          <span className="item-spec-line">
            <span className="item-spec tabular-nums text-[#5B616A]">규격 {formatSpec(item)}</span>
          </span>
        </div>
        <div className="item-edit-slot flex justify-center">
          {!readonly && onEdit && (
            <button
              type="button"
              aria-label="값 수정"
              onClick={(event) => {
                event.stopPropagation();
                onEdit();
              }}
              className="btn-edit flex h-7 w-7 items-center justify-center rounded-md text-[#5B616A]"
            >
              <Icon name="pencil" size={15} />
            </button>
          )}
        </div>
        <div className="item-judge flex flex-col items-center gap-0.5">
          <JudgementBadge judgement={item.judgement} fixedWidth />
          <ConfidenceText item={item} resolved={resolved} />
        </div>

        {item.judgement === 'undetermined' && reason && !reasonCovered && (
          <div className={`item-reason ${SUB} py-0.5 text-[12px] leading-snug text-[#6B4FBB]`}>{item.judgement_reason}</div>
        )}
        {item.judgement === 'check' && !lowPending && reason && !reasonCovered && (
          <div className={`item-reason ${SUB} py-0.5 text-[12px] leading-snug text-[#9A5B00]`}>{item.judgement_reason}</div>
        )}
        {followUp}

        {lowPending && !readonly && onVerify && (
          <SubAction
            button={
              <button
                type="button"
                onClick={(event) => {
                  event.stopPropagation();
                  onVerify();
                }}
                className="btn-verify h-6 shrink-0 rounded-md border border-[#9A5B00]/40 bg-[#FBF0DF] px-3 text-[12px] font-semibold text-[#9A5B00]"
              >
                값 확인
              </button>
            }
          >
            <span className="item-confidence-low flex items-center gap-1 font-semibold text-[#9A5B00]">
              <Icon name="warn" size={12} />
              원문 확인이 필요합니다.
            </span>
          </SubAction>
        )}

        {confirmLog && !editLog && (
          <SubAction
            button={
              !readonly && (
                <button
                  type="button"
                  disabled
                  className="btn-verified inline-flex h-6 shrink-0 cursor-default items-center gap-1 rounded-md border border-[#177A46]/30 bg-[#E7F5EC] px-3 text-[12px] font-semibold text-[#177A46]"
                >
                  <Icon name="check" size={13} />
                  확인됨
                </button>
              )
            }
          >
            <span className="item-edit-log text-[11px] text-[#8A9099]">
              확인: {confirmLog.reviewer_name} · {formatDateTime(confirmLog.reviewed_at)}
            </span>
          </SubAction>
        )}
        {editLog && (
          <div className={`item-edit-log ${SUB} text-[11px] text-[#8A9099]`}>
            수정: {editLog.reviewer_name} · {formatDateTime(editLog.reviewed_at)}
            {editLog.reason ? ` · 사유: ${editLog.reason}` : ''}
          </div>
        )}

        {item.mapping_source === 'ai' && (
          <SubAction
            button={
              !readonly &&
              onMap && (
                <button
                  type="button"
                  onClick={(event) => {
                    event.stopPropagation();
                    onMap();
                  }}
                  className="btn-map inline-flex h-6 shrink-0 items-center gap-1 rounded-md border border-[#6B4FBB]/40 bg-[#F0ECFA] px-3 text-[12px] font-semibold text-[#6B4FBB]"
                >
                  <Icon name="link" size={13} />
                  매핑 수정
                </button>
              )
            }
          >
            <span className="flex items-center gap-1 font-semibold text-[#6B4FBB]">{`AI가 ‘${item.normalized_name}’로 추정했습니다.`}</span>
          </SubAction>
        )}

        {flags.map((message) => (
          <div
            key={message}
            className={`item-flag ${SUB} flex items-start gap-1 rounded-md border border-[#F0C987] bg-[#FFF7E6] px-2 py-1 text-[11px] font-semibold leading-snug text-[#8A5A00]`}
          >
            <span className="mt-px shrink-0">
              <Icon name="flag" size={12} />
            </span>
            <span>{message}</span>
          </div>
        ))}

        {editor}
      </div>
    </li>
  );
}

/**
 * 누락 항목 한 줄. 원본에 없으므로 하이라이트하지 않고 목록 하단에 묶어 보여 줍니다.
 * 담당자가 자체 시험 값을 입력하면 서버가 다시 판정하므로, 처분 전에는 수정 아이콘을 둡니다.
 */
export function MissingRow({
  item,
  readonly,
  followUp,
  editor,
  onSelect,
  onEdit,
}: {
  item: ExtractionItem;
  readonly: boolean;
  followUp?: ReactNode;
  editor?: ReactNode;
  onSelect(): void;
  onEdit?(): void;
}) {
  return (
    <li className={`item-row item-row-missing px-5 py-1${editor !== undefined ? ' bg-[#F3F6FE]' : ''}`} onClick={onSelect}>
      <div className={GRID}>
        <NameCell item={item} />
        <div className="item-values flex min-w-0 flex-col gap-0.5 text-[13px] leading-snug">
          <span className="item-measured-line text-[#5B616A]">CoA에 기재되어 있지 않습니다.</span>
          <span className="item-spec-line item-spec tabular-nums text-[#5B616A]">규격 {formatSpec(item)}</span>
        </div>
        <div className="item-edit-slot flex justify-center">
          {!readonly && onEdit && (
            <button
              type="button"
              aria-label="값 입력"
              onClick={(event) => {
                event.stopPropagation();
                onEdit();
              }}
              className="btn-edit flex h-7 w-7 items-center justify-center rounded-md text-[#5B616A]"
            >
              <Icon name="pencil" size={15} />
            </button>
          )}
        </div>
        <div className="item-judge flex flex-col items-center gap-0.5">
          <JudgementBadge judgement="missing" fixedWidth />
        </div>
        {followUp}
        {editor}
      </div>
    </li>
  );
}
