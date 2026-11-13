import type { ReactNode } from 'react';
import type { ExtractionItem } from '../shared/api/types';
import { Icon } from '../shared/components/Icon';
import { DispositionBadge, MultiLotBadge, RecommendationBadge } from '../shared/components/badges';
import { formatDate } from '../shared/domain/format';
import { splitItems } from '../shared/domain/items';
import { JUDGEMENT_META, JUDGEMENT_ORDER } from '../shared/domain/judgement';
import { lotDisplay } from '../shared/domain/lots';
import { DOCUMENT_ISSUE_LABEL } from '../shared/domain/exceptions';
import { dispositionOf } from '../shared/domain/recommendation';
import type { ReviewData } from '../hooks/useReviewData';
import { ItemRow, type ItemRowProps, MissingRow } from './ItemRow';

type RowExtras = Pick<ItemRowProps, 'editor' | 'followUp' | 'exception' | 'onEdit' | 'onVerify' | 'onMap'>;

interface ItemsPanelProps {
  data: ReviewData;
  readonly: boolean;
  docInfoCollapsed: boolean;
  onToggleDocInfo(): void;
  onSelect(item: ExtractionItem): void;
  /** 문서 단위 문제(로트 불일치 등) 경고 줄을 눌렀을 때. 예외 상세 패널(시안 2-11)을 엽니다. */
  onSelectIssue?(code: string): void;
  /** 항목별로 덧붙는 요소와 동작(수정 편집 박스, 값 확인, 매핑 수정, 후속 조치 줄) */
  getRowExtras?(item: ExtractionItem): RowExtras;
  /** 후속 조치 줄이 펼쳐진 판정 종류와, 건수 칩으로 켜고 끄는 동작 */
  followUpKinds?: Set<ExtractionItem['judgement']>;
  onToggleFollowUp?(judgement: ExtractionItem['judgement']): void;
  /** 처분이 끝난 문서의 처분 결과 요약 */
  approvalSummary?: ReactNode;
  /** 문서 정보의 "적용 규격" 줄에 들어가는 규격 세트 선택 */
  specSetControl?: ReactNode;
  /** 하단 액션 바 */
  actionBar: ReactNode;
}

function CountChip({
  judgement,
  count,
  active,
  onToggle,
}: {
  judgement: (typeof JUDGEMENT_ORDER)[number];
  count: number;
  active?: boolean;
  onToggle?(): void;
}) {
  const meta = JUDGEMENT_META[judgement];
  const className = `count-chip count-chip-${judgement} inline-flex items-center gap-1 whitespace-nowrap rounded-full px-2 py-1 text-[11px] font-semibold${
    count === 0 ? ' opacity-40' : ''
  }`;
  const style = { backgroundColor: meta.bg, color: meta.color };
  const content = (
    <>
      {meta.label}
      <b className="tabular-nums">{count}</b>
    </>
  );
  // 판정 불가와 누락은 눌러서 후속 조치 줄을 펼칩니다. 나머지 칩은 건수만 보여 줍니다.
  if (!onToggle || count === 0) {
    return (
      <span className={className} style={style}>
        {content}
      </span>
    );
  }
  return (
    <button type="button" aria-pressed={active} onClick={onToggle} className={className} style={style}>
      {content}
    </button>
  );
}

function Check({ children }: { children: ReactNode }) {
  return (
    <span className="item-check inline-flex items-center gap-0.5 text-[11px] font-semibold text-[#177A46]">
      <Icon name="check" size={12} />
      {children}
    </span>
  );
}

function InfoLine({ label, children, extra }: { label: string; children: ReactNode; extra?: ReactNode }) {
  return (
    <div className="doc-info-item grid h-5 grid-cols-[104px_1fr] items-center gap-x-3 text-[13px]">
      <span className="text-[12px] text-[#8A9099]">{label}</span>
      <span className="flex items-center gap-2 font-semibold tabular-nums">
        {children}
        {extra}
      </span>
    </div>
  );
}

