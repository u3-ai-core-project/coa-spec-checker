const STAGE_LABEL: Record<string, string> = {
    extract: '추출 단계',
    judge: '판정 단계',
    timeout: '처리 시간 초과',
    interrupted: '서버 중단',
}

const KIND_LABEL: Record<string, string> = {
    transient: '일시 오류(재처리 가능)',
    permanent: '영구 오류(재처리해도 동일)',
}

export function failureHint(stage?: string | null, kind?: string | null, attempts?: number): string | null {
    const parts: string[] = []
    if (stage && STAGE_LABEL[stage]) parts.push(STAGE_LABEL[stage])
    if (kind && KIND_LABEL[kind]) parts.push(KIND_LABEL[kind])
    if (attempts !== undefined && attempts >= 2) parts.push('자동 재시도 후 실패')
    return parts.length > 0 ? parts.join(' · ') : null
}