import type { MappingRecord, SpecChangeLog, UnitConversion } from './types';

/**
 * 서버가 아직 구현하지 않은 기능(매핑 사전, 단위 환산표, 규격 변경 이력)을 메모리에서 흉내 내는 목업 저장소입니다.
 * MockApi만 씁니다. 서버가 구현되면(GET /mappings, DELETE /mappings/{id}, GET /mappings/conversions, GET /specs/{id}/change-logs)
 * HttpApi가 서버를 직접 부르고, 이 저장소의 응답 모양(types.ts의 MappingRecord, SpecChangeLog, UnitConversion)을 서버에 맞춥니다.
 * TODO(백엔드 협의): 응답 필드 이름은 가정입니다.
 */
export class LocalOnlyStore {
  private mappings: MappingRecord[] = SEED_MAPPINGS.map((entry) => ({ ...entry }));
  private changeLogs: SpecChangeLog[] = SEED_CHANGE_LOGS.map((entry) => ({ ...entry, before: { ...entry.before }, after: { ...entry.after } }));
  private nextId = 1000;

  // --- 매핑 사전 (5-2) -----------------------------------------------------

  listMappings(materialCode: string): MappingRecord[] {
    return this.mappings.filter((entry) => entry.material_code === materialCode).map((entry) => ({ ...entry }));
  }

  /** 검수 중 항목명을 고치면 서버가 manual로 누적하는 것을 흉내 냅니다. 화면에서 직접 추가하는 기능은 없습니다. */
  addMapping(entry: Omit<MappingRecord, 'id'>): MappingRecord {
    const created: MappingRecord = { ...entry, id: this.nextId++ };
    this.mappings.push(created);
    return created;
  }

  deleteMapping(id: number): void {
    this.mappings = this.mappings.filter((entry) => entry.id !== id);
  }

  // --- 단위 환산표 (5-2, 조회 전용) ---------------------------------------

  listUnitConversions(): UnitConversion[] {
    return SEED_UNIT_CONVERSIONS.map((entry) => ({ ...entry }));
  }

  // --- 규격 변경 이력 (5-1) ------------------------------------------------

  /** 규격 항목 하나의 변경 이력. 최근 것이 먼저 옵니다. */
  listSpecChangeLogs(specId: number): SpecChangeLog[] {
    return this.changeLogs
      .filter((entry) => entry.spec_id === specId)
      .sort((a, b) => b.changed_at.localeCompare(a.changed_at))
      .map((entry) => ({ ...entry, before: { ...entry.before }, after: { ...entry.after } }));
  }

  addSpecChangeLog(entry: Omit<SpecChangeLog, 'id'>): void {
    this.changeLogs.push({ ...entry, id: this.nextId++ });
  }
}

const MATERIAL = 'LI2CO3';

function mapping(
  id: number,
  normalizedName: string,
  rawName: string,
  source: MappingRecord['source'],
  createdBy: string,
  date: string,
): MappingRecord {
  return {
    id,
    material_code: MATERIAL,
    raw_name: rawName,
    normalized_name: normalizedName,
    source,
    created_by: createdBy,
    created_at: `${date}T09:00:00+09:00`,
  };
}

