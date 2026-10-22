import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { MaterialList } from './components/MaterialList';
import { SpecTabs } from './components/SpecTabs';
import { formatLimit, groupByMaterial, latestUpdate } from './lib/specs';
import { api } from '../review/shared/api';
import { errorMessage } from '../review/shared/api/errors';
import { Chem } from '../review/shared/components/Chem';
import { ErrorNotice } from '../review/shared/components/EmptyState';
import { Icon } from '../review/shared/components/Icon';
import { PageIntro } from '../review/shell/PageIntro';
import { useCurrentUser } from '../review/shared/currentUser';
import { formatDate } from '../review/shared/domain/format';
import { useAsync } from '../review/shared/hooks/useAsync';

/**
 * 시안 5-0 규격 조회. 사용자와 관리자 모두 볼 수 있고, 관리자에게만 규격 수정 진입과 매핑 사전 탭이 보입니다.
 * 규격 항목과 값은 확정 전이라 하드코딩하지 않고 GET /specs 응답으로만 그립니다.
 */
export function SpecsPage() {
  const user = useCurrentUser();
  const isAdmin = user.role === 'ADMIN';
  const { data, error, reload } = useAsync(() => api.listSpecs(), []);
  const groups = useMemo(() => groupByMaterial(data ?? []), [data]);
  const [selected, setSelected] = useState<string | null>(null);
  const current = groups.find((group) => group.code === selected) ?? groups[0];

  const header = (
    <PageIntro title="규격 관리" subtitle="원자재별 시험 항목의 단위와 규격 한계(LSL/USL)를 조회합니다." />
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
  if (!current) {
    return (
      <>
        {header}
        <main className="body flex min-h-0 flex-1 items-center justify-center">
          <p className="text-[14px] text-[#5B616A]">{data ? '등록된 규격이 없습니다.' : '불러오는 중입니다.'}</p>
        </main>
      </>
    );
  }

  const updated = latestUpdate(current.items);
  // [v1.4안] 규격 버전. 한 원자재 안에서 항목마다 다르면 모두 보여 줍니다.
  const versions = [...new Set(current.items.map((item) => item.version).filter((version): version is string => version !== null && version !== undefined))];

  return (
    <>
      {header}
      <main className="body flex min-h-0 flex-1 flex-col gap-3 overflow-hidden">
        {isAdmin && <SpecTabs active="specs" />}
        <div className="flex min-h-0 flex-1 gap-[18px]">
          <MaterialList groups={groups} selectedCode={current.code} onSelect={setSelected} />
          <section className="spec-detail flex min-w-0 flex-1 flex-col rounded-xl border border-[#E3E5E8] bg-white">
            <div className="spec-detail-header flex items-center justify-between border-b border-[#E3E5E8] px-5 py-4">
              <div className="flex flex-col gap-0.5">
                <h3 className="spec-material text-[16px] font-bold">
                  <Chem text={current.name} />
                </h3>
                <span className="text-[12px] tabular-nums text-[#5B616A]">
                  시험 항목 {`${current.items.length}개`}
                  {versions.length > 0 ? ` · 규격 버전 ${versions.join(', ')}` : ''}
                  {updated ? ` · 최종 수정 ${formatDate(updated.at)}${updated.by ? ` · ${updated.by}` : ''}` : ''}
                </span>
              </div>
              {isAdmin && (
                <Link
                  to={`/specs/edit?material=${encodeURIComponent(current.code)}`}
                  className="btn-edit-spec flex h-9 items-center gap-1.5 rounded-lg bg-[#2B4FCB] px-4 text-[13px] font-semibold text-white"
                >
                  <Icon name="pencil" size={14} />
                  규격 수정
                </Link>
              )}
            </div>
            {!isAdmin && (
              <div className="spec-readonly-notice mx-5 mt-4 flex items-center gap-2 rounded-lg bg-[#F4F5F7] px-3 py-2.5 text-[13px] text-[#5B616A]">
                <Icon name="lock" size={14} />
                조회 전용입니다. 규격 변경은 관리자에게 요청해 주십시오.
              </div>
            )}
            <div className="spec-table-wrap mt-4 min-h-0 flex-1 overflow-y-auto">
              <table className="spec-table w-full text-left">
                <thead className="bg-[#F9FAFB]">
                  <tr className="text-[12px] font-semibold text-[#5B616A]">
                    <th className="px-5 py-2.5 font-semibold">항목명</th>
                    <th className="px-3 py-2.5 font-semibold">단위</th>
                    <th className="px-3 py-2.5 text-right font-semibold">LSL (하한)</th>
                    <th className="px-3 py-2.5 text-right font-semibold">USL (상한)</th>
                    <th className="px-5 py-2.5 font-semibold">규격 근거</th>
                    <th className="px-5 py-2.5 text-right font-semibold">최종 수정</th>
                  </tr>
                </thead>
                <tbody>
                  {current.items.map((item) => (
                    <tr key={item.id} className="spec-row border-t border-[#E3E5E8]">
                      <td className="px-5 py-3 text-[14px] font-semibold">
                        {item.item_name}
                        {/* [v1.4안] 필수가 아닌 시험 항목만 "선택"으로 표시합니다. */}
                        {item.is_required === false && (
                          <span className="spec-optional ml-1.5 rounded bg-[#EEF0F3] px-1 text-[10px] font-semibold leading-[14px] text-[#5B616A]">선택</span>
                        )}
                      </td>
                      <td className="px-3 py-3 text-[13px] tabular-nums text-[#5B616A]">{item.unit}</td>
                      <td className="px-3 py-3 text-right text-[14px] font-semibold tabular-nums">{formatLimit(item.lsl)}</td>
                      <td className="px-3 py-3 text-right text-[14px] font-semibold tabular-nums">{formatLimit(item.usl)}</td>
                      <td className="spec-basis px-5 py-3 text-[13px] text-[#1F2328]">{item.source ?? '-'}</td>
                      <td className="px-5 py-3 text-right text-[12px] tabular-nums text-[#8A9099]">{formatDate(item.updated_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="spec-legend border-t border-[#E3E5E8] px-5 py-3 text-[12px] text-[#8A9099]">
              LSL은 규격 하한, USL은 규격 상한입니다. “-”는 해당 한계가 없음을 의미합니다.
            </div>
          </section>
        </div>
      </main>
    </>
  );
}
