import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import type { DocumentDetail } from '../shared/api/types';
import { StatusBadge } from '../shared/components/badges';
import { REVIEW_PATH } from '../shared/domain/constants';
import { failureInfo } from '../shared/domain/failure';

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="failed-doc-row grid grid-cols-[88px_1fr] items-start gap-x-3 text-[13px]">
      <span className="text-[12px] leading-5 text-[#8A9099]">{label}</span>
      <span className="font-semibold leading-5">{children}</span>
    </div>
  );
}

/**
 * 처리에 실패한 문서(status failed)를 열었을 때 검수 화면 대신 보이는 안내. 추출 결과가 없어 항목은 없고,
 * 서버가 알려 준 실패 단계(failed_stage)와 종류(error_kind)에 따른 안내, 오류 내용, 처리 시도 횟수를 보여 줍니다.
 * 이 화면에는 다시 처리하는 버튼이 없습니다(재처리는 업로드 화면의 기존 버튼).
 */
export function FailedDocumentPanel({ doc }: { doc: DocumentDetail }) {
  const info = failureInfo(doc);
  const transient = doc.error_kind === 'transient';
  return (
    <section className="failed-doc flex w-full max-w-[560px] flex-col gap-3.5 rounded-xl border border-[#E3E5E8] bg-white p-6" aria-label="처리 실패 문서">
      <div className="flex items-center gap-2">
        <StatusBadge status={doc.status} />
        <span className="failed-doc-name truncate text-[14px] font-semibold tabular-nums">{doc.file_name}</span>
      </div>
      <h3 className="text-[16px] font-bold">처리에 실패한 문서입니다</h3>
      {info?.stage && <Row label="실패 단계">{info.stage}</Row>}
      {info?.guide && (
        <p
          className={`failed-doc-guide rounded-lg border px-3 py-2 text-[13px] font-semibold ${
            transient ? 'border-[#2B4FCB]/30 bg-[#EAEFFC] text-[#2B4FCB]' : 'border-[#C0342E]/30 bg-[#FBEAE9] text-[#C0342E]'
          }`}
        >
          {info.guide}
        </p>
      )}
      {doc.error_message && <Row label="오류 내용">{doc.error_message}</Row>}
      {doc.attempt_count != null && (
        <Row label="처리 시도">
          <span className="tabular-nums">{doc.attempt_count}회</span>
        </Row>
      )}
      <Link to={REVIEW_PATH} className="failed-doc-back text-[13px] font-semibold text-[#2B4FCB]">
        검수 목록으로 돌아가기
      </Link>
    </section>
  );
}
