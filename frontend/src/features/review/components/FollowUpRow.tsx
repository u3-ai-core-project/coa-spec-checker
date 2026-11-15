import type { ExtractionItem, HoldFollowUp } from '../shared/api/types';

const SUB = 'col-start-2 col-span-3';

/** 시안 2-8의 두 버튼. 실측값 요청과 자체 시험 요청은 보류의 후속 조치(follow_up)에 대응합니다. */
const OPTIONS: Array<{ label: string; followUp: HoldFollowUp }> = [
  { label: '실측값 요청', followUp: 'request_actual_value' },
  { label: '자체 시험 요청', followUp: 'internal_test' },
];

interface FollowUpRowProps {
  item: Pick<ExtractionItem, 'judgement'>;
  onRequest(followUp: HoldFollowUp): void;
}

/**
 * 판정 불가·누락 항목에 펼쳐지는 후속 조치 줄.
 * 판정 불가는 협력사에 실측값을 요청하고, 누락은 자체 시험 또는 추가 데이터를 요청합니다(명세 2.4).
 * 버튼을 누르면 보류 다이얼로그가 해당 후속 조치가 선택된 채 열립니다.
 */
export function FollowUpRow({ item, onRequest }: FollowUpRowProps) {
  const color = item.judgement === 'missing' ? '#5B616A' : '#6B4FBB';
  return (
    <div className={`item-followup ${SUB} flex items-center gap-2 text-[12px]`}>
      <span className="font-semibold" style={{ color }}>
        후속 조치
      </span>
      {OPTIONS.map((option) => (
        <button
          key={option.followUp}
          type="button"
          onClick={(event) => {
            event.stopPropagation();
            onRequest(option.followUp);
          }}
          className="btn-request h-7 rounded-md border border-[#D0D4DA] bg-white px-2.5 text-[12px] font-semibold text-[#1F2328]"
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}
