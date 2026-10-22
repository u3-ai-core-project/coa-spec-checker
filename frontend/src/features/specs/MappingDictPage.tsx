import { useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { SpecTabs } from './components/SpecTabs';
import { SOURCE_LABEL, countByStandard, isNewlyAccumulated, validateNewRawName } from './lib/mappingDict';
import { groupByMaterial } from './lib/specs';
import { api } from '../review/shared/api';
import type { MappingEntry, MappingEntrySource } from '../review/shared/api/Api';
import { errorMessage } from '../review/shared/api/errors';
import { Chem } from '../review/shared/components/Chem';
import { ErrorNotice } from '../review/shared/components/EmptyState';
import { Icon } from '../review/shared/components/Icon';
import { PageIntro } from '../review/shell/PageIntro';
import { useCurrentUser } from '../review/shared/currentUser';
import { useAsync } from '../review/shared/hooks/useAsync';

const SOURCE_STYLE: Record<MappingEntrySource, string> = {
  dictionary: 'bg-[#EEF0F3] text-[#5B616A]',
  ai: 'bg-[#F0ECFA] text-[#6B4FBB]',
  manual: 'bg-[#E1F3F6] text-[#0F6A7B]',
};

function SourceBadge({ source }: { source: MappingEntrySource }) {
  return (
    <span className={`map-src rounded px-1 text-[10px] font-semibold leading-[14px] ${SOURCE_STYLE[source]}`}>
      {SOURCE_LABEL[source]}
    </span>
  );
}

const today = () => new Date().toISOString().slice(0, 10);

/**
 * 시안 5-2 매핑 사전·단위 환산표(관리자). 표준 항목별 협력사 표기를 조회, 등록, 삭제합니다.
 * TODO(백엔드 협의): 매핑 사전 조회·등록·삭제 API가 없어 목업입니다. 매핑 사전은 협력사별이 아니라
 * material_code + raw_name 기준이므로 협력사 열은 두지 않았습니다.
 * 단위 환산표의 환산 계수는 서버 설정값이라 이 화면에서는 조회만 하고 수정 기능을 만들지 않습니다.
 */
export function MappingDictPage() {
  const user = useCurrentUser();
  const [params] = useSearchParams();
  const specs = useAsync(() => api.listSpecs(), []);
  // [v1.4안] 매핑 사전은 material_code별입니다. 주소의 ?material=LIOH처럼 원자재를 고르고, 없으면 첫 원자재입니다.
  // TODO(디자인 협의): 원자재를 바꾸는 선택 UI는 시안에 없어 만들지 않았습니다.
  const materialParam = params.get('material');
  const group = useMemo(() => {
    const groups = groupByMaterial(specs.data ?? []);
    return groups.find((entry) => entry.code === materialParam) ?? groups[0];
  }, [specs.data, materialParam]);
  const code = group?.code ?? null;

  const mappings = useAsync(() => (code ? api.listMappings(code) : Promise.resolve([])), [code]);
  const conversions = useAsync(() => api.listUnitConversions(), []);

  const [selectedName, setSelectedName] = useState<string | null>(params.get('item'));
  const [adding, setAdding] = useState(false);
  const [newName, setNewName] = useState('');
  const [newSupplier, setNewSupplier] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const header = (
    <PageIntro title="규격 관리" subtitle="표준 항목별 협력사 표기와 단위 환산식을 관리합니다." />
  );

  if ((specs.error && !specs.data) || (mappings.error && !mappings.data)) {
    return (
      <>
        {header}
        <main className="body flex min-h-0 flex-1 items-center justify-center">
          <ErrorNotice message={errorMessage(specs.error ?? mappings.error)} onRetry={() => { specs.reload(); mappings.reload(); }} />
        </main>
      </>
    );
  }
  if (!group || !mappings.data) {
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
  // 표준 항목: 규격 항목에 더해, 검수 중 매핑을 고쳐 사전에만 쌓인 항목(예: 중금속 총량)도 보여 줍니다.
  const specNames = group.items.map((spec) => spec.item_name);
  const names = [...specNames, ...[...new Set(entries.map((entry) => entry.standardName))].filter((name) => !specNames.includes(name))];
  const current = selectedName && names.includes(selectedName) ? selectedName : names[0];
  const rows = entries.filter((entry) => entry.standardName === current);

  async function run(action: () => Promise<void>) {
    setBusy(true);
    setError(null);
    try {
      await action();
      mappings.reload();
    } catch (failure) {
      setError(errorMessage(failure));
    } finally {
      setBusy(false);
    }
  }

  const addEntry = () =>
    run(async () => {
      const problem = validateNewRawName(entries, newName);
      if (problem) {
        throw new Error(problem);
      }
      await api.addMapping({
        materialCode: group.code,
        standardName: current,
        rawName: newName.trim(),
        supplier: newSupplier.trim() || '공통',
        source: 'dictionary',
        conversion: null,
        registeredBy: user.name,
        registeredAt: today(),
      });
      setNewName('');
      setNewSupplier('');
      setAdding(false);
    }).catch(() => undefined);

  const newNameProblem = adding ? validateNewRawName(entries, newName) : null;

  return (
    <>
      {header}
      <main className="body flex min-h-0 flex-1 flex-col gap-3 overflow-hidden">
        <SpecTabs active="mappings" />
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
                      onClick={() => {
                        setSelectedName(name);
                        setAdding(false);
                      }}
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
                <button
                  type="button"
                  onClick={() => setAdding((value) => !value)}
                  className="btn-add-map flex h-8 items-center gap-1.5 rounded-md border border-[#D0D4DA] bg-white px-3 text-[12px] font-semibold"
                >
                  <Icon name="plus" size={14} />
                  표기 추가
                </button>
              </div>
              {adding && (
                <div className="map-add flex items-center gap-2 border-b border-[#E3E5E8] bg-[#F3F6FE] px-5 py-2.5">
                  <input
                    className="h-8 w-[130px] rounded-md border border-[#D0D4DA] bg-white px-2.5 text-[13px]"
                    placeholder="협력사(비우면 공통)"
                    value={newSupplier}
                    aria-label="협력사"
                    onChange={(event) => setNewSupplier(event.target.value)}
                  />
                  <input
                    className="h-8 w-[260px] rounded-md border-2 border-[#2B4FCB] bg-white px-2.5 text-[13px]"
                    placeholder="협력사가 CoA에 적은 표기를 입력합니다."
                    value={newName}
                    autoFocus
                    aria-label="새 표기"
                    onChange={(event) => setNewName(event.target.value)}
                    onKeyDown={(event) => {
                      if (event.key === 'Enter' && !newNameProblem) void addEntry();
                    }}
                  />
                  <button
                    type="button"
                    disabled={busy || newNameProblem !== null}
                    onClick={() => void addEntry()}
                    className={`h-8 rounded-md px-3 text-[12px] font-semibold ${
                      busy || newNameProblem !== null ? 'cursor-not-allowed bg-[#E3E5E8] text-[#8A9099]' : 'bg-[#2B4FCB] text-white'
                    }`}
                  >
                    등록
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setAdding(false);
                      setNewName('');
                    }}
                    className="h-8 rounded-md border border-[#D0D4DA] bg-white px-3 text-[12px] font-semibold"
                  >
                    취소
                  </button>
                  {newNameProblem === 'DUPLICATE' && <span className="text-[12px] text-[#C0342E]">이미 등록된 표기입니다.</span>}
                </div>
              )}
              {error && <p className="px-5 py-2 text-[12px] text-[#C0342E]">{error}</p>}
              <div className="min-h-0 flex-1 overflow-y-auto">
                <table className="map-table w-full text-left">
                  <thead className="bg-[#F9FAFB]">
                    <tr className="text-[12px] font-semibold text-[#5B616A]">
                      <th className="px-5 py-2 font-semibold">표기</th>
                      <th className="px-2 py-2 font-semibold">협력사</th>
                      <th className="px-2 py-2 font-semibold">출처</th>
                      <th className="px-2 py-2 font-semibold">환산</th>
                      <th className="px-2 py-2 font-semibold">등록</th>
                      <th className="px-5 py-2" />
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((entry) => (
                      <MappingRow
                        key={entry.id}
                        entry={entry}
                        busy={busy}
                        onRegister={() => void run(() => api.registerMapping(entry.id, user.name))}
                        onDelete={() => void run(() => api.deleteMapping(entry.id))}
                      />
                    ))}
                    {rows.length === 0 && (
                      <tr>
                        <td colSpan={6} className="px-5 py-8 text-center text-[13px] text-[#8A9099]">
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
                {/* 환산 계수는 서버 설정값이라(명세 2.2) 이 화면에서는 조회만 합니다. 환산식 추가 기능은 없습니다. */}
              </div>
              <div className="min-h-0 flex-1 overflow-y-auto">
                <table className="unit-table w-full text-left">
                  <thead className="bg-[#F9FAFB]">
                    <tr className="text-[12px] font-semibold text-[#5B616A]">
                      <th className="px-5 py-2 font-semibold">변환</th>
                      <th className="px-2 py-2 font-semibold">환산식</th>
                      <th className="px-2 py-2 font-semibold">계수</th>
                      <th className="px-5 py-2" />
                    </tr>
                  </thead>
                  <tbody>
                    {(conversions.data ?? []).map((conversion) => (
                      <tr key={conversion.id} className="unit-row border-t border-[#E3E5E8]">
                        <td className="px-5 py-2 text-[13px] font-semibold">
                          <Chem text={conversion.label} />
                        </td>
                        <td className="px-2 py-2 text-[13px] tabular-nums">
                          <Chem text={conversion.formula} />
                        </td>
                        <td className="px-2 py-2 text-[13px] tabular-nums text-[#5B616A]">{conversion.factor}</td>
                        <td className="px-5 py-2 text-right text-[#8A9099]" title="환산 계수는 서버 설정값이라 수정할 수 없습니다.">
                          <Icon name="pencil" size={14} />
                        </td>
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

function MappingRow({
  entry,
  busy,
  onRegister,
  onDelete,
}: {
  entry: MappingEntry;
  busy: boolean;
  onRegister(): void;
  onDelete(): void;
}) {
  return (
    <tr className="map-row border-t border-[#E3E5E8]">
      <td className="px-5 py-2 text-[13px] font-semibold">
        <Chem text={entry.rawName} />
      </td>
      <td className="px-2 py-2 text-[12px] text-[#5B616A]">{entry.supplier}</td>
      <td className="px-2 py-2">
        <SourceBadge source={entry.source} />
      </td>
      <td className="px-2 py-2 text-[12px] tabular-nums text-[#5B616A]">{entry.conversion ? <Chem text={entry.conversion} /> : '-'}</td>
      <td className="px-2 py-2 text-[12px] tabular-nums text-[#8A9099]">
        {entry.registeredBy} · {entry.registeredAt}
      </td>
      <td className="px-5 py-2 text-right">
        {entry.source === 'ai' ? (
          <button
            type="button"
            disabled={busy}
            onClick={onRegister}
            className="h-6 rounded-md border border-[#6B4FBB]/40 bg-white px-2 text-[11px] font-semibold text-[#6B4FBB]"
          >
            사전 등록
          </button>
        ) : (
          <button
            type="button"
            disabled={busy}
            onClick={onDelete}
            aria-label={`${entry.rawName} 삭제`}
            className="inline-flex h-[21px] w-[21px] items-center justify-center rounded-md text-[#8A9099] hover:bg-[#F4F5F7]"
          >
            <Icon name="trash" size={14} />
          </button>
        )}
      </td>
    </tr>
  );
}
