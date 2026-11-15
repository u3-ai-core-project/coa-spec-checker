import { useState } from 'react';
import { api } from '../shared/api';
import type { DocumentDetail, SpecSet } from '../shared/api/types';
import { specSetName, specSetOptionLabel, visibleSpecSets } from '../shared/domain/specSets';
import { useAsync } from '../shared/hooks/useAsync';
import { RejudgeDialog } from './RejudgeDialog';

interface SpecSetSelectProps {
  doc: DocumentDetail;
  /** 다른 작업(값 수정, 확인 등)이 진행 중이라 잠시 바꿀 수 없을 때 */
  locked?: boolean;
  /** 서버가 다시 판정을 마쳤을 때(새 결과를 불러올 차례) */
  onDone(): void;
  /** 서버가 처분 완료 등으로 거절해 화면 상태가 서버와 다를 때(다시 불러오기) */
  onStale(): void;
}

/** 이 문서의 원자재 규격 세트만 고릅니다. 서버가 세트 목록을 원자재로 거르지만, 다른 원자재의 세트가 섞여 오면 한 번 더 거릅니다. */
function setsOfMaterial(sets: SpecSet[], materialCode: string): SpecSet[] {
  return sets.filter((set) => set.material_code === materialCode);
}

/**
 * 문서 정보의 "적용 규격" 드롭다운. 보이는 세트와 이름은 shared/domain/specSets.ts의 이름 맵을 따릅니다(표시만 바꾸고 서버 코드와 요청 값은 그대로).
 * 현재 적용 중인 세트(문서 상세의 spec_set_code)가 선택돼 있고,
 * 다른 세트를 고르면 다이얼로그가 서버 미리보기(이전 → 이후)를 보여 주고, 처분 전 문서는 사유를 적어 적용합니다
 * (화면에서 판정을 다시 계산하지 않습니다). 처분 완료 문서도 드롭다운은 열려 있고 미리보기만 됩니다(적용은 다이얼로그에서 비활성).
 */
export function SpecSetSelect({ doc, locked = false, onDone, onStale }: SpecSetSelectProps) {
  const setsQuery = useAsync(() => api.listSpecSets(doc.material_code), [doc.material_code]);
  /** 확인 다이얼로그에서 확정을 기다리는 세트 */
  const [target, setTarget] = useState<SpecSet | null>(null);

  const sets = visibleSpecSets(setsOfMaterial(setsQuery.data ?? [], doc.material_code), doc.material_code, doc.spec_set_code);
  const current = sets.find((set) => set.code === doc.spec_set_code) ?? null;

  const disabledReason = setsQuery.error && !setsQuery.data ? '규격 세트 목록을 불러오지 못했습니다.' : null;
  const disabled = disabledReason !== null || locked || setsQuery.data === null;

  function change(code: string) {
    const next = sets.find((set) => set.code === code);
    if (next && next.code !== doc.spec_set_code) setTarget(next);
  }

  return (
    <>
      <span title={disabledReason ?? undefined} className="spec-set-select block">
        <select
          aria-label="적용 규격"
          value={doc.spec_set_code ?? ''}
          disabled={disabled}
          title={disabledReason ?? undefined}
          onChange={(event) => change(event.target.value)}
          className={`spec-set-select-input h-7 w-full max-w-full rounded-md border border-[#D0D4DA] px-2 text-[13px] font-semibold ${
            disabled ? 'cursor-not-allowed bg-[#F3F4F6] text-[#8A9099]' : 'bg-white text-[#1F2328]'
          }`}
        >
          {/* 문서에 규격 세트 정보가 없거나 서버 목록에 없는 세트이면, 지금 값을 그대로 보여 줍니다. */}
          {!current && (
            <option value={doc.spec_set_code ?? ''} disabled>
              {specSetName(doc.spec_set_code) ?? doc.spec_set_code ?? '지정되지 않음'}
            </option>
          )}
          {sets.map((set) => (
            <option key={set.code} value={set.code} title={[set.version, set.description].filter(Boolean).join(' · ')}>
              {specSetOptionLabel(set)}
            </option>
          ))}
        </select>
      </span>
      {target && (
        <RejudgeDialog
          doc={doc}
          target={target}
          onClose={() => setTarget(null)}
          onDone={() => {
            setTarget(null);
            onDone();
          }}
          onStale={onStale}
        />
      )}
    </>
  );
}