function DocInfo({
  data,
  collapsed,
  onToggle,
  specSetControl,
}: {
  data: ReviewData;
  collapsed: boolean;
  onToggle(): void;
  specSetControl?: ReactNode;
}) {
  const { doc } = data;
  const lot = lotDisplay(doc);
  const grade = `협력사 ${doc.applied_standard ?? '-'} · 사내 ${doc.spec_grade ?? '-'}`;
  // 협력사 적용 규격과 사내 등급이 다르면 안내합니다(명세 4.6).
  // 업로드할 때 입력한 입고 로트번호가 CoA의 로트번호와 다르면 "발주 정보와 일치" 대신 안내합니다(문서 수준 문제 LOT_MISMATCH와 같은 기준).
  const lotMismatch = doc.received_lot_no !== null && doc.lot_no !== null && doc.received_lot_no !== doc.lot_no;
  const gradeDiffers = doc.applied_standard !== null && doc.spec_grade !== null && !doc.applied_standard.endsWith(doc.spec_grade);

  if (collapsed) {
    return (
      <button
        type="button"
        onClick={onToggle}
        className="docinfo-collapsed flex w-full items-center justify-between border-b border-[#E3E5E8] px-5 py-2.5 text-left text-[12px] text-[#5B616A]"
      >
        <span>
          <b className="font-semibold text-[#1F2328]">문서 정보</b> · {lot.text}
          {lot.multi && (
            <>
              {' '}
              <MultiLotBadge />
            </>
          )}{' '}
          · {formatDate(doc.test_date)} ·{' '}
          {doc.origin ?? '-'} · {grade}
        </span>
        <Icon name="chev_dn" size={14} />
      </button>
    );
  }
  return (
    <>
      <button
        type="button"
        onClick={onToggle}
        className="section-title flex w-full items-center justify-between px-5 pb-1 pt-2 text-left text-[12px] font-semibold text-[#8A9099]"
      >
        <span>문서 정보</span>
        <Icon name="chev_up" size={14} />
      </button>
      <div className="doc-info flex flex-col border-b border-[#E3E5E8] px-5 pb-2 pt-0">
        <InfoLine
          label="Lot No"
          extra={
            lotMismatch ? (
              <span className="doc-info-notice text-[11px] font-semibold text-[#9A5B00]">{`입고 로트번호(${doc.received_lot_no})와 다릅니다.`}</span>
            ) : doc.po_no ? (
              <Check>발주 정보와 일치</Check>
            ) : undefined
          }
        >
          {lot.text}
          {lot.multi && <MultiLotBadge />}
        </InfoLine>
        <InfoLine label="시험일자" extra={doc.test_date ? <Check>유효</Check> : undefined}>
          {formatDate(doc.test_date)}
        </InfoLine>
        <InfoLine label="원산지">{doc.origin ?? '-'}</InfoLine>
        <InfoLine
          label="적용 등급"
          extra={
            gradeDiffers ? (
              <span className="doc-info-notice text-[11px] font-semibold text-[#9A5B00]">협력사 적용 규격과 사내 등급이 다릅니다.</span>
            ) : undefined
          }
        >
          {grade}
        </InfoLine>
        {specSetControl && (
          <div className="doc-info-item doc-info-spec-set grid min-h-7 grid-cols-[104px_1fr] items-center gap-x-3 text-[13px]">
            <span className="text-[12px] text-[#8A9099]">적용 규격</span>
            <div className="min-w-0">{specSetControl}</div>
          </div>
        )}
      </div>
    </>
  );
}

