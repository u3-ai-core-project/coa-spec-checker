import type { ReissueStatus } from '../shared/api/types';
import { Icon } from '../shared/components/Icon';

interface ReissueBannerProps {
  status: ReissueStatus;
  onCompare(): void;
}

/** 재발행 충돌 상태별 안내 문구(백엔드 #61 reissue_status). none은 배너가 없습니다. */
const TEXT: Record<Exclude<ReissueStatus, 'none'>, { text: string; tone: 'warn' | 'info' }> = {
  conflict: { text: '같은 로트의 CoA가 여러 개입니다. 기준 버전을 선택해야 처분할 수 있습니다.', tone: 'warn' },
  review_needed: { text: '이미 처분된 로트에 재발행본이 들어왔습니다. 기존 처분은 바뀌지 않았습니다. 재검토가 필요합니다.', tone: 'warn' },
  resolved: { text: '기준 버전이 선택되었습니다. 기준 버전 문서만 처분할 수 있습니다.', tone: 'info' },
};

/**
 * 검수 상세 위쪽의 재발행 충돌 배너. 상태는 서버(문서 상세의 reissue_status)가 정한 그대로 문구만 바꿔 보여 주고,
 * "버전 비교"로 같은 로트의 CoA 목록을 열어 기준 버전을 고릅니다.
 */
export function ReissueBanner({ status, onCompare }: ReissueBannerProps) {
  if (status === 'none') return null;
  const { text, tone } = TEXT[status];
  const palette =
    tone === 'warn' ? 'border-[#F0C987] bg-[#FFF7E6] text-[#8A5A00]' : 'border-[#D6DEF7] bg-[#F3F6FE] text-[#2B4FCB]';
  return (
    <div role="status" className={`reissue-banner reissue-banner-${status} mx-5 mt-2 flex items-start gap-2 rounded-lg border px-3 py-2 text-[12px] font-semibold leading-snug ${palette}`}>
      <span className="mt-px shrink-0">
        <Icon name={tone === 'warn' ? 'flag' : 'info'} size={14} />
      </span>
      <span className="reissue-banner-text min-w-0 flex-1">{text}</span>
      <button
        type="button"
        onClick={onCompare}
        className="btn-reissue-compare h-7 shrink-0 rounded-md border border-current bg-white px-2.5 text-[12px] font-semibold"
      >
        버전 비교
      </button>
    </div>
  );
}
