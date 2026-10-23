import { Chem } from '../../review/shared/components/Chem';
import type { SpecSet } from '../../review/shared/api/types';

interface SpecSetListProps {
  sets: SpecSet[];
  selectedCode: string;
  onSelect(code: string): void;
}

/**
 * 좌측 규격 세트 목록 (시안 5-0의 원자재 목록). [v1.4] 규격은 원자재별 세트(등급, 버전) 단위라 세트마다 한 줄이고,
 * 같은 원자재에 세트가 여럿이면 "기본" 태그로 기본 세트를 구분합니다. 항목 수는 GET /specs/sets의 item_count입니다.
 */
export function SpecSetList({ sets, selectedCode, onSelect }: SpecSetListProps) {
  const countByMaterial = new Map<string, number>();
  for (const entry of sets) countByMaterial.set(entry.material_code, (countByMaterial.get(entry.material_code) ?? 0) + 1);

  return (
    <section className="material-list flex w-[280px] shrink-0 flex-col rounded-xl border border-[#E3E5E8] bg-white">
      <div className="border-b border-[#E3E5E8] px-5 py-4 text-[16px] font-bold">원자재</div>
      <ul className="flex flex-col gap-1 overflow-y-auto p-3">
        {sets.map((entry) => {
          const selected = entry.code === selectedCode;
          const grade = [entry.grade, entry.version].filter(Boolean).join(' · ');
          return (
            <li key={entry.code}>
              <button
                type="button"
                onClick={() => onSelect(entry.code)}
                className={`material-item flex w-full flex-col gap-0.5 rounded-lg border px-3 py-2.5 text-left ${
                  selected ? 'border-[#C9D5F7] bg-[#EAEFFC]' : 'border-transparent'
                }`}
              >
                <span className={`material-name flex items-center gap-1.5 text-[14px] font-semibold ${selected ? 'text-[#2B4FCB]' : 'text-[#1F2328]'}`}>
                  <Chem text={entry.material_name} />
                  {entry.is_default && (countByMaterial.get(entry.material_code) ?? 0) > 1 && (
                    <span className="rounded bg-[#EEF0F3] px-1 text-[10px] font-semibold leading-[14px] text-[#5B616A]">기본</span>
                  )}
                </span>
                {grade && <span className="spec-set-grade text-[12px] tabular-nums text-[#5B616A]">{grade}</span>}
                <span className="text-[12px] text-[#5B616A]">시험 항목 {`${entry.item_count}개`}</span>
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
