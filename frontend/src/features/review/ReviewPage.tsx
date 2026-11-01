import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { ActionBar } from './components/ActionBar';
import { ApprovalCancelDialog } from './components/ApprovalCancelDialog';
import { ApprovalSummary } from './components/ApprovalSummary';
import { CompleteDialog } from './components/CompleteDialog';
import { ExceptionPanel } from './components/ExceptionPanel';
import { FollowUpRow } from './components/FollowUpRow';
import { HistoryCard } from './components/HistoryCard';
import { ItemEditor, type ItemEditSubmit } from './components/ItemEditor';
import { ItemsPanel } from './components/ItemsPanel';
import { MappingDialog } from './components/MappingDialog';
import { PdfPanel } from './components/PdfPanel';
import type { PdfHighlight } from './components/PdfViewer';
import { ReplyResultStrip, ResolvedNote } from './components/ReplyResultStrip';
import { type QueuePosition, ReviewHeader } from './components/ReviewHeader';
import { useAiDraft } from './hooks/useAiDraft';
import { useReviewData } from './hooks/useReviewData';
import { hasFollowUp } from './lib/followUp';
import { buildHistory } from './lib/history';
import { writeLastViewed } from './lib/lastViewed';
import { isResolved, type ReplyResult } from './lib/replyResult';
import { Icon } from './shared/components/Icon';
import { api } from './shared/api';
import { errorMessage, isApiError } from './shared/api/errors';
import type { ExtractionItem, HoldFollowUp } from './shared/api/types';
import { ErrorNotice } from './shared/components/EmptyState';
import { useCurrentUser } from './shared/currentUser';
import { REVIEW_PATH, REVIEW_QUEUE_STATUS } from './shared/domain/constants';
import { pendingLowConfidenceCount, processedKind } from './shared/domain/items';
import { isEditableStatus } from './shared/domain/status';
import { useAsync } from './shared/hooks/useAsync';
import { PageIntro } from './shell/PageIntro';

/** 원본 위 하이라이트 색. 수정·확인을 마친 항목은 파랑, 그 외에는 판정 색에 맞춥니다(시안 2-1). */
const HIGHLIGHT_FILL: Partial<Record<ExtractionItem['judgement'], string>> = {
  check: '#FBE9A6',
  fail: '#F6C9C6',
  undetermined: '#E3DAF7',
};
const RESOLVED_FILL = '#DCE5FB';

/** 라우트 REVIEW_PATH/:documentId(/inspection/:documentId). 문서를 바꾸면 화면 상태를 처음부터 다시 시작합니다. */
export function ReviewPage() {
  const { documentId = '' } = useParams();
  return <ReviewScreen key={documentId} documentId={documentId} />;
}

