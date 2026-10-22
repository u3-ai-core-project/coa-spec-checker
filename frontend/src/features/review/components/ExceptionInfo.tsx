import type { ExtractionItem } from '../shared/api/types';
import { REASON_CODE_LABEL, RESOLUTION_TYPE_LABEL } from '../shared/domain/exceptions';

const SUB = 'col-start-2 col-span-3';

/**
 * [v1.4안] 항목의 예외 사유코드(reason_code)와 해결 조건(resolution). 시안에 없는 줄이라 기본 형태(회색 글자 두 줄)로만 두고,
 * 선택한 항목 아래에서만 보여 줍니다(기본 화면이 시안에서 벗어나지 않게).
 * 서버가 보낸 코드가 이 화면의 이름 목록에 없으면 코드 그대로 보여 줍니다.
 */
export function ExceptionInfo({ item }: { item: Pick<ExtractionItem, 'reason_code' | 'resolution' | 'normalized_name'> }) {
  const { reason_code: code, resolution } = item;
  if (!code && !resolution) return null;
  return (
    <div className={`item-exception ${SUB} flex flex-col gap-0.5 rounded-md bg-[#F4F5F7] px-2 py-1 text-[11px] leading-snug text-[#5B616A]`}>
      {code && (
        <span className="item-reason-code">
          사유 코드: {REASON_CODE_LABEL[code] ?? code} ({code})
        </span>
      )}
      {resolution && (
        <span className="item-resolution">
          해결 조건: {RESOLUTION_TYPE_LABEL[resolution.type] ?? resolution.type}
          {resolution.condition ? ` · ${resolution.condition}` : ''}
          {resolution.target_item && resolution.target_item !== item.normalized_name ? ` (값을 받을 항목: ${resolution.target_item})` : ''}
        </span>
      )}
    </div>
  );
}
