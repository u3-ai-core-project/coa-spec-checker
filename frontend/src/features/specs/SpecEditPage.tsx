import { useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import {
  DRAFT_ERROR_MESSAGE,
  describeChangeLog,
  type SpecChangeEntry,
  type SpecDraft,
  buildChanges,
  draftErrors,
  draftOf,
} from './lib/specEdit';
import { api } from '../review/shared/api';
import { errorMessage } from '../review/shared/api/errors';
import type { SpecItem } from '../review/shared/api/types';
import { Chem } from '../review/shared/components/Chem';
import { ErrorNotice } from '../review/shared/components/EmptyState';
import { Icon } from '../review/shared/components/Icon';
import { PageIntro } from '../review/shell/PageIntro';
import { useCurrentUser } from '../review/shared/currentUser';
import { formatDateTime } from '../review/shared/domain/format';
import { useAsync } from '../review/shared/hooks/useAsync';

function inputClass(changed: boolean, invalid: boolean, align: string, readOnly = false): string {
  const base = `spec-input h-9 rounded-md px-2.5 text-[13px] tabular-nums ${align}`;
  // 항목명과 규격 근거는 API(PATCH /specs)로 고칠 수 없어 읽기 전용이지만, 시안과 같은 흰 입력창 모양으로 둡니다.
  if (readOnly) return `${base} border border-[#D0D4DA] bg-white`;
  if (invalid) return `${base} border-2 border-[#C0342E] bg-white`;
  if (changed) return `${base} border-2 border-[#2B4FCB] bg-[#F3F6FE]`;
  return `${base} border border-[#D0D4DA] bg-white`;
}

/**
 * 시안 5-1 규격 수정(관리자). 실제 API(PATCH /specs/{id})는 하한, 상한, 단위만 수정할 수 있고,
 * 변경한 규격은 이후 업로드되는 문서부터 적용됩니다(이미 추출된 문서의 판정은 그대로입니다).
 * 백엔드 확정 답변: PATCH /specs/{id}에 변경 사유(reason)가 필수이고, 변경 이력은 GET /specs/{id}/change-logs로 봅니다.
 * 항목 추가·삭제, 규격 근거(source) 수정, 재판정 체크박스는 서버에 없어 화면에서 숨겼습니다.
 */
export function SpecEditPage() {
  const user = useCurrentUser();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  // [v1.4] 규격은 세트 단위입니다. 주소의 ?set=(규격 세트 코드)로 고르고, 없으면 ?material=(원자재)의 첫 세트, 그것도 없으면 첫 세트입니다.
  const setsQuery = useAsync(() => api.listSpecSets(), []);
  const sets = setsQuery.data ?? [];
  const currentSet =
    sets.find((entry) => entry.code === params.get('set')) ?? sets.find((entry) => entry.material_code === params.get('material')) ?? sets[0];
  const specsQuery = useAsync(
    () => (currentSet ? api.listSpecs({ spec_set_code: currentSet.code }) : Promise.resolve([] as SpecItem[])),
    [currentSet?.code],
  );
  // 매핑 사전과 변경 이력은 원자재(material_code) 단위입니다.
  const group = currentSet ? { code: currentSet.material_code, name: currentSet.material_name, items: specsQuery.data ?? [] } : undefined;
  const code = group?.code ?? null;

  const mappings = useAsync(() => (code ? api.listMappings(code) : Promise.resolve([])), [code]);
  // 변경 이력은 항목(규격 id) 단위 API라 세트의 항목마다 받아서 항목 이름을 붙이고 최근 순으로 합칩니다(서버는 오래된 순).
  // TODO(백엔드 협의): 세트 단위로 한 번에 받는 API가 있으면 바꿉니다.
  const specsForLogs = specsQuery.data ?? [];
  const itemIds = specsForLogs.map((spec) => spec.id);
  const changeLogs = useAsync(
    () =>
      Promise.all(
        specsForLogs.map(async (spec): Promise<SpecChangeEntry[]> =>
          (await api.listSpecChangeLogs(spec.id)).map((log) => ({ ...log, spec_id: spec.id, item_name: spec.item_name, unit: spec.unit })),
        ),
      ).then((lists) => lists.flat().sort((a, b) => b.created_at.localeCompare(a.created_at))),
    [itemIds.join(',')],
  );

  // 사용자가 고친 입력값만 보관하고, 고치지 않은 값은 규격 원래 값을 씁니다.
  const [edits, setEdits] = useState<Record<number, Partial<SpecDraft>>>({});
  const [reason, setReason] = useState('');
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  const header = (
    <PageIntro
      title="규격 수정"
      subtitle="변경한 규격은 저장 후 새로 업로드되는 문서부터 적용됩니다."
      breadcrumb={`규격 관리 / ${group ? group.name.split(' ')[0] : ''} / 수정`}
    />
  );

  if ((setsQuery.error ?? specsQuery.error) && !setsQuery.data) {
    return (
      <>
        {header}
        <main className="body flex min-h-0 flex-1 items-center justify-center">
          <ErrorNotice
            message={errorMessage(setsQuery.error ?? specsQuery.error)}
            onRetry={() => {
              setsQuery.reload();
              specsQuery.reload();
            }}
          />
        </main>
      </>
    );
  }
  if (!group) {
    return (
      <>
        {header}
        <main className="body flex min-h-0 flex-1 items-center justify-center">
          <p className="text-[14px] text-[#5B616A]">{setsQuery.data ? '등록된 규격이 없습니다.' : '불러오는 중입니다.'}</p>
        </main>
      </>
    );
  }

  const drafts: Record<number, SpecDraft> = Object.fromEntries(
    group.items.map((spec) => [spec.id, { ...draftOf(spec), ...edits[spec.id] }]),
  );
  const changes = buildChanges(group.items, drafts);
  const errors = draftErrors(group.items, drafts);
  const hasErrors = Object.keys(errors).length > 0;
  const mappingCount = (spec: SpecItem) => (mappings.data ?? []).filter((entry) => entry.normalized_name === spec.item_name).length;
  const canSave = changes.length > 0 && reason.trim().length > 0 && !hasErrors && !saving;
  const pendingTitles = changes.flatMap((change) => change.descriptions);

  function update(spec: SpecItem, patch: Partial<SpecDraft>) {
    setEdits((current) => ({ ...current, [spec.id]: { ...current[spec.id], ...patch } }));
    setSaveError(null);
  }

  async function save() {
    if (!code) return;
    setSaving(true);
    setSaveError(null);
    try {
      for (const change of changes) {
        // 서버가 하한/상한 범위를 다시 검증합니다(400 INVALID_SPEC_RANGE). 변경 사유는 항목마다 같은 값을 보냅니다.
        await api.patchSpec(change.spec.id, { ...change.body, reason: reason.trim() });
      }
      navigate('/specs');
    } catch (failure) {
      setSaveError(errorMessage(failure));
      specsQuery.reload();
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      {header}
      <main className="body flex min-h-0 flex-1 gap-[18px] overflow-hidden">
        <section className="spec-form flex min-w-0 flex-1 flex-col rounded-xl border border-[#E3E5E8] bg-white">
          <div className="spec-form-header flex items-center justify-between border-b border-[#E3E5E8] px-5 py-3.5">
            <h3 className="spec-material text-[16px] font-bold">
              <Chem text={group.name} /> · 규격 편집
              {currentSet?.grade || currentSet?.version ? (
                <span className="ml-2 text-[12px] font-normal text-[#5B616A]">{[currentSet.grade, currentSet.version].filter(Boolean).join(' · ')}</span>
              ) : null}
            </h3>
          </div>
          <div className="spec-apply-notice mx-5 mt-3 flex items-start gap-2 rounded-lg bg-[#EAEFFC] px-3 py-2.5 text-[13px] text-[#2B4FCB]">
            <span className="mt-0.5 shrink-0">
              <Icon name="info" size={16} />
            </span>
            <span>
              <b className="font-semibold">이후 업로드 건부터 적용됩니다.</b> 이미 업로드된 문서의 판정 결과는 기존 규격 그대로 유지됩니다.
            </span>
          </div>
          <div className="spec-table-wrap mt-3 min-h-0 flex-1 overflow-y-auto">
            <table className="spec-table w-full text-left">
              <thead className="bg-[#F9FAFB]">
                <tr className="text-[12px] font-semibold text-[#5B616A]">
                  <th className="px-4 py-2 font-semibold">항목명</th>
                  <th className="px-2 py-2 font-semibold">원문 표기</th>
                  <th className="px-2 py-2 font-semibold">단위</th>
                  <th className="px-2 py-2 font-semibold">LSL</th>
                  <th className="px-2 py-2 font-semibold">USL</th>
                </tr>
              </thead>
              <tbody>
                {group.items.map((spec) => {
                  const draft = drafts[spec.id];
                  const original = draftOf(spec);
                  const changed = changes.some((change) => change.spec.id === spec.id);
                  const error = errors[spec.id];
                  return (
                    <tr key={spec.id} className={`spec-row border-t border-[#E3E5E8]${changed ? ' bg-[#F3F6FE]' : ''}`}>
                      <td className="px-4 py-2">
                        <div className="flex items-center gap-1.5">
                          <input className={`${inputClass(false, false, '', true)} w-[96px]`} value={spec.item_name} readOnly title="항목명은 서버 API로 수정할 수 없습니다." aria-label="항목명" />
                          {changed && (
                            <span className="spec-changed-chip rounded-full bg-[#EAEFFC] px-1.5 py-0.5 text-[10px] font-semibold text-[#2B4FCB]">
                              변경됨
                            </span>
                          )}
                        </div>
                      </td>
                      <td className="px-2 py-2">
                        <Link
                          to={`/specs/mappings?item=${encodeURIComponent(spec.item_name)}`}
                          className="spec-map-link flex h-9 w-[116px] items-center justify-between gap-1 rounded-md border border-dashed border-[#B6BBC4] px-2 text-[12px] font-semibold text-[#2B4FCB]"
                        >
                          표기 {`${mappingCount(spec)}개`}
                          <Icon name="ext" size={12} />
                        </Link>
                      </td>
                      <td className="px-2 py-2">
                        <input
                          className={`${inputClass(draft.unit !== original.unit, error === 'EMPTY_UNIT', '')} w-[62px]`}
                          value={draft.unit}
                          aria-label={`${spec.item_name} 단위`}
                          onChange={(event) => update(spec, { unit: event.target.value })}
                        />
                      </td>
                      <td className="px-2 py-2">
                        <input
                          className={`${inputClass(draft.lsl !== original.lsl, error === 'INVALID_NUMBER' || error === 'INVALID_SPEC_RANGE', 'text-right')} w-[76px]`}
                          value={draft.lsl}
                          inputMode="decimal"
                          aria-label={`${spec.item_name} LSL`}
                          onChange={(event) => update(spec, { lsl: event.target.value })}
                        />
                      </td>
                      <td className="px-2 py-2">
                        <input
                          className={`${inputClass(draft.usl !== original.usl, error === 'INVALID_NUMBER' || error === 'INVALID_SPEC_RANGE', 'text-right')} w-[76px]`}
                          value={draft.usl}
                          inputMode="decimal"
                          aria-label={`${spec.item_name} USL`}
                          onChange={(event) => update(spec, { usl: event.target.value })}
                        />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            {hasErrors && (
              <ul className="spec-errors mx-5 mt-2 flex flex-col gap-0.5 text-[12px] text-[#C0342E]">
                {group.items
                  .filter((spec) => errors[spec.id])
                  .map((spec) => (
                    <li key={spec.id}>
                      {spec.item_name}: {DRAFT_ERROR_MESSAGE[errors[spec.id]]}
                    </li>
                  ))}
              </ul>
            )}
            <div className="flex items-center justify-end px-5 py-3">
              <span className="text-[12px] text-[#8A9099]">원문 표기는 매핑 사전 · 단위 환산표에서 관리합니다.</span>
            </div>
            <div className="spec-reason mx-5 mb-4 flex flex-col gap-1.5">
              <label className="text-[13px] font-semibold" htmlFor="spec-reason">
                변경 사유 <span className="text-[#C0342E]">*</span> <span className="text-[12px] font-normal text-[#8A9099]">필수 입력입니다.</span>
              </label>
              <input
                id="spec-reason"
                className="spec-reason-input h-9 w-full rounded-md border border-[#D0D4DA] bg-white px-3 text-[13px]"
                placeholder="변경 사유를 입력해 주십시오."
                value={reason}
                onChange={(event) => setReason(event.target.value)}
              />
            </div>
          </div>
          <div className="spec-form-actions flex items-center justify-between border-t border-[#E3E5E8] px-5 py-3.5">
            <span className={`spec-change-summary text-[12px] ${saveError ? 'text-[#C0342E]' : 'text-[#5B616A]'}`}>
              {saveError ?? `변경 ${changes.length}건 · 이후 업로드 건부터 적용됩니다.`}
            </span>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => navigate('/specs')}
                className="btn-cancel h-10 rounded-lg border border-[#D0D4DA] bg-white px-5 text-[14px] font-semibold"
              >
                취소
              </button>
              <button
                type="button"
                disabled={!canSave}
                onClick={() => void save()}
                className={`btn-save h-10 rounded-lg px-5 text-[14px] font-semibold ${
                  canSave ? 'bg-[#2B4FCB] text-white' : 'cursor-not-allowed bg-[#E3E5E8] text-[#8A9099]'
                }`}
              >
                저장
              </button>
            </div>
          </div>
        </section>
        <aside className="spec-history flex w-[300px] shrink-0 flex-col rounded-xl border border-[#E3E5E8] bg-white">
          <div className="spec-history-header border-b border-[#E3E5E8] px-5 py-3.5 text-[16px] font-bold">변경 이력</div>
          <ul className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto px-5 py-4">
            {pendingTitles.map((title) => (
              <li key={title} className="history-entry flex gap-3">
                <span className="history-dot mt-1.5 h-2 w-2 shrink-0 rounded-full bg-[#2B4FCB]" />
                <div className="history-body flex flex-col gap-0.5 text-[12px]">
                  <span className="history-title font-semibold tabular-nums">
                    {title} <span className="text-[#2B4FCB]">(저장 대기)</span>
                  </span>
                  <span className="history-meta tabular-nums text-[#5B616A]">{user.name} · 지금</span>
                </div>
              </li>
            ))}
            {(changeLogs.data ?? []).map((entry, index) => (
              <li key={`${entry.spec_id}-${entry.created_at}-${index}`} className="history-entry flex gap-3">
                <span className="history-dot mt-1.5 h-2 w-2 shrink-0 rounded-full bg-[#D0D4DA]" />
                <div className="history-body flex flex-col gap-0.5 text-[12px]">
                  <span className="history-title font-semibold tabular-nums">{`${entry.item_name} ${describeChangeLog(entry, entry.unit)}`}</span>
                  <span className="history-meta tabular-nums text-[#5B616A]">
                    {entry.user_name} · {formatDateTime(entry.created_at)}
                    {entry.reason && (
                      <>
                        <br />
                        사유: {entry.reason}
                      </>
                    )}
                  </span>
                </div>
              </li>
            ))}
          </ul>
        </aside>
      </main>
    </>
  );
}
