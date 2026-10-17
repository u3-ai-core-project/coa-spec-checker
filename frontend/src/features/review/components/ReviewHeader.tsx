import { Link } from 'react-router-dom';
import type { DocumentDetail, Role } from '../shared/api/types';
import { Chem } from '../shared/components/Chem';
import { Icon } from '../shared/components/Icon';
import { RoleBadge } from '../shared/components/badges';

export interface QueuePosition {
  /** 0부터 시작하는 현재 위치 */
  index: number;
  total: number;
  prevId: string | null;
  nextId: string | null;
}

interface ReviewHeaderProps {
  doc: DocumentDetail;
  role: Role;
  /** 검수 대기 목록(extracted, in_review, on_hold) 안에서의 위치. 목록에 없는 문서(처분 완료 등)는 null입니다. */
  queue: QueuePosition | null;
  onMove(documentId: string): void;
}

const Sep = () => <span className="text-[#D0D4DA]">|</span>;

/** 검수 화면 헤더. 이전/다음 이동은 검수 대기 목록 순서 기준이고, 완료된 문서는 페이저 대신 "목록으로"만 둡니다. */
export function ReviewHeader({ doc, role, queue, onMove }: ReviewHeaderProps) {
  return (
    <header className="header flex h-[72px] shrink-0 items-center justify-between border-b border-[#E3E5E8] bg-white px-6">
      <div className="header-title flex flex-col gap-0.5">
        <Link to="/review" className="header-back flex items-center gap-0.5 text-[11px] font-semibold text-[#2B4FCB]">
          <Icon name="back" size={12} />
          검수 목록
        </Link>
        <span className="header-docname text-[14px] font-semibold tabular-nums">{doc.file_name}</span>
        <div className="header-meta flex items-center gap-2.5 text-[12px] text-[#5B616A]">
          <span>
            협력사 <b className="font-semibold text-[#1F2328]">{doc.supplier}</b>
          </span>
          <Sep />
          <span>
            품목{' '}
            <b className="font-semibold text-[#1F2328]">
              <Chem text={doc.material_name ?? doc.material_code} />
            </b>
          </span>
          <Sep />
          <span>
            발주번호 <b className="font-semibold text-[#1F2328] tabular-nums">{doc.po_no ?? '-'}</b>
          </span>
          <Sep />
          <span>
            Lot <b className="font-semibold text-[#1F2328] tabular-nums">{doc.lot_no ?? '-'}</b>
          </span>
        </div>
      </div>
      <div className="header-right flex items-center gap-4">
        <RoleBadge role={role} />
        {queue ? (
          <div className="header-pager flex items-center gap-2">
            <button
              type="button"
              aria-label="이전 문서"
              onClick={() => queue.prevId && onMove(queue.prevId)}
              className="btn-prev flex h-8 w-8 items-center justify-center rounded-md border border-[#D0D4DA] bg-white text-[#5B616A]"
            >
              <Icon name="chev_l" />
            </button>
            <span className="pager-progress w-[56px] text-center text-[13px] font-semibold tabular-nums">
              {queue.index + 1} / {queue.total}
            </span>
            <button
              type="button"
              aria-label="다음 문서"
              onClick={() => queue.nextId && onMove(queue.nextId)}
              className="btn-next flex h-8 w-8 items-center justify-center rounded-md border border-[#D0D4DA] bg-white text-[#5B616A]"
            >
              <Icon name="chev_r" />
            </button>
          </div>
        ) : (
          <Link
            to="/review"
            className="header-to-list flex h-8 items-center gap-1 rounded-md border border-[#D0D4DA] bg-white px-3 text-[13px] font-semibold leading-4 text-[#1F2328]"
          >
            <Icon name="back" size={14} />
            목록으로
          </Link>
        )}
      </div>
    </header>
  );
}
