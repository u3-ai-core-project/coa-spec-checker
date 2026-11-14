import { apiDownload } from '../../api/client'
import { saveFile } from './lib/saveFile'

// 문서 1건의 엑셀 리포트를 받아 저장. 파일명은 서버가 준 이름, 없으면 기본 이름
// pseudonymize=true면 엑셀 속 사람 이름이 "담당자 A, B…"로 바뀌고 파일명 끝에 _가명이 붙음 (외부 공유용)
export async function downloadReport(documentId: string, pseudonymize = false) {
    const query = pseudonymize ? '?pseudonymize=true' : ''
    const { blob, fileName } = await apiDownload(`/documents/${encodeURIComponent(documentId)}/report${query}`)
    saveFile(blob, fileName ?? `${documentId}_report${pseudonymize ? '_가명' : ''}.xlsx`)
}