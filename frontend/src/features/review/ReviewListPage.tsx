import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from './shared/api';
import { errorMessage } from './shared/api/errors';
import type { DocumentListItem } from './shared/api/types';
import { useCurrentUser } from './shared/currentUser';
import { DispositionBadge, RecommendationBadge, StatusBadge } from './shared/components/badges';
import { EmptyState, ErrorNotice } from './shared/components/EmptyState';
import { Icon } from './shared/components/Icon';
import { formatDateTime } from './shared/domain/format';
import { dispositionOf } from './shared/domain/recommendation';
import { STATUS_META, STATUS_ORDER, type StatusKey } from './shared/domain/status';
import { DeleteDocumentDialog } from './components/DeleteDocumentDialog';
import { readLastViewed } from './lib/lastViewed';
import { useAsync } from './shared/hooks/useAsync';
import { PageIntro } from './shell/PageIntro';
import { REVIEW_PATH } from './shared/domain/constants';

type Filter = 'all' | StatusKey;

/** 추출이 끝나 검수 화면을 열 수 있는 상태 */
function isOpenable(doc: DocumentListItem): boolean {
  return ['extracted', 'in_review', 'on_hold', 'approved'].includes(doc.status);
}

/** 삭제 버튼을 누를 수 없는 문서와 그 이유(툴팁). 서버가 같은 상태에서 409로 거절합니다. */
function deleteBlockReason(doc: DocumentListItem): string | null {
  if (doc.status === 'approved') return '처분 완료 문서는 삭제할 수 없습니다. 처분 취소 후 삭제하세요.';
  if (doc.status === 'processing') return '추출 중인 문서는 삭제할 수 없습니다. 추출이 끝난 뒤 삭제하세요.';
  return null;
}

/** 한 페이지에 불러오는 문서 수(서버 size 상한과 같음). 넘으면 이전/다음으로 넘깁니다. */
const PAGE_SIZE = 100;

/** 필터 탭이 서버에 보내는 status 값(쉼표로 여러 개). "전체"는 보내지 않습니다. */
const FILTER_STATUS: Record<StatusKey, string> = {
  queued: 'queued',
  processing: 'processing',
  reviewing: 'extracted,in_review',
  on_hold: 'on_hold',
  done: 'approved',
  failed: 'failed',
};

/** 탭 개수를 받아 오는 순서: 전체, 그리고 상태별 */
const TAB_KEYS: Filter[] = ['all', ...STATUS_ORDER];

