export const MAX_FILES = 20 // 서버 일괄 접수 한도(MAX_BATCH_FILES).
export const MAX_FILE_BYTES = 20 * 1024 * 1024 // 최대 20MB
export const ALLOWED_EXTENSIONS = ['pdf', 'png', 'jpg']
export const CSV_EXTENSION = 'csv'

// 지금은 탄산리튬만 진행
export const MATERIALS = [
    { code: 'LI2CO3', name: '탄산리튬', formula: 'Li₂CO₃', enabled: true },
    { code: 'LIOH', name: '수산화리튬', formula: 'LiOH', enabled: true },
]

// 임시 목록. 협력사 목록을 주는 API가 아직 없음
export const SUPPLIERS = ['Chengxin', '서진소재', '대흥리튬']