// 시안 5-2의 표기와 같은 값입니다. 사전(seed)과 담당자 수정(manual)만 있고, 협력사, 환산 열은 서버에 없어 뺐습니다.
const SEED_MAPPINGS: MappingRecord[] = [
  mapping(1, '순도', 'Assay', 'seed', '박OO', '2026-03-11'),
  mapping(2, '순도', 'Purity', 'seed', '박OO', '2026-03-11'),
  mapping(3, '순도', 'Li2CO3 (Assay)', 'seed', '박OO', '2026-03-11'),
  mapping(4, '순도', 'Titration excess HCl', 'seed', '박OO', '2026-04-02'),
  mapping(5, '순도', 'Li2CO3 content', 'seed', '박OO', '2026-04-02'),

  mapping(10, 'Na', 'Na', 'seed', '박OO', '2026-03-11'),
  mapping(11, 'Na', 'Sodium', 'seed', '박OO', '2026-03-11'),
  mapping(12, 'Na', 'Na (ppm)', 'seed', '이OO', '2026-04-02'),
  mapping(13, 'Na', 'Na2O', 'seed', '박OO', '2026-06-18'),
  mapping(15, 'Na', '钠', 'manual', '김OO', '2026-10-05'),

  mapping(20, 'K', 'K', 'seed', '박OO', '2026-03-11'),
  mapping(21, 'K', 'Potassium', 'seed', '박OO', '2026-03-11'),
  mapping(22, 'K', 'K (ppm)', 'seed', '이OO', '2026-04-02'),
  mapping(23, 'K', 'K2O', 'seed', '박OO', '2026-06-18'),

  mapping(30, 'Fe', 'Fe', 'seed', '박OO', '2026-03-11'),
  mapping(31, 'Fe', 'Iron', 'seed', '박OO', '2026-03-11'),
  mapping(32, 'Fe', 'Fe (ppm)', 'seed', '이OO', '2026-04-02'),
  mapping(33, 'Fe', 'Fe2O3', 'seed', '박OO', '2026-06-18'),

  mapping(40, 'Ca', 'Ca', 'seed', '박OO', '2026-03-11'),
  mapping(41, 'Ca', 'Calcium', 'seed', '박OO', '2026-03-11'),
  mapping(42, 'Ca', 'CaO', 'seed', '박OO', '2026-06-18'),

  mapping(50, 'Cl', 'Cl', 'seed', '박OO', '2026-03-11'),
  mapping(51, 'Cl', 'Chloride', 'seed', '박OO', '2026-03-11'),
  mapping(52, 'Cl', 'Chloride (Cl)', 'seed', '이OO', '2026-04-02'),
  mapping(53, 'Cl', 'Cl-', 'seed', '이OO', '2026-04-02'),

  mapping(70, '중금속 총량', 'Heavy metals (as Pb)', 'manual', '김OO', '2026-10-05'),

  mapping(60, '황산염', 'Sulfate', 'seed', '박OO', '2026-03-11'),
  mapping(61, '황산염', 'Sulfur compounds (as SO4)', 'seed', '박OO', '2026-04-02'),
  mapping(62, '황산염', 'SO3', 'seed', '박OO', '2026-06-18'),
];

const SEED_UNIT_CONVERSIONS: UnitConversion[] = [
  { id: 'uc-1', label: '% → ppm', formula: '1 % = 10,000 ppm', factor: '×10,000' },
  { id: 'uc-2', label: 'ppb → ppm', formula: '1,000 ppb = 1 ppm', factor: '÷1,000' },
  { id: 'uc-3', label: 'mg/kg → ppm', formula: '1 mg/kg = 1 ppm', factor: '×1' },
  { id: 'uc-4', label: 'Na2O → Na', formula: 'Na = Na2O × 0.7419', factor: '×0.7419' },
  { id: 'uc-5', label: 'K2O → K', formula: 'K = K2O × 0.8301', factor: '×0.8301' },
  { id: 'uc-6', label: 'SO3 → SO42−', formula: 'SO42− = SO3 × 1.1999', factor: '×1.1999' },
];

// 규격 항목 id는 목업 규격(fixtures의 createSpecs)과 같습니다: K 3, 황산염 7. "최초 등록"은 변경 이력이 아니라 뺐습니다.
const SEED_CHANGE_LOGS: SpecChangeLog[] = [
  {
    id: 1,
    spec_id: 3,
    item_name: 'K',
    before: { lsl: null, usl: 15, unit: 'ppm' },
    after: { lsl: null, usl: 10, unit: 'ppm' },
    changed_by: '박OO',
    reason: 'Chengxin 납품 협약 개정 반영',
    changed_at: '2026-09-20T09:12:00+09:00',
  },
  {
    id: 2,
    spec_id: 7,
    item_name: '황산염',
    before: { lsl: null, usl: 500, unit: 'ppm' },
    after: { lsl: null, usl: 400, unit: 'ppm' },
    changed_by: '박OO',
    reason: '사내 D1 기준 정렬',
    changed_at: '2026-06-02T15:40:00+09:00',
  },
];
