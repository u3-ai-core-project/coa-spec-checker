import { useState } from 'react';
import type { ExtractionItem, FollowUpLine, FollowUpsResponse } from '../shared/api/types';
import { JudgementBadge } from '../shared/components/badges';
import { Icon } from '../shared/components/Icon';
import { DOCUMENT_ISSUE_LABEL, REASON_CODE_LABEL, RESOLUTION_ACTION_LABEL } from '../shared/domain/exceptions';
import { formatConverted, formatSpec } from '../shared/domain/items';
import { DraftBox } from './DraftBox';

/** 문서 단위 문제 줄의 target 값(GET /documents/{id}/follow-ups) */
const DOCUMENT_TARGET = '문서';

const LABEL = 'text-[11px] font-semibold text-[#8A9099]';

interface ExceptionPanelProps {
  /** 항목의 예외를 볼 때의 항목. 문서 단위 문제를 볼 때는 null입니다. */
  item: ExtractionItem | null;
  /** 문서 단위 문제를 볼 때의 코드(item이 null일 때) */
  issueCode?: string;
  /** follow-ups 응답. 불러오지 못했으면 null입니다. */
  followUps: FollowUpsResponse | null;
  /** 회신값 입력 버튼(값을 받을 수 없는 예외면 없음) */
  onReply?: () => void;
  /** 회신값을 입력할 항목이 이 항목과 다를 때(개별값 받기) 그 항목 이름 */
  replyTarget?: string;
  onClose(): void;
  /** follow-ups를 다시 불러옵니다. */
  onRetry?(): void;
}

/** 항목 하나 또는 문서 단위 문제 하나에 해당하는 follow-ups의 줄을 target과 code로 찾습니다. */
function findLine(followUps: FollowUpsResponse | null, item: ExtractionItem | null, issueCode?: string): FollowUpLine | null {
  if (!followUps) return null;
  const lines = [...followUps.supplier_lines, ...followUps.internal_lines];
  if (item) return lines.find((line) => line.target === item.normalized_name && line.code === item.reason_code) ?? null;
  return lines.find((line) => line.target === DOCUMENT_TARGET && line.code === issueCode) ?? null;
}

/**
 * 시안 2-11 예외 상세 패널. 예외 항목(또는 문서 단위 문제)을 누르면 원본 문서 아래에 열리고,
 * [왜 문제인가 / 해결 조건 / 생성된 문의 초안(복사 버튼)]을 보여 줍니다.
 * 데이터는 GET /documents/{id}/follow-ups의 supplier_lines, internal_lines(label, why, condition, raw_value)와 draft, combined_draft입니다.
 * 판정과 문구는 서버 응답을 그대로 보여 줍니다. follow-ups를 불러오지 못했으면 항목 자체의 사유와 해결 조건만 보여 줍니다.
 */
