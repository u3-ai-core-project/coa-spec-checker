import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { ActionBar } from './components/ActionBar';
import { ApprovalCancelDialog } from './components/ApprovalCancelDialog';
import { ApprovalSummary } from './components/ApprovalSummary';
import { CompleteDialog } from './components/CompleteDialog';
import { ExceptionInfo } from './components/ExceptionInfo';
import { FollowUpRow } from './components/FollowUpRow';
import { HistoryCard } from './components/HistoryCard';
import { ItemEditor, type ItemEditSubmit } from './components/ItemEditor';
import { ItemsPanel } from './components/ItemsPanel';
import { MappingDialog } from './components/MappingDialog';
import { PdfPanel } from './components/PdfPanel';
import type { PdfHighlight } from './components/PdfViewer';
import { type QueuePosition, ReviewHeader } from './components/ReviewHeader';
import { useReviewData } from './hooks/useReviewData';
import { hasFollowUp } from './lib/followUp';
import { buildHistory } from './lib/history';
import { writeLastViewed } from './lib/lastViewed';
import { Icon } from './shared/components/Icon';
import { api } from './shared/api';
import { errorMessage, isApiError } from './shared/api/errors';
import type { ExtractionItem, HoldFollowUp } from './shared/api/types';
import { ErrorNotice } from './shared/components/EmptyState';
import { useCurrentUser } from './shared/currentUser';
import { REVIEW_QUEUE_STATUS } from './shared/domain/constants';
import { pendingLowConfidenceCount, processedKind } from './shared/domain/items';
import { isEditableStatus } from './shared/domain/status';
import { useAsync } from './shared/hooks/useAsync';
import { Header } from './shell/Header';

/** 원본 위 하이라이트 색. 수정·확인을 마친 항목은 파랑, 그 외에는 판정 색에 맞춥니다(시안 2-1). */
const HIGHLIGHT_FILL: Partial<Record<ExtractionItem['judgement'], string>> = {
  check: '#FBE9A6',
  fail: '#F6C9C6',
  undetermined: '#E3DAF7',
};
const RESOLVED_FILL = '#DCE5FB';

/** 라우트 /review/:documentId. 문서를 바꾸면 화면 상태를 처음부터 다시 시작합니다. */
export function ReviewPage() {
  const { documentId = '' } = useParams();
  return <ReviewScreen key={documentId} documentId={documentId} />;
}

function ReviewScreen({ documentId }: { documentId: string }) {
  const user = useCurrentUser();
  const navigate = useNavigate();
  const { data, error, reload } = useReviewData(documentId);

  const [selectedId, setSelectedId] = useState<string | null>(null);
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
        <Header role={user.role} title="검수" />
        <main className="body flex min-h-0 flex-1 flex-col items-center justify-center gap-4 p-6">
          {error ? (
            <>
              <ErrorNotice message={errorMessage(error)} onRetry={reload} />
              <Link to="/review" className="text-[13px] font-semibold text-[#2B4FCB]">
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
  const pending = pendingLowConfidenceCount(data.extraction.items, data.reviewLogs);

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

  function select(item: ExtractionItem) {
    setSelectedId(item.item_id);
    if (item.bbox) setPage(item.bbox.page);
  }

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

  async function submitEdit(item: ExtractionItem, { value, reason }: ItemEditSubmit) {
    setBusy(true);
    setEditError(null);
    try {
      // 판정과 이탈 폭은 서버가 다시 계산합니다. 응답으로 다시 불러와 화면에 반영합니다.
      await api.patchItem(documentId, item.item_id, { converted_value: value }, { reason });
      await reload();
      setEditingId(null);
    } catch (failure) {
      await handleFailure(failure, setEditError);
    } finally {
      setBusy(false);
    }
  }

  async function verify(item: ExtractionItem) {
    setBusy(true);
    setActionError(null);
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
      <ReviewHeader doc={data.doc} role={user.role} queue={queue} onMove={(id) => navigate(`/review/${id}`)} />
      <main className="body flex min-h-0 flex-1 gap-[18px] overflow-hidden p-6">
        <PdfPanel
          documentId={documentId}
          page={page}
          onPageChange={setPage}
          highlights={highlights}
          footer={readonly || data.approvalLogs.length > 0 ? <HistoryCard entries={history} /> : undefined}
        />
        <ItemsPanel
          data={data}
          readonly={readonly}
          docInfoCollapsed={docInfoCollapsed}
          onToggleDocInfo={() => setDocInfoChoice(!docInfoCollapsed)}
          onSelect={select}
          followUpKinds={followUpKinds}
          onToggleFollowUp={toggleFollowUp}
          approvalSummary={readonly ? <ApprovalSummary doc={data.doc} /> : undefined}
          getRowExtras={(item) => ({
            onEdit: canEdit && !busy ? () => openEditor(item) : undefined,
            onVerify: canEdit && !busy ? () => void verify(item) : undefined,
            onMap: canEdit && !busy ? () => { select(item); setMappingId(item.item_id); } : undefined,
            // [v1.4안] 사유 코드와 해결 조건은 선택한 항목 아래에서만 보여 줍니다.
            exception: selectedId === item.item_id ? <ExceptionInfo item={item} /> : undefined,
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
          onClose={() => setCompleteOpen(false)}
          onDone={() => {
            setCompleteOpen(false);
            void reload();
          }}
          onStale={() => void reload()}
        />
      )}
    </>
  );
}
