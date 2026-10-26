import type { Role } from '../../types/auth'

export interface DeviationItem {
    item_name: string
    fail_count: number
    undetermined_count: number
}

export interface DashboardSummary {
    total_processed: number
    accept_count: number
    conditional_accept_count: number
    reject_count: number
    on_hold_count: number
    pass_rate: number
    avg_processing_time_sec: number
    recommendation_match_rate: number
    deviation_by_item: DeviationItem[]
    auto_approve_rate?: number
    reviewed_item_ratio?: number
    reason_code_counts?: Record<string, number>
}

// scope는 보내지 않음. 서버가 USER는 본인(mine), ADMIN은 전체(all)로 정함.
export interface DashboardQuery {
    userId?: number // ADMIN만 사용 가능. USER가 보내면 403
    materialCode?: string
    from?: string // YYYY-MM-DD
    to?: string // YYYY-MM-DD (포함)
}

// GET /users 응답 (ADMIN 전용)
export interface UserOption {
    id: number
    name: string
    role: Role
}