import type { DuplicateInfo } from '../types'

// ApiError.data 안에서 기존 문서 목록(duplicates)을 꺼냄. 모양이 다르면 빈 목록
export function parseDuplicates(data: unknown): DuplicateInfo[] {
    const list = (data as { duplicates?: unknown } | null)?.duplicates
    return Array.isArray(list) ? (list as DuplicateInfo[]) : []
}