/** 우측 추출 항목 패널: 헤더(건수, AI 권고, 담당자 처분), 문서 정보, 항목 목록, 누락 항목, 하단 액션 바 */
export function ItemsPanel({
  data,
  readonly,
  docInfoCollapsed,
  onToggleDocInfo,
  onSelect,
  onSelectIssue,
  followUpKinds,
  onToggleFollowUp,
  getRowExtras,
  approvalSummary,
  specSetControl,
  actionBar,
}: ItemsPanelProps) {
  const { doc, extraction, reviewLogs, specs, anomalies } = data;
  const { tests, missing } = splitItems(extraction.items, specs.map((spec) => spec.item_name));
  const flagsOf = (item: ExtractionItem) =>
    anomalies.filter((anomaly) => anomaly.item_name === item.normalized_name).map((anomaly) => anomaly.message);
  // [v1.4안] 문서 수준 문제(document_issues)는 시안에 없어, 문서 단위 이상 패턴 경고와 같은 경고 상자 모양으로 먼저 보여 줍니다.
  // 문서 수준 문제는 눌러서 예외 상세 패널(시안 2-11)을 열 수 있고, 문서 단위 이상 패턴 경고는 안내만 합니다.
  const issueFlags = (extraction.document_issues ?? []).map((issue) => ({
    message: `${DOCUMENT_ISSUE_LABEL[issue.code] ?? issue.code} · ${issue.message}`,
    code: issue.code as string | null,
  }));
  const docFlags = [
    ...issueFlags,
    ...anomalies.filter((anomaly) => anomaly.item_name === null).map((anomaly) => ({ message: anomaly.message, code: null as string | null })),
  ];

  return (
    <section className="items-panel flex min-h-0 w-[480px] shrink-0 flex-col rounded-xl border border-[#E3E5E8] bg-white">
      <div className="items-panel-header flex flex-col gap-1.5 border-b border-[#E3E5E8] px-5 py-2">
        <div className="flex items-center justify-between gap-2">
          <h3 className="shrink-0 text-[16px] font-bold">
            추출 항목 <span className="text-[13px] font-normal text-[#8A9099]">{`${extraction.items.length}개`}</span>
          </h3>
          <div className="lot-status flex items-center gap-1.5">
            <RecommendationBadge recommendation={extraction.lot_recommendation} />
            <DispositionBadge disposition={dispositionOf(doc)} />
          </div>
        </div>
        <div className="count-chips flex gap-1.5">
          {JUDGEMENT_ORDER.map((judgement) => (
            <CountChip
              key={judgement}
              judgement={judgement}
              count={extraction.summary[judgement]}
              active={followUpKinds?.has(judgement)}
              onToggle={
                !readonly && onToggleFollowUp && (judgement === 'undetermined' || judgement === 'missing')
                  ? () => onToggleFollowUp(judgement)
                  : undefined
              }
            />
          ))}
        </div>
      </div>
      {approvalSummary}
      <div className="item-scroll min-h-0 flex-1 overflow-y-auto">
        {docFlags.map(({ message, code }) => {
          const open = code !== null && onSelectIssue ? () => onSelectIssue(code) : undefined;
          return (
            <div
              key={message}
              role={open ? 'button' : undefined}
              tabIndex={open ? 0 : undefined}
              onClick={open}
              onKeyDown={open ? (event) => event.key === 'Enter' && open() : undefined}
              className={`item-flag mx-5 mt-2 flex items-start gap-1 rounded-md border border-[#F0C987] bg-[#FFF7E6] px-2 py-1 text-[11px] font-semibold leading-snug text-[#8A5A00]${
                open ? ' cursor-pointer' : ''
              }`}
            >
              <span className="mt-px shrink-0">
                <Icon name="flag" size={12} />
              </span>
              <span>{message}</span>
            </div>
          );
        })}
        <DocInfo data={data} collapsed={docInfoCollapsed} onToggle={onToggleDocInfo} specSetControl={specSetControl} />
        <div className="section-title px-5 pb-0.5 pt-1.5 text-[12px] font-semibold text-[#8A9099]">시험 항목 · {`${tests.length}개`}</div>
        <ul className="item-list item-list-test flex flex-col divide-y divide-[#E3E5E8] border-t border-[#E3E5E8]">
          {tests.map((item) => (
            <ItemRow
              key={item.item_id}
              item={item}
              logs={reviewLogs}
              readonly={readonly}
              flags={flagsOf(item)}
              onSelect={() => onSelect(item)}
              {...getRowExtras?.(item)}
            />
          ))}
        </ul>
        {missing.length > 0 && (
          <>
            <div className="section-title px-5 pb-0.5 pt-1.5 text-[12px] font-semibold text-[#8A9099]">누락 항목 · {`${missing.length}건`}</div>
            <ul className="item-list item-list-missing flex flex-col divide-y divide-[#E3E5E8] border-t border-[#E3E5E8]">
              {missing.map((item) => (
                <MissingRow key={item.item_id} item={item} readonly={readonly} onSelect={() => onSelect(item)} {...getRowExtras?.(item)} />
              ))}
            </ul>
          </>
        )}
      </div>
      <div className="action-bar flex items-center justify-between gap-3 border-t border-[#E3E5E8] px-5 py-2">{actionBar}</div>
    </section>
  );
}
