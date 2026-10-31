import { apiDownload } from '../../api/client'
import { saveFile } from './lib/saveFile'

// 문서 1건의 엑셀 리포트를 받아 저장. 파일명은 서버가 준 이름, 없으면 기본 이름
export async function downloadReport(documentId: string) {
    const { blob, fileName } = await apiDownload(`/documents/${encodeURIComponent(documentId)}/report`)
    saveFile(blob, fileName ?? `${documentId}_report.xlsx`)
}