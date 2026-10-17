import type { HistoryEntry } from '../lib/history';

/** 승인 이력 카드 (시안 2-5, 2-6). 값 수정·확인, 보류, 처분, 승인 취소 이력을 최근 순으로 보여 줍니다. */
export function HistoryCard({ entries }: { entries: HistoryEntry[] }) {
  return (
    <div className="history-card shrink-0 overflow-hidden rounded-xl border border-[#E3E5E8] bg-white">
      <div className="flex items-center justify-between px-5 py-2 text-[13px] font-bold">
        승인 이력
        <span className="text-[11px] font-normal text-[#8A9099]">값 수정 · 확인 기록을 포함합니다.</span>
      </div>
      <div className="max-h-[200px] overflow-y-auto">
        <table className="approval-history w-full text-left text-[12px]">
          <tbody>
            {entries.map((entry) => (
              <tr key={entry.key} className="history-row border-t border-[#E3E5E8]">
                <td className="whitespace-nowrap px-5 py-[3px] tabular-nums text-[#5B616A]">{entry.when}</td>
                <td className="whitespace-nowrap px-2 py-[3px] font-semibold" style={{ color: entry.color }}>
                  {entry.kind}
                </td>
                <td className="whitespace-nowrap px-2 py-[3px]">{entry.who}</td>
                <td className="px-2 py-[3px] pr-5 text-[#5B616A]">{entry.detail}</td>
              </tr>
            ))}
            {entries.length === 0 && (
              <tr className="border-t border-[#E3E5E8]">
                <td className="px-5 py-3 text-[#8A9099]">기록된 이력이 없습니다.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
