import { DOCUMENT_ISSUE_LABEL } from '../../review/shared/domain/exceptions'
import type { BatchQueueItem, ItemSummary } from '../batchTypes'

const ISSUE_LABEL = DOCUMENT_ISSUE_LABEL as Record<string, string>

// 항목 판정 요약을 "부적합 1건 · 판정 불가 2건". 해당하는 것이 없으면 빈 글자
export function summaryText(s: ItemSummary | null): string {
    if (!s) return ''
    const parts: string[] = []
    if (s.fail) parts.push(`부적합 ${s.fail}건`)
    if (s.undetermined) parts.push(`판정 불가 ${s.undetermined}건`)
    if (s.missing) parts.push(`누락 ${s.missing}건`)
    if (s.check) parts.push(`확인 필요 ${s.check}건`)
    return parts.join(' · ')
}

// 우선순위 큐의 "사유" 칸에 보일 문장
export function queueReason(item: BatchQueueItem): string {
    if (item.status === 'queued') return 'AI 분석 전'
    if (item.status === 'processing') return 'AI 분석 중'
    if (item.status === 'failed') return item.error_message ?? '문서 처리 오류'
    // 서류 불일치는 사유코드의 한글 이름을 쓰고, 로트 불일치면 두 로트번호를 붙인다
    if (item.document_issues.length > 0) {
        const labels = item.document_issues.map((code) => ISSUE_LABEL[code] ?? code).join(' · ')
        const lots =
            item.document_issues.includes('LOT_MISMATCH') && item.received_lot_no && item.lot_no
                ? ` (입고 ${item.received_lot_no} ≠ CoA ${item.lot_no})`
                : ''
        return labels + lots
    }
    return summaryText(item.summary) || '-'
}