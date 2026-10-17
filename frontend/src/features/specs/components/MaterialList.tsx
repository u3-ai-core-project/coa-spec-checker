import { Chem } from '../../review/shared/components/Chem';
import type { MaterialGroup } from '../lib/specs';

interface MaterialListProps {
  groups: MaterialGroup[];
  selectedCode: string;
  onSelect(code: string): void;
}

/** 좌측 원자재 목록 (시안 5-0). 규격 항목 수는 GET /specs 응답에서 셉니다. */
export function MaterialList({ groups, selectedCode, onSelect }: MaterialListProps) {
  return (
    <section className="material-list flex w-[280px] shrink-0 flex-col rounded-xl border border-[#E3E5E8] bg-white">
      <div className="border-b border-[#E3E5E8] px-5 py-4 text-[16px] font-bold">원자재</div>
      <ul className="flex flex-col gap-1 p-3">
        {groups.map((group) => {
          const selected = group.code === selectedCode;
          return (
            <li key={group.code}>
              <button
                type="button"
                onClick={() => onSelect(group.code)}
                className={`material-item flex w-full flex-col gap-0.5 rounded-lg border px-3 py-2.5 text-left ${
                  selected ? 'border-[#C9D5F7] bg-[#EAEFFC]' : 'border-transparent'
                }`}
              >
                <span className={`material-name text-[14px] font-semibold ${selected ? 'text-[#2B4FCB]' : 'text-[#1F2328]'}`}>
                  <Chem text={group.name} />
                </span>
                <span className="text-[12px] text-[#5B616A]">시험 항목 {`${group.items.length}개`}</span>
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