function ReviewScreen({ documentId }: { documentId: string }) {
  const user = useCurrentUser();
  const navigate = useNavigate();
  const { data, error, reload } = useReviewData(documentId);
  const aiDraft = useAiDraft(documentId, data?.followUps ?? null);

  const [selectedId, setSelectedId] = useState<string | null>(null);
  /** 원본 문서 아래에 여는 예외 상세 패널(시안 2-11). 예외가 있는 항목 또는 문서 단위 문제를 눌렀을 때 열립니다. */
  const [detail, setDetail] = useState<{ kind: 'item'; id: string } | { kind: 'issue'; code: string } | null>(null);
  /** 회신값을 넣고 서버가 다시 판정한 결과(시안 2-12b). 다음 수정, 확인을 시작하거나 닫으면 지웁니다. */
  const [replyResult, setReplyResult] = useState<ReplyResult | null>(null);
  useEffect(() => writeLastViewed(documentId), [documentId]);
  const [page, setPage] = useState(1);
  /** null이면 아직 사용자가 정하지 않은 상태입니다. 처분된 문서는 접힌 채, 그 외에는 펼친 채 시작합니다. */
  const [docInfoChoice, setDocInfoChoice] = useState<boolean | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  /** 후속 조치 줄을 펼친 판정 종류("판정 불가", "누락" 건수 칩으로 켜고 끕니다). */
  const [followUpKinds, setFollowUpKinds] = useState<Set<ExtractionItem['judgement']>>(new Set());
  const [busy, setBusy] = useState(false);
  /** 수정 박스 안에 보이는 오류 */
  const [editError, setEditError] = useState<string | null>(null);
  /** 액션 바에 보이는 오류(값 확인 등) */
  const [actionError, setActionError] = useState<string | null>(null);
  // 다이얼로그. 주소에 ?dialog=complete를 붙이면 열린 채로 시작합니다(시안 비교용).
  const [searchParams] = useSearchParams();
  const [completeOpen, setCompleteOpen] = useState(searchParams.get('dialog') === 'complete');
  const [completeFollowUp, setCompleteFollowUp] = useState<HoldFollowUp | undefined>(undefined);
  /** 항목 매핑 수정 다이얼로그. 'auto'는 AI가 추정한 첫 항목(시안 비교용 ?dialog=mapping)입니다. */
  const [mappingId, setMappingId] = useState<string | 'auto' | null>(searchParams.get('dialog') === 'mapping' ? 'auto' : null);
  const [cancelOpen, setCancelOpen] = useState(searchParams.get('dialog') === 'cancel');

  // 이전/다음 이동은 GET /documents?status=extracted,in_review,on_hold 목록 순서 기준입니다.
  const status = data?.doc.status;
  const queueList = useAsync(
    () =>
      api.listDocuments({
        status: REVIEW_QUEUE_STATUS,
        uploaded_by: user.role === 'USER' ? user.id : undefined,
        size: 100,
      }),
    [user.id, user.role, status],
  );

  const queue = useMemo<QueuePosition | null>(() => {
    const ids = queueList.data?.items.map((item) => item.document_id) ?? [];
    const index = ids.indexOf(documentId);
    if (index === -1) return null; // 완료된 문서는 이 목록에 없습니다.
    // 시안처럼 이전/다음 버튼은 항상 활성이므로, 첫 문서에서 이전은 마지막 문서로, 마지막 문서에서 다음은 첫 문서로 갑니다.
    const total = ids.length;
    return {
      index,
      total,
      prevId: total > 1 ? ids[(index - 1 + total) % total] : null,
      nextId: total > 1 ? ids[(index + 1) % total] : null,
    };
  }, [queueList.data, documentId]);

  const highlights = useMemo<PdfHighlight[]>(() => {
    if (!data) return [];
    return data.extraction.items.flatMap((item) => {
      if (!item.bbox) return []; // 누락 항목은 원본에 없으므로 하이라이트하지 않습니다.
      const resolved = processedKind(item.item_id, data.reviewLogs) !== null;
      return [
        {
          key: item.item_id,
          bbox: item.bbox,
          fill: resolved ? RESOLVED_FILL : HIGHLIGHT_FILL[item.judgement],
          selected: item.item_id === selectedId,
        },
      ];
    });
  }, [data, selectedId]);

  // 주소로 매핑 수정을 바로 열 때(?dialog=mapping)는 그 항목을 선택하고 원본을 해당 쪽으로 넘깁니다.
  // 아직 선택한 항목이 없을 때 한 번만 일어나는 조건부 갱신이라 effect 대신 렌더 중에 처리합니다.
  const autoTarget =
    mappingId === 'auto' && data && selectedId === null
      ? data.extraction.items.find((item) => item.mapping_source === 'ai')
      : undefined;
  if (autoTarget) {
    setSelectedId(autoTarget.item_id);
    if (autoTarget.bbox) setPage(autoTarget.bbox.page);
  }

  if (!data) {
    return (
      <>
        <PageIntro title="검수" />
        <main className="body flex min-h-0 flex-1 flex-col items-center justify-center gap-4">
          {error ? (
            <>
              <ErrorNotice message={errorMessage(error)} onRetry={reload} />
              <Link to={REVIEW_PATH} className="text-[13px] font-semibold text-[#2B4FCB]">
                검수 목록으로 돌아가기
              </Link>
            </>
          ) : (
            <p className="text-[14px] text-[#5B616A]">불러오는 중입니다.</p>
          )}
        </main>
      </>
    );
  }

  const readonly = data.doc.status === 'approved';
  const pending = pendingLowConfidenceCount(data.extraction.items);

  const canEdit = isEditableStatus(data.doc.status);
  // 문서 정보는 사용자가 정하기 전에는 항목 영역이 더 필요한 상태(처분 완료, 편집, 후속 조치, 이상 패턴, 다이얼로그)에서 접습니다.
  const needsRoom =
    readonly ||
    editingId !== null ||
    followUpKinds.size > 0 ||
    data.anomalies.length > 0 ||
    (data.extraction.document_issues ?? []).length > 0 ||
    completeOpen ||
    cancelOpen ||
    mappingId !== null;
  const docInfoCollapsed = docInfoChoice ?? needsRoom;
  const history = buildHistory({
    reviewLogs: data.reviewLogs,
    approvalLogs: data.approvalLogs,
    items: data.extraction.items,
  });
  const mappingItem =
    mappingId === null
      ? undefined
      : data.extraction.items.find((item) =>
          mappingId === 'auto' ? item.mapping_source === 'ai' : item.item_id === mappingId,
        );
  // 승인 취소는 관리자만 할 수 있습니다.
  const canCancelApproval = readonly && user.role === 'ADMIN';
  // 회신값으로 예외가 풀린 항목(사유 코드가 사라짐)의 상세는 닫고, 원래의 승인 이력 카드로 돌아갑니다(시안 2-12b).
  const detailFound = detail?.kind === 'item' ? data.extraction.items.find((entry) => entry.item_id === detail.id) : undefined;
  const detailItem = detailFound?.reason_code ? detailFound : null;

  const extraction = data.extraction;

  function select(item: ExtractionItem) {
    setSelectedId(item.item_id);
    if (item.bbox) setPage(item.bbox.page);
    // 예외가 있는 항목이면 예외 상세 패널을 열고, 아니면 닫습니다(원래의 승인 이력 카드로 돌아갑니다).
    setDetail(item.reason_code ? { kind: 'item', id: item.item_id } : null);
  }

  /** 문서 단위 문제(로트 불일치 등)의 상세를 엽니다. 항목 선택은 해제합니다. */
  function selectIssue(code: string) {
    setSelectedId(null);
    setDetail({ kind: 'issue', code });
  }

  /**
   * 회신값을 입력할 항목. 값을 받아야 하는 예외(resolution.type이 confirm이 아님)만 대상이고,
   * 개별값 받기(single_value)는 resolution.target_item 항목에 입력합니다(예: 중금속 총량 → Pb).
   */
  function replyTargetOf(item: ExtractionItem): ExtractionItem | null {
    const resolution = item.resolution;
    if (!canEdit || !resolution || resolution.type === 'confirm') return null;
    if (resolution.type === 'single_value' && resolution.target_item && resolution.target_item !== item.normalized_name) {
      return extraction.items.find((entry) => entry.normalized_name === resolution.target_item) ?? null;
    }
    return item;
  }
  const detailReplyTarget = detailItem ? replyTargetOf(detailItem) : null;

  /** "판정 불가", "누락" 건수 칩: 해당 항목들의 후속 조치 줄을 펼치거나 접습니다(시안 2-8). */
  function toggleFollowUp(judgement: ExtractionItem['judgement']) {
    setFollowUpKinds((current) => {
      const next = new Set(current);
      if (next.has(judgement)) next.delete(judgement);
      else next.add(judgement);
      return next;
    });
  }

  /** 후속 조치 버튼: 보류 다이얼로그를 해당 후속 조치가 선택된 채 엽니다. */
  function requestFollowUp(followUp: HoldFollowUp) {
    setCompleteFollowUp(followUp);
    setCompleteOpen(true);
  }

  function openEditor(item: ExtractionItem) {
    select(item);
    setEditingId(item.item_id);
    setEditError(null);
    setActionError(null);
    setReplyResult(null);
    setDocInfoChoice(true); // 편집 박스가 들어갈 자리를 만듭니다.
  }

  /** 서버 오류를 안내하고, 이미 처분된 문서처럼 상태가 바뀐 경우에는 다시 불러옵니다. */
  async function handleFailure(failure: unknown, show: (message: string) => void) {
    show(errorMessage(failure));
    if (isApiError(failure, 'ALREADY_APPROVED')) {
      setEditingId(null);
      await reload();
    }
  }

  async function submitEdit(item: ExtractionItem, { value, reason, valueSource, qualifier }: ItemEditSubmit) {
    setBusy(true);
    setEditError(null);
    // 값을 받아야 하는 예외에 회신값을 넣는 경우에는 재판정 결과(시안 2-12b)를 보여 줍니다. 입력 전 값을 기억해 둡니다.
    const reply = item.resolution != null && item.resolution.type !== 'confirm';
    const before = { judgement: item.judgement, recommendation: extraction.lot_recommendation, summary: extraction.summary };
    try {
      // 판정과 이탈 폭은 서버가 다시 계산합니다. 응답으로 다시 불러와 화면에 반영합니다.
      const result = await api.patchItem(
        documentId,
        item.item_id,
        // 수정 사유는 값 수정에서 필수이고 요청에 함께 보냅니다(백엔드 확정 답변).
        qualifier === 'not_detected'
          ? { value_qualifier: 'not_detected', detection_limit: value, value_source: valueSource, reason }
          : qualifier === 'less_than'
            ? { value_qualifier: 'less_than', converted_value: value, value_source: valueSource, reason }
            : { converted_value: value, value_source: valueSource, reason },
      );
      await reload();
      setEditingId(null);
      setReplyResult(
        reply
          ? {
              itemId: item.item_id,
              name: item.normalized_name,
              beforeJudgement: before.judgement,
              after: result.item,
              beforeRecommendation: before.recommendation,
              afterRecommendation: result.lot_recommendation,
              beforeSummary: before.summary,
              afterSummary: result.summary,
            }
          : null,
      );
    } catch (failure) {
      await handleFailure(failure, setEditError);
    } finally {
      setBusy(false);
    }
  }

  async function verify(item: ExtractionItem) {
    setBusy(true);
    setActionError(null);
    setReplyResult(null);
    try {
      await api.confirmItem(documentId, item.item_id);
      await reload();
    } catch (failure) {
      await handleFailure(failure, setActionError);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <ReviewHeader doc={data.doc} queue={queue} onMove={(id) => navigate(`${REVIEW_PATH}/${id}`)} />
      <main className="body flex min-h-0 flex-1 gap-[18px] overflow-hidden">
        <PdfPanel
          documentId={documentId}
          page={page}
          onPageChange={setPage}
          highlights={highlights}
          footer={
            detailItem || detail?.kind === 'issue' ? (
              <ExceptionPanel
                key={detail?.kind === 'item' ? detail.id : detail?.code}
                item={detailItem}
                issueCode={detail?.kind === 'issue' ? detail.code : undefined}
                followUps={data.followUps}
                onReply={detailReplyTarget && !busy ? () => openEditor(detailReplyTarget) : undefined}
                replyTarget={detailItem && detailReplyTarget && detailReplyTarget !== detailItem ? detailReplyTarget.normalized_name : undefined}
                onClose={() => setDetail(null)}
                onRetry={() => void reload()}
                aiDraft={{
                  followUps: aiDraft.followUps,
                  hasResult: aiDraft.hasResult,
                  loading: aiDraft.loading,
                  error: aiDraft.error,
                  onRequest: () => void aiDraft.request(),
                  onShowTemplate: aiDraft.showTemplate,
                }}
              />
            ) : readonly || data.approvalLogs.length > 0 ? (
              <HistoryCard entries={history} />
            ) : undefined
          }
        />
        <ItemsPanel
          data={data}
          readonly={readonly}
          docInfoCollapsed={docInfoCollapsed}
          onToggleDocInfo={() => setDocInfoChoice(!docInfoCollapsed)}
          onSelect={select}
          onSelectIssue={selectIssue}
          followUpKinds={followUpKinds}
          onToggleFollowUp={toggleFollowUp}
          approvalSummary={
            readonly ? (
              <ApprovalSummary doc={data.doc} />
            ) : replyResult ? (
              <ReplyResultStrip result={replyResult} onClose={() => setReplyResult(null)} />
            ) : undefined
          }
          getRowExtras={(item) => ({
            onEdit: canEdit && !busy ? () => openEditor(item) : undefined,
            onVerify: canEdit && !busy ? () => void verify(item) : undefined,
            onMap: canEdit && !busy ? () => { select(item); setMappingId(item.item_id); } : undefined,
            // 회신값으로 예외가 풀린 항목 아래에 "해결됨"을 보여 줍니다(시안 2-12b).
            exception: replyResult && replyResult.itemId === item.item_id && isResolved(replyResult) ? <ResolvedNote result={replyResult} /> : undefined,
            followUp:
              canEdit && hasFollowUp(item) && followUpKinds.has(item.judgement) ? (
                <FollowUpRow item={item} onRequest={requestFollowUp} />
              ) : undefined,
            editor:
              editingId === item.item_id ? (
                <ItemEditor
                  item={item}
                  busy={busy}
                  error={editError}
                  onCancel={() => setEditingId(null)}
                  onSubmit={(submit) => void submitEdit(item, submit)}
                />
              ) : undefined,
          })}
          actionBar={
            <ActionBar
              readonly={readonly}
              pending={pending}
              error={actionError}
              readonlyAction={
                canCancelApproval ? (
                  <button
                    type="button"
                    onClick={() => setCancelOpen(true)}
                    className="btn-cancel-approval flex h-10 shrink-0 items-center gap-1.5 rounded-lg border border-[#C0342E]/40 bg-white px-4 text-[14px] font-semibold text-[#C0342E]"
                  >
                    <Icon name="undo" />
                    승인 취소
                  </button>
                ) : undefined
              }
              onComplete={() => {
                setCompleteFollowUp(undefined);
                setCompleteOpen(true);
              }}
            />
          }
        />
      </main>
      {mappingItem && canEdit && (
        <MappingDialog
          doc={data.doc}
          item={mappingItem}
          specs={data.specs}
          page={mappingItem.bbox?.page ?? null}
          onClose={() => setMappingId(null)}
          onDone={() => {
            setMappingId(null);
            void reload();
          }}
          onStale={() => void reload()}
        />
      )}
      {cancelOpen && canCancelApproval && (
        <ApprovalCancelDialog
          doc={data.doc}
          onClose={() => setCancelOpen(false)}
          onDone={() => {
            setCancelOpen(false);
            setDocInfoChoice(null);
            void reload();
          }}
          onStale={() => void reload()}
        />
      )}
      {completeOpen && !readonly && (
        <CompleteDialog
          doc={data.doc}
          extraction={data.extraction}
          pending={pending}
          initialFollowUp={completeFollowUp}
          suggestedFollowUp={data.followUps?.suggested_follow_up ?? null}
          onClose={() => setCompleteOpen(false)}
          onDone={(completed) => {
            setCompleteOpen(false);
            // 보류로 완료하면 검수 목록으로 돌아갑니다. 처분(승인, 조건부 승인, 불합격)은 이 화면에서 처분 결과를 보여 줍니다.
            if (completed === 'hold') navigate(REVIEW_PATH);
            else void reload();
          }}
          onStale={() => void reload()}
        />
      )}
    </>
  );
}
