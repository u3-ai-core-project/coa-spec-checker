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
import { STATUS_META, STATUS_ORDER, type StatusKey, statusKey } from './shared/domain/status';
import { readLastViewed } from './lib/lastViewed';
import { useAsync } from './shared/hooks/useAsync';
import { PageIntro } from './shell/PageIntro';
import { REVIEW_PATH } from './shared/domain/constants';

type Filter = 'all' | StatusKey;

/** 추출이 끝나 검수 화면을 열 수 있는 상태 */
function isOpenable(doc: DocumentListItem): boolean {
  return ['extracted', 'in_review', 'on_hold', 'approved'].includes(doc.status);
}

const PAGE_SIZE = 100;

/** 시안 2-7 검수 목록 (빈 상태는 시안 2-0) */
export function ReviewListPage() {
  const user = useCurrentUser();
  const navigate = useNavigate();
  const [filter, setFilter] = useState<Filter>('all');

  // 사용자는 uploaded_by로 본인 문서만, 관리자는 전체를 봅니다.
  const { data, error, loading, reload } = useAsync(
    () => api.listDocuments({ uploaded_by: user.role === 'USER' ? user.id : undefined, size: PAGE_SIZE }),
    [user.id, user.role],
  );

  const docs = useMemo(() => data?.items ?? [], [data]);
  const counts = useMemo(() => {
    const result = { all: docs.length } as Record<Filter, number>;
    for (const key of STATUS_ORDER) result[key] = 0;
    for (const doc of docs) result[statusKey(doc.status)] += 1;
    return result;
  }, [docs]);
  // 마지막으로 본 문서(없으면 다음에 검수할 문서)의 행을 연하게 강조합니다.
  const lastViewed = readLastViewed();
  const highlightId =
    docs.find((doc) => doc.document_id === lastViewed)?.document_id ??
    docs.find((doc) => ['extracted', 'in_review', 'on_hold'].includes(doc.status))?.document_id ??
    null;
  const visible = filter === 'all' ? docs : docs.filter((doc) => statusKey(doc.status) === filter);

  const scopeLabel = user.role === 'USER' ? `${user.name} 담당 ${docs.length}건` : `전체 ${docs.length}건`;
  const header = (
    <PageIntro title="검수 목록" subtitle="업로드된 문서를 상태별로 확인하고 검수를 시작합니다." />
  );

  if (error && !data) {
    return (
      <>
        {header}
        <main className="body flex min-h-0 flex-1 items-center justify-center">
          <ErrorNotice message={errorMessage(error)} onRetry={reload} />
        </main>
      </>
    );
  }

  if (!loading && docs.length === 0) {
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
            <FilterTab label="전체" count={counts.all} active={filter === 'all'} onClick={() => setFilter('all')} />
            {STATUS_ORDER.map((key) => (
              <FilterTab
                key={key}
                label={STATUS_META[key].label}
                count={counts[key]}
                active={filter === key}
                onClick={() => setFilter(key)}
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
                  <th className="px-2 py-2.5 pr-5 font-semibold">담당자 처분</th>
                </tr>
              </thead>
              <tbody>
                {visible.map((doc, index) => (
                  <DocRow key={doc.document_id} doc={doc} index={index} highlighted={doc.document_id === highlightId} onOpen={() => navigate(`${REVIEW_PATH}/${doc.document_id}`)} />
                ))}
                {visible.length === 0 && (
                  <tr>
                    <td colSpan={7} className="px-5 py-10 text-center text-[13px] text-[#8A9099]">
                      해당 상태의 문서가 없습니다.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
          <div className="list-footer mt-auto flex items-center justify-between border-t border-[#E3E5E8] px-5 py-2.5 text-[12px] text-[#5B616A]">
            <span>{scopeLabel} · 행을 선택하면 검수 화면으로 이동합니다.</span>
            <span className="tabular-nums">
              {`${visible.length === 0 ? 0 : 1}–${visible.length}`} / {visible.length}
            </span>
          </div>
        </section>
      </main>
    </>
  );
}

function FilterTab({ label, count, active, onClick }: { label: string; count: number; active: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`filter-tab flex h-8 items-center gap-1.5 rounded-lg px-3 text-[13px] font-semibold ${
        active ? 'bg-[#2B4FCB] text-white' : 'border border-[#D0D4DA] bg-white text-[#5B616A]'
      }`}
    >
      {label}
      <b className={`tabular-nums font-semibold ${active ? 'text-white/80' : 'text-[#8A9099]'}`}>{count}</b>
    </button>
  );
}

function DocRow({ doc, index, highlighted, onOpen }: { doc: DocumentListItem; index: number; highlighted: boolean; onOpen: () => void }) {
  const openable = isOpenable(doc);
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
      <td className="px-2 py-2 pr-5">
        {disposition ? <DispositionBadge disposition={disposition} compact /> : <span className="text-[#B6BBC4]">-</span>}
      </td>
    </tr>
  );
}