export function ExceptionPanel({ item, issueCode, followUps, onReply, replyTarget, onClose, onRetry }: ExceptionPanelProps) {
  const [showCombined, setShowCombined] = useState(false);
  const line = findLine(followUps, item, issueCode);

  const target = item?.normalized_name ?? DOCUMENT_TARGET;
  const code = item?.reason_code ?? issueCode ?? null;
  const label = line?.label ?? (item?.reason_code ? REASON_CODE_LABEL[item.reason_code] : issueCode ? (DOCUMENT_ISSUE_LABEL[issueCode as keyof typeof DOCUMENT_ISSUE_LABEL] ?? issueCode) : '');
  const why = line?.why ?? item?.judgement_reason ?? '';
  const condition = line?.condition ?? item?.resolution?.condition ?? '';
  const rawValue = line?.raw_value ?? item?.raw_value ?? null;
  const toSupplier = line?.to_supplier ?? false;
  const resolutionType = item?.resolution?.type ?? null;

  const supplier = followUps?.supplier ?? null;
  const combined = followUps?.combined_draft ?? null;
  const openCount = followUps?.open_documents.length ?? 0;
  const draft = showCombined && combined ? combined : followUps?.draft ?? null;

  return (
    <div className="exception-panel shrink-0 overflow-hidden rounded-xl border border-[#E3E5E8] bg-white">
      <div className="exception-panel-header flex items-center justify-between border-b border-[#E3E5E8] px-5 py-2">
        <div className="flex items-center gap-2">
          <h3 className="text-[14px] font-bold">예외 상세</h3>
          <span className="text-[14px] font-semibold">{target}</span>
          {item && <JudgementBadge judgement={item.judgement} />}
          {line && (
            <span
              className={`route-chip inline-flex h-5 items-center rounded-full px-2 text-[11px] font-semibold ${
                toSupplier ? 'route-chip-supplier bg-[#EAEFFC] text-[#2B4FCB]' : 'route-chip-internal bg-[#EEF0F3] text-[#5B616A]'
              }`}
            >
              {toSupplier ? '공급사에 요청' : '내부에서 확인'}
            </span>
          )}
        </div>
        <button
          type="button"
          aria-label="예외 상세 닫기"
          onClick={onClose}
          className="btn-close-panel flex h-7 w-7 items-center justify-center rounded-md text-[#5B616A]"
        >
          <Icon name="x" size={15} />
        </button>
      </div>

      <div className="exception-panel-body grid grid-cols-[210px_1fr] gap-x-5 px-5 py-2.5">
        <div className="exception-info flex flex-col gap-2">
          <div className="flex flex-col gap-0.5">
            <span className={LABEL}>사유</span>
            <span className="exception-label text-[13px] font-semibold leading-snug">{label || '-'}</span>
            {code && <span className="text-[10px] text-[#8A9099]">{code}</span>}
          </div>
          <div className="flex flex-col gap-0.5">
            <span className={LABEL}>왜 문제인가</span>
            <span className="exception-why text-[12px] leading-snug">{why || '-'}</span>
            {item && (
              <span className="text-[11px] text-[#5B616A]">
                {rawValue ? (
                  <>
                    CoA 기재: <b className="font-semibold tabular-nums">{rawValue}</b> ·{' '}
                  </>
                ) : (
                  <>CoA 기재: <b className="font-semibold tabular-nums">{formatConverted(item)}</b> · </>
                )}
                사내 규격 <span className="tabular-nums">{formatSpec(item)}</span>
              </span>
            )}
          </div>
          <div className="flex flex-col gap-1">
            <span className={LABEL}>해결 조건</span>
            <span className="exception-condition text-[12px] font-semibold leading-snug tabular-nums">{condition || '-'}</span>
            {resolutionType && (
              <span>
                <span className="resolution-type-chip inline-flex h-5 items-center rounded-full bg-[#EEF0F3] px-2 text-[11px] font-semibold text-[#5B616A]">
                  {RESOLUTION_ACTION_LABEL[resolutionType]}
                </span>
              </span>
            )}
          </div>
        </div>

        {followUps === null ? (
          <div className="exception-draft-error flex flex-col items-start justify-center gap-2 text-[12px] text-[#5B616A]">
            <span>문의 초안을 불러오지 못했습니다.</span>
            {onRetry && (
              <button type="button" onClick={onRetry} className="h-7 rounded-md border border-[#D0D4DA] bg-white px-2.5 text-[12px] font-semibold text-[#1F2328]">
                다시 불러오기
              </button>
            )}
          </div>
        ) : draft && (toSupplier || showCombined) ? (
          <DraftBox title={showCombined ? '묶음 문의 초안 (같은 공급사)' : '문의 초안 (이 로트)'} draft={draft} />
        ) : (
          <div className="exception-draft-none flex items-center text-[12px] text-[#8A9099]">
            {toSupplier ? '이 로트의 문의 초안이 없습니다.' : '내부에서 확인하는 항목이라 공급사 문의 초안이 없습니다.'}
          </div>
        )}
      </div>

      {(onReply || openCount > 1) && (
        <div className="exception-panel-footer flex items-center justify-between gap-3 border-t border-[#E3E5E8] bg-[#F9FAFB] px-5 py-2">
          <span className="flex items-center gap-2 text-[12px] text-[#5B616A]">
            {openCount > 1 && (
              <>
                <Icon name="mail" size={13} />
                {supplier ? `같은 공급사(${supplier})의 열린 요청` : '같은 공급사의 열린 요청'} <b className="font-semibold tabular-nums text-[#1F2328]">{`${openCount}건`}</b>
                {combined && (
                  <button
                    type="button"
                    onClick={() => setShowCombined((value) => !value)}
                    className="btn-combined-draft h-7 rounded-md border border-[#D0D4DA] bg-white px-2.5 text-[12px] font-semibold text-[#1F2328]"
                  >
                    {showCombined ? '이 로트 초안 보기' : '묶음 초안 보기'}
                  </button>
                )}
              </>
            )}
          </span>
          {onReply && (
            <span className="flex items-center gap-2">
              {replyTarget && <span className="text-[11px] text-[#5B616A]">{`입력 항목: ${replyTarget}`}</span>}
              <button
                type="button"
                onClick={onReply}
                className="btn-open-reply flex h-8 shrink-0 items-center gap-1.5 rounded-md bg-[#2B4FCB] px-3.5 text-[13px] font-semibold text-white"
              >
                <Icon name="pencil" size={13} />
                회신값 입력
              </button>
            </span>
          )}
        </div>
      )}
    </div>
  );
}
