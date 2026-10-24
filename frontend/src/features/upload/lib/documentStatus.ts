import type { DocumentStatus, FinalDecision } from '../types'

export const STATUS_LABEL: Record<DocumentStatus, string> = { queued: '대기', processing: '처리 중', extracted: '검수하기', in_review: '검수 중', on_hold: '보류', approved: '처리 완료', failed: '오류', }

export const DECISION_LABEL: Record<FinalDecision, string> = { accept: '승인', conditional_accept: '조건부 승인', reject: '불합격', }

// 더 이상 바뀌지 않는 상태 -> 이때 처리 상태 확인을 멈춤
const SETTLED: DocumentStatus[] = ['extracted', 'in_review', 'on_hold', 'approved', 'failed']
export const isSettled = (status: DocumentStatus) => SETTLED.includes(status)