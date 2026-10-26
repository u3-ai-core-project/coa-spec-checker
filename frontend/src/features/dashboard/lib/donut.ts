import type { DashboardSummary } from '../types'

export interface DonutSlice {
    name: string
    value: number
    color: string
}

// 합·불 비율: 합격 = 승인 + 조건부 승인, 불합격 = 불합격 (서버 pass_rate와 같은 기준)
export function passFailSlices(d: DashboardSummary): DonutSlice[] {
    return [
        { name: '합격', value: d.accept_count + d.conditional_accept_count, color: '#1a7f4b' },
        { name: '불합격', value: d.reject_count, color: '#c0392b' },
    ]
}

const DEVIATION_COLORS = ['#2b4fcb', '#8ba3ec', '#cfd4da']

// 항목별 이탈 빈도: 부적합 수(fail_count)가 많은 상위 3개, 나머지는 "기타"로 묶음
export function deviationSlices(d: DashboardSummary): DonutSlice[] {
    const items = d.deviation_by_item
        .filter((i) => i.fail_count > 0)
        .sort((a, b) => b.fail_count - a.fail_count)
    const slices: DonutSlice[] = items
        .slice(0, 3)
        .map((i, idx) => ({ name: i.item_name, value: i.fail_count, color: DEVIATION_COLORS[idx] }))
    const rest = items.slice(3).reduce((sum, i) => sum + i.fail_count, 0)
    if (rest > 0) slices.push({ name: '기타', value: rest, color: '#e6e8eb' })
    return slices
}