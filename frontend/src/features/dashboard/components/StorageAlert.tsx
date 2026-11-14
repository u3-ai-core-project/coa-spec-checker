import { useEffect, useState } from 'react'
import { apiFetch } from '../../../api/client'

//ADMIN 전용: 저장 공간 단계와 정리 후보
interface Candidate {
    kind: string
    action: 'auto_delete' | 'manual_delete' | 'archive'
    count: number
    bytes: number
}

interface AdminStorage {
    level: 'ok' | 'warn' | 'block'
    reason?: 'quota' | 'disk' | null
    used_percent: number
    candidates?: Candidate[]
}

const ACTION_LABEL: Record<Candidate['action'], string> = {
    auto_delete: '자동 정리 대상',
    manual_delete: '사유를 넣어 삭제할 수 있는 문서',
    archive: '보관용 폴더로 옮길 수 있는 문서',
}

const mb = (bytes: number) => `${(bytes / 1024 / 1024).toFixed(1)}MB`

export default function StorageAlert() {
    const [data, setData] = useState<AdminStorage | null>(null)

    useEffect(() => {
        let alive = true
        apiFetch<AdminStorage>('/admin/storage')
            .then((d) => { if (alive) setData(d) })
            .catch(() => { /* 옛 서버이거나 실패하면 경고만 생략한다 */ })
        return () => { alive = false }
    }, [])

    if (!data || data.level === 'ok') return null

    const block = data.level === 'block'
    const candidates = (data.candidates ?? []).filter((c) => c.count > 0)

    return (
        <div
            role="status"
            className={`rounded-xl border p-4 text-sm [word-break:keep-all] ${block ? 'border-[#ffccc7] bg-[#FFF1F0] text-[#c0392b]' : 'border-[#ffe58f] bg-[#FFF8E6] text-[#9a6700]'}`}
        >
            <p className="font-bold">
                {block
                    ? data.reason === 'disk'
                        ? '서버 디스크의 남은 공간이 부족해 새 업로드가 막혀 있습니다.'
                        : `저장 공간이 ${Math.round(data.used_percent)}%까지 차서 새 업로드가 막혀 있습니다.`
                    : `저장 공간이 ${Math.round(data.used_percent)}% 찼습니다. 정리가 필요합니다.`}
            </p>
            {candidates.length > 0 && (
                <ul className="mt-2 list-disc pl-5 text-xs text-ink-sub">
                    {candidates.map((c) => (
                        <li key={`${c.kind}-${c.action}`}>
                            {ACTION_LABEL[c.action]} {c.count}건 ({mb(c.bytes)})
                        </li>
                    ))}
                </ul>
            )}
        </div>
    )
}