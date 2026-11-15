import { useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { SpecTabs } from './components/SpecTabs';
import { SOURCE_LABEL, countByStandard, isNewlyAccumulated } from './lib/mappingDict';
import { api } from '../review/shared/api';
import type { MappingRecord, MappingRecordSource, SpecItem } from '../review/shared/api/types';
import { errorMessage } from '../review/shared/api/errors';
import { Chem } from '../review/shared/components/Chem';
import { ErrorNotice } from '../review/shared/components/EmptyState';
import { Icon } from '../review/shared/components/Icon';
import { PageIntro } from '../review/shell/PageIntro';
import { useCurrentUser } from '../review/shared/currentUser';
import { formatDate } from '../review/shared/domain/format';
import { useAsync } from '../review/shared/hooks/useAsync';

/** 환산 계수 표시. 천 단위 구분(10,000)을 쓰고 소수는 6자리까지 보여 줍니다. */
const formatFactor = (value: number) => value.toLocaleString('en-US', { maximumFractionDigits: 6 });

const SOURCE_STYLE: Record<MappingRecordSource, string> = {
  seed: 'bg-[#EEF0F3] text-[#5B616A]',
  manual: 'bg-[#E1F3F6] text-[#0F6A7B]',
};

function SourceBadge({ source }: { source: MappingRecordSource }) {
  return (
    <span className={`map-src rounded px-1 text-[10px] font-semibold leading-[14px] ${SOURCE_STYLE[source]}`}>
      {SOURCE_LABEL[source]}
    </span>
  );
}

/**
 * 시안 5-2 매핑 사전·단위 환산표(관리자). 백엔드 확정 답변에 따라 원자재별 매핑 사전을 조회하고 삭제만 합니다.
 *   GET /mappings?material_code=, DELETE /mappings/{id}(ADMIN만), GET /mappings/conversions(조회만).
 * 표기 추가, 사전 등록, 환산표 수정은 서버에 없어 화면에서 숨겼습니다. 사전은 material_code + raw_name 기준이라 협력사 열도 없습니다.
 * 응답 형식은 백엔드 PR #12에서 확정되었습니다(types.ts의 MappingRecord, ConversionsResponse).
 * 환산표는 단위 환산(units)과 산화물 → 원소 환산(oxides)을 한 표에 이어서 보여 줍니다.
 */
export function MappingDictPage() {
  const user = useCurrentUser();
  const canDelete = user.role === 'ADMIN';
  const [params, setParams] = useSearchParams();

  // 원자재 선택. 규격 세트 목록에서 원자재(LI2CO3, LIOH 등)를 뽑고, 주소의 ?material=로 고릅니다.
  const setsQuery = useAsync(() => api.listSpecSets(), []);
  const materials = useMemo(() => {
    const seen = new Map<string, string>();
    for (const entry of setsQuery.data ?? []) if (!seen.has(entry.material_code)) seen.set(entry.material_code, entry.material_name);
    return [...seen].map(([code, name]) => ({ code, name }));
  }, [setsQuery.data]);
  const materialParam = params.get('material');
  const material = materials.find((entry) => entry.code === materialParam) ?? materials[0];
  const code = material?.code ?? null;

  // 표준 항목명은 선택한 원자재의 기본 규격 세트(is_default) 항목에서 가져옵니다.
  const defaultSet = useMemo(() => {
    const all = (setsQuery.data ?? []).filter((entry) => entry.material_code === code);
    return all.find((entry) => entry.is_default) ?? all[0];
  }, [setsQuery.data, code]);
  const itemsQuery = useAsync(
    () => (defaultSet ? api.listSpecs({ spec_set_code: defaultSet.code }) : Promise.resolve([] as SpecItem[])),
    [defaultSet?.code],
  );
  const mappings = useAsync(() => (code ? api.listMappings(code) : Promise.resolve([] as MappingRecord[])), [code]);
  const conversions = useAsync(() => api.getConversions(), []);

  const [selectedName, setSelectedName] = useState<string | null>(params.get('item'));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const header = <PageIntro title="규격 관리" subtitle="표준 항목별 협력사 표기와 단위 환산식을 관리합니다." />;

  const loadError = setsQuery.error ?? itemsQuery.error ?? mappings.error;
  if (loadError && !(setsQuery.data && mappings.data)) {
    return (
      <>
        {header}
        <main className="body flex min-h-0 flex-1 items-center justify-center">
          <ErrorNotice
            message={errorMessage(loadError)}
            onRetry={() => {
              setsQuery.reload();
              itemsQuery.reload();
              mappings.reload();
            }}
          />
        </main>
      </>
    );
  }
  if (!material || !itemsQuery.data || !mappings.data) {
    return (
      <>
        {header}
        <main className="body flex min-h-0 flex-1 items-center justify-center">
          <p className="text-[14px] text-[#5B616A]">불러오는 중입니다.</p>
        </main>
      </>
    );
  }

  const entries = mappings.data;
  const counts = countByStandard(entries);
  // 환산표 한 줄: 단위 환산은 "from 값 × factor = to 값", 산화물 환산은 "산화물 값 × factor = 원소 값"입니다.
  const conversionRows = [
    ...(conversions.data?.units ?? []).map((entry) => ({
      key: `unit-${entry.from}-${entry.to}`,
      label: `${entry.from} → ${entry.to}`,
      formula: `1 ${entry.from} = ${formatFactor(entry.factor)} ${entry.to}`,
      factor: `×${formatFactor(entry.factor)}`,
    })),
    ...(conversions.data?.oxides ?? []).map((entry) => ({
      key: `oxide-${entry.oxide}`,
      label: `${entry.oxide} → ${entry.element ?? '-'}`,
      formula: entry.element ? `${entry.element} = ${entry.oxide} × ${formatFactor(entry.factor)}` : `${entry.oxide} × ${formatFactor(entry.factor)}`,
      factor: `×${formatFactor(entry.factor)}`,
    })),
  ];
  // 표준 항목: 규격 항목에 더해, 검수 중 매핑을 고쳐 사전에만 쌓인 항목(예: 중금속 총량)도 보여 줍니다.
  const specNames = itemsQuery.data.map((spec) => spec.item_name);
  const names = [...specNames, ...[...new Set(entries.map((entry) => entry.normalized_name))].filter((name) => !specNames.includes(name))];
  const current = selectedName && names.includes(selectedName) ? selectedName : names[0];
  const rows = entries.filter((entry) => entry.normalized_name === current);

  async function remove(id: number) {
    setBusy(true);
    setError(null);
    try {
      await api.deleteMapping(id);
      mappings.reload();
    } catch (failure) {
      setError(errorMessage(failure));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      {header}
      <main className="body flex min-h-0 flex-1 flex-col gap-3 overflow-hidden">
        <div className="flex items-center justify-between gap-3">
          <SpecTabs active="mappings" />
          {/* 백엔드 확정 답변: 상단 원자재 선택. 시안에 없는 컨트롤이라 기본 형태의 선택 상자로 둡니다. */}
          <label className="material-select flex items-center gap-2 text-[13px] font-semibold">
            원자재
            <select
              className="h-9 rounded-md border border-[#D0D4DA] bg-white px-2.5 text-[13px] font-normal"
              value={material.code}
              onChange={(event) => setParams({ material: event.target.value })}
            >
              {materials.map((entry) => (
                <option key={entry.code} value={entry.code}>
                  {`${entry.name} (${entry.code})`}
                </option>
              ))}
            </select>
          </label>
        </div>
        <div className="flex min-h-0 flex-1 gap-[18px]">
          <section className="std-list flex w-[240px] shrink-0 flex-col rounded-xl border border-[#E3E5E8] bg-white">
            <div className="border-b border-[#E3E5E8] px-5 py-3.5 text-[15px] font-bold">표준 항목</div>
            <ul className="flex min-h-0 flex-col gap-1 overflow-y-auto p-3">
              {names.map((name) => {
                const on = name === current;
                return (
                  <li key={name}>
                    <button
                      type="button"
                      onClick={() => setSelectedName(name)}
                      className={`std-item flex w-full items-center justify-between rounded-lg border px-3 py-2 text-left text-[13px] ${
                        on ? 'border-[#C9D5F7] bg-[#EAEFFC]' : 'border-transparent'
                      }`}
                    >
                      <span className={`flex items-center gap-1.5 font-semibold ${on ? 'text-[#2B4FCB]' : ''}`}>
                        {name}
                        {isNewlyAccumulated(entries, name) && (
                          <span className="rounded bg-[#F0ECFA] px-1 text-[10px] font-semibold text-[#6B4FBB]">신규 누적</span>
                        )}
                      </span>
                      <span className="text-[12px] tabular-nums text-[#8A9099]">{counts[name] ?? 0}</span>
                    </button>
                  </li>
                );
              })}
              {names.length === 0 && <li className="px-3 py-2 text-[12px] text-[#8A9099]">표준 항목이 없습니다.</li>}
            </ul>
          </section>
          <div className="flex min-w-0 flex-1 flex-col gap-[14px]">
            <section className="map-card flex min-h-0 flex-col rounded-xl border border-[#E3E5E8] bg-white">
              <div className="flex items-center justify-between border-b border-[#E3E5E8] px-5 py-3">
                <div className="flex flex-col">
                  <h3 className="text-[15px] font-bold">
                    {current} · 협력사 표기 {`${rows.length}개`}
                  </h3>
                  <span className="text-[12px] text-[#5B616A]">변경 내용은 이후 업로드 건부터 적용됩니다.</span>
                </div>
              </div>
              {error && <p className="px-5 py-2 text-[12px] text-[#C0342E]">{error}</p>}
              <div className="min-h-0 flex-1 overflow-y-auto">
                <table className="map-table w-full text-left">
                  <thead className="bg-[#F9FAFB]">
                    <tr className="text-[12px] font-semibold text-[#5B616A]">
                      <th className="px-5 py-2 font-semibold">표기</th>
                      <th className="px-2 py-2 font-semibold">출처</th>
                      <th className="px-2 py-2 font-semibold">등록자</th>
                      <th className="px-2 py-2 font-semibold">등록일</th>
                      <th className="px-5 py-2" />
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((entry) => (
                      <tr key={entry.id} className="map-row border-t border-[#E3E5E8]">
                        <td className="px-5 py-2 text-[13px] font-semibold">
                          <Chem text={entry.raw_name} />
                        </td>
                        <td className="px-2 py-2">
                          <SourceBadge source={entry.source} />
                        </td>
                        <td className="px-2 py-2 text-[12px] text-[#5B616A]">{entry.created_by ?? '-'}</td>
                        <td className="px-2 py-2 text-[12px] tabular-nums text-[#8A9099]">{formatDate(entry.created_at)}</td>
                        <td className="px-5 py-2 text-right">
                          {canDelete && (
                            <button
                              type="button"
                              disabled={busy}
                              onClick={() => void remove(entry.id)}
                              aria-label={`${entry.raw_name} 삭제`}
                              className="btn-delete-map inline-flex h-[21px] w-[21px] items-center justify-center rounded-md text-[#8A9099] hover:bg-[#F4F5F7]"
                            >
                              <Icon name="trash" size={14} />
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                    {rows.length === 0 && (
                      <tr>
                        <td colSpan={5} className="px-5 py-8 text-center text-[13px] text-[#8A9099]">
                          등록된 표기가 없습니다.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </section>
            <section className="unit-card flex min-h-0 flex-1 flex-col rounded-xl border border-[#E3E5E8] bg-white">
              <div className="flex items-center justify-between border-b border-[#E3E5E8] px-5 py-3">
                <h3 className="text-[15px] font-bold">단위 환산표</h3>
                {/* 환산 계수는 서버 설정값이라(GET /mappings/conversions) 이 화면에서는 조회만 합니다. */}
              </div>
              <div className="min-h-0 flex-1 overflow-y-auto">
                <table className="unit-table w-full text-left">
                  <thead className="bg-[#F9FAFB]">
                    <tr className="text-[12px] font-semibold text-[#5B616A]">
                      <th className="px-5 py-2 font-semibold">변환</th>
                      <th className="px-2 py-2 font-semibold">환산식</th>
                      <th className="px-2 py-2 font-semibold">계수</th>
                    </tr>
                  </thead>
                  <tbody>
                    {conversionRows.map((conversion) => (
                      <tr key={conversion.key} className="unit-row border-t border-[#E3E5E8]">
                        <td className="px-5 py-2 text-[13px] font-semibold">
                          <Chem text={conversion.label} />
                        </td>
                        <td className="px-2 py-2 text-[13px] tabular-nums">
                          <Chem text={conversion.formula} />
                        </td>
                        <td className="px-2 py-2 text-[13px] tabular-nums text-[#5B616A]">{conversion.factor}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          </div>
        </div>
      </main>
    </>
  );
}