/** 시안 2-7 검수 목록 (빈 상태는 시안 2-0) */
export function ReviewListPage() {
  const user = useCurrentUser();
  const navigate = useNavigate();
  const [filter, setFilter] = useState<Filter>('all');
  const [page, setPage] = useState(1);
  const [deleting, setDeleting] = useState<DocumentListItem | null>(null);

  // 사용자는 uploaded_by로 본인 문서만, 관리자는 전체를 봅니다. 상태 필터와 페이지는 서버에 맡기고 total로 전체 개수를 압니다.
  const uploadedBy = user.role === 'USER' ? user.id : undefined;
  const { data, error, loading, reload } = useAsync(
    () =>
      api.listDocuments({
        uploaded_by: uploadedBy,
        status: filter === 'all' ? undefined : FILTER_STATUS[filter],
        page,
        size: PAGE_SIZE,
      }),
    [user.id, user.role, filter, page],
  );
  // 탭마다 보여 줄 개수: 상태별로 size 1만 요청해 total만 받습니다(현재 페이지에 없는 문서도 센다).
  const countsQuery = useAsync(
    () =>
      Promise.all(
        TAB_KEYS.map((key) =>
          api.listDocuments({ uploaded_by: uploadedBy, status: key === 'all' ? undefined : FILTER_STATUS[key], size: 1 }).then((result) => result.total),
        ),
      ),
    [user.id, user.role],
  );

  const docs = useMemo(() => data?.items ?? [], [data]);
  const total = data?.total ?? 0;
  const lastPage = Math.max(1, Math.ceil(total / PAGE_SIZE));
  // 마지막 페이지가 줄어든 뒤(문서가 처분되어 필터에서 빠지는 등)에도 빈 페이지에 머물지 않게 합니다.
  if (data && page > lastPage) setPage(lastPage);
  const counts = useMemo(() => {
    const totals = countsQuery.data;
    if (!totals) return null;
    return Object.fromEntries(TAB_KEYS.map((key, index) => [key, totals[index]])) as Record<Filter, number>;
  }, [countsQuery.data]);
  // 마지막으로 본 문서(없으면 다음에 검수할 문서)의 행을 연하게 강조합니다.
  const lastViewed = readLastViewed();
  const highlightId =
    docs.find((doc) => doc.document_id === lastViewed)?.document_id ??
    docs.find((doc) => ['extracted', 'in_review', 'on_hold'].includes(doc.status))?.document_id ??
    null;
  const firstShown = docs.length === 0 ? 0 : (page - 1) * PAGE_SIZE + 1;
  const lastShown = (page - 1) * PAGE_SIZE + docs.length;

  // 필터와 관계없는 전체 문서 수(탭 개수를 받기 전에는 "전체" 필터일 때만 알 수 있습니다)
  const scopeTotal = counts?.all ?? (filter === 'all' ? total : null);
  const scopeLabel = `${user.role === 'USER' ? `${user.name} 담당` : '전체'} ${scopeTotal ?? '-'}건`;
  function selectFilter(next: Filter) {
    setFilter(next);
    setPage(1);
  }
  // 사용자는 본인이 올린 문서에만, 관리자는 전체에 삭제 버튼을 보입니다(서버도 같은 규칙으로 403을 줍니다).
  const canDelete = (doc: DocumentListItem) => user.role === 'ADMIN' || doc.uploaded_by === user.name;
  const refreshAfterDelete = () => {
    reload();
    countsQuery.reload();
  };
  const header = (
    <PageIntro title="검수 목록" subtitle="업로드된 문서를 상태별로 확인하고 검수를 시작합니다." />
  );

  if (error && !data) {
    return (
      <>
        {header}
        <main className="body flex min-h-0 flex-1 items-center justify-center">
          <ErrorNotice
            message={errorMessage(error)}
            onRetry={() => {
              reload();
              countsQuery.reload();
            }}
          />
        </main>
      </>
    );
  }

  // 문서가 하나도 없을 때만 빈 화면(시안 2-0)입니다. 필터 결과가 비는 것은 표 안에서 안내합니다.
  if (!loading && filter === 'all' && data && data.total === 0) {
    return (
      <>
        <PageIntro title="검수" />
        <main className="body flex min-h-0 flex-1 items-center justify-center">
          <EmptyState
            title="선택된 문서가 없습니다"
            message="업로드 화면에서 문서를 선택해 주십시오."
            action={
              <button
                type="button"
                onClick={() => navigate('/upload')}
                className="btn-go-upload mt-2 flex h-10 items-center gap-1.5 rounded-lg bg-[#2B4FCB] px-5 text-[14px] font-semibold text-white"
              >
                <Icon name="upload" size={16} />
                업로드
              </button>
            }
            note="지원 형식: PDF, PNG, JPG"
          />
        </main>
      </>
    );
  }

  return (
    <>
      {header}
      <main className="body flex min-h-0 flex-1 flex-col gap-4">
        <div className="list-toolbar flex items-center justify-between">
          <div className="filter-tabs flex items-center gap-2">
            <FilterTab label="전체" count={counts?.all ?? null} active={filter === 'all'} onClick={() => selectFilter('all')} />
            {STATUS_ORDER.map((key) => (
              <FilterTab
                key={key}
                label={STATUS_META[key].label}
                count={counts?.[key] ?? null}
                active={filter === key}
                onClick={() => selectFilter(key)}
              />
            ))}
          </div>
        </div>
        <section className="doc-list flex min-h-0 flex-1 flex-col overflow-hidden rounded-xl border border-[#E3E5E8] bg-white">
          <div className="min-h-0 flex-1 overflow-y-auto">
            <table className="doc-table w-full text-left">
              <thead className="sticky top-0 bg-[#F9FAFB]">
                <tr className="text-[12px] font-semibold text-[#5B616A]">
                  <th className="px-5 py-2.5 font-semibold">#</th>
                  <th className="px-2 py-2.5 font-semibold">파일명</th>
                  <th className="px-2 py-2.5 font-semibold">협력사</th>
                  <th className="px-2 py-2.5 font-semibold">업로드 일시</th>
                  <th className="px-2 py-2.5 font-semibold">상태</th>
                  <th className="px-2 py-2.5 font-semibold">AI 권고</th>
                  <th className="px-2 py-2.5 font-semibold">담당자 처분</th>
                  <th className="w-14 px-2 py-2.5 pr-5 text-center font-semibold">삭제</th>
                </tr>
              </thead>
              <tbody>
                {docs.map((doc, index) => (
                  <DocRow key={doc.document_id} doc={doc} index={(page - 1) * PAGE_SIZE + index} highlighted={doc.document_id === highlightId}
                    onOpen={() => navigate(`${REVIEW_PATH}/${doc.document_id}`)}
                    deletable={canDelete(doc)}
                    onDelete={() => setDeleting(doc)}
                  />
                ))}
                {docs.length === 0 && !loading && (
                  <tr>
                    <td colSpan={8} className="px-5 py-10 text-center text-[13px] text-[#8A9099]">
                      해당 상태의 문서가 없습니다.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
          <div className="list-footer mt-auto flex items-center justify-between border-t border-[#E3E5E8] px-5 py-2.5 text-[12px] text-[#5B616A]">
            <span>{scopeLabel} · 행을 선택하면 검수 화면으로 이동합니다.</span>
            <span className="flex items-center gap-3">
              <span className="list-range tabular-nums">
                {firstShown}–{lastShown} / {total}
              </span>
              <span className="list-pager flex items-center gap-1.5">
                <PagerButton label="이전" disabled={page <= 1 || loading} onClick={() => setPage(page - 1)} />
                <span className="list-page tabular-nums">
                  {page} / {lastPage} 페이지
                </span>
                <PagerButton label="다음" disabled={page >= lastPage || loading} onClick={() => setPage(page + 1)} />
              </span>
            </span>
          </div>
        </section>
      </main>
      {deleting && (
        <DeleteDocumentDialog
          doc={deleting}
          onClose={() => setDeleting(null)}
          onDone={() => {
            setDeleting(null);
            refreshAfterDelete();
          }}
          onStale={refreshAfterDelete}
        />
      )}
    </>
  );
}

function PagerButton({ label, disabled, onClick }: { label: string; disabled: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      className="btn-page flex h-7 items-center rounded-md border border-[#D0D4DA] bg-white px-2.5 text-[12px] font-semibold text-[#1F2328] disabled:cursor-not-allowed disabled:text-[#B6BBC4]"
    >
      {label}
    </button>
  );
}

function FilterTab({ label, count, active, onClick }: { label: string; count: number | null; active: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`filter-tab flex h-8 items-center gap-1.5 rounded-lg px-3 text-[13px] font-semibold ${
        active ? 'bg-[#2B4FCB] text-white' : 'border border-[#D0D4DA] bg-white text-[#5B616A]'
      }`}
    >
      {label}
      <b className={`tabular-nums font-semibold ${active ? 'text-white/80' : 'text-[#8A9099]'}`}>{count ?? '–'}</b>
    </button>
  );
}

interface DocRowProps {
  doc: DocumentListItem;
  index: number;
  highlighted: boolean;
  onOpen: () => void;
  /** 삭제 버튼을 보일지(USER는 본인 문서만) */
  deletable: boolean;
  onDelete: () => void;
}

function DocRow({ doc, index, highlighted, onOpen, deletable, onDelete }: DocRowProps) {
  const openable = isOpenable(doc);
  const blockReason = deleteBlockReason(doc);
  const disposition = dispositionOf(doc);
  return (
    <tr
      className={`doc-row border-t border-[#E3E5E8]${highlighted ? ' bg-[#F3F6FE]' : ''} ${openable ? 'cursor-pointer hover:bg-[#F3F6FE]' : ''}`}
      onClick={openable ? onOpen : undefined}
      title={doc.status === 'failed' ? (doc.error_message ?? undefined) : undefined}
    >
      <td className="w-10 px-5 py-2 text-[12px] tabular-nums text-[#8A9099]">{index + 1}</td>
      <td className="px-2 py-2 text-[13px] font-semibold tabular-nums">{doc.file_name}</td>
      <td className="px-2 py-2 text-[13px]">{doc.supplier}</td>
      <td className="px-2 py-2 text-[12px] tabular-nums text-[#5B616A]">{formatDateTime(doc.uploaded_at)}</td>
      <td className="px-2 py-2">
        <StatusBadge status={doc.status} />
      </td>
      <td className="px-2 py-2">
        {doc.lot_recommendation ? (
          <RecommendationBadge recommendation={doc.lot_recommendation} compact />
        ) : (
          <span className="text-[#B6BBC4]">-</span>
        )}
      </td>
      <td className="px-2 py-2">
        {disposition ? <DispositionBadge disposition={disposition} compact /> : <span className="text-[#B6BBC4]">-</span>}
      </td>
      {/* 삭제 칸은 행 클릭(검수 화면 열기)과 겹치지 않도록 클릭이 행으로 올라가지 않게 막습니다. */}
      <td className="doc-delete-cell px-2 py-2 pr-5 text-center" onClick={(event) => event.stopPropagation()}>
        {deletable && (
          <span title={blockReason ?? '문서 삭제'} className="inline-flex">
            <button
              type="button"
              disabled={blockReason !== null}
              aria-label={`${doc.file_name} 삭제`}
              onClick={onDelete}
              className="btn-delete-row flex h-7 w-7 items-center justify-center rounded-md border border-[#D0D4DA] bg-white text-[#C0342E] hover:bg-[#FBEAE9] disabled:cursor-not-allowed disabled:text-[#B6BBC4] disabled:hover:bg-white"
            >
              <Icon name="trash" size={14} />
            </button>
          </span>
        )}
      </td>
    </tr>
  );
}
