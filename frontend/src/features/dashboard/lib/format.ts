export function formatPercent(value: number): string {
    return `${value.toFixed(1)}%`
}

// 서버는 초 단위 숫자를 줌. 화면 표기는 시안 기준: 200초 -> "3분 20초", 45초 -> "45초"
// 처분 완료 0건이면 서버가 0을 주므로 "0초"로 보임

export function formatDuration(totalSec: number): string {
    const sec = Math.round(totalSec)
    if (sec <= 0) return '0초'
    const h = Math.floor(sec / 3600)
    const m = Math.floor((sec % 3600) / 60)
    const s = sec % 60
    const parts: string[] = []
    if (h) parts.push(`${h}시간`)
    if (m) parts.push(`${m}분`)
    if (s && !h) parts.push(`${s}초`)
    return parts.join(' ')
}