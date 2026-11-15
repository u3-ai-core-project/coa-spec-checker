import { ALLOWED_EXTENSIONS, CSV_EXTENSION } from './upload'

const extOf = (f: File) => f.name.split('.').pop()?.toLowerCase() ?? ''

// 한 번에 고른 파일을 CoA(pdf/png/jpg), 입고 정보 CSV, 지원하지 않는 형식으로 나눈다
export function splitSelection(files: File[]) {
    const coa: File[] = []
    const csv: File[] = []
    const other: File[] = []
    for (const f of files) {
        const e = extOf(f)
        if (e === CSV_EXTENSION) csv.push(f)
        else if (ALLOWED_EXTENSIONS.includes(e)) coa.push(f)
        else other.push(f)
    }
    return { coa, csv, other }
}