import type { ConversionsResponse, MappingRecord, SpecChangeLog } from './types';

/**
 * 서버가 없는 화면에서 매핑 사전, 환산표, 규격 변경 이력을 메모리에서 흉내 내는 목업 저장소입니다. MockApi만 씁니다.
 * 응답 모양은 백엔드 PR #12에서 확정된 형식(GET /mappings, GET /mappings/conversions, GET /specs/{id}/change-logs)과 같습니다.
 */
export class LocalOnlyStore {
  private mappings: MappingRecord[] = SEED_MAPPINGS.map((entry) => ({ ...entry }));
  private changeLogs: Array<SpecChangeLog & { spec_id: number }> = SEED_CHANGE_LOGS.map((entry) => ({ ...entry }));
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

  /** 지우면 true, 없는 id면 false (서버는 없는 id에 404 NOT_FOUND) */
  deleteMapping(id: number): boolean {
    const before = this.mappings.length;
    this.mappings = this.mappings.filter((entry) => entry.id !== id);
    return this.mappings.length < before;
  }

  // --- 환산표 (5-2, 조회 전용) ----------------------------------------------

  getConversions(): ConversionsResponse {
    return {
      units: SEED_CONVERSIONS.units.map((entry) => ({ ...entry })),
      oxides: SEED_CONVERSIONS.oxides.map((entry) => ({ ...entry })),
    };
  }

  // --- 규격 변경 이력 (5-1) ------------------------------------------------

  /** 규격 항목 하나의 변경 이력. 서버처럼 오래된 순입니다. */
  listSpecChangeLogs(specId: number): SpecChangeLog[] {
    return this.changeLogs
      .filter((entry) => entry.spec_id === specId)
      .sort((a, b) => a.created_at.localeCompare(b.created_at))
      .map((entry) => ({ before_value: entry.before_value, after_value: entry.after_value, reason: entry.reason, user_name: entry.user_name, created_at: entry.created_at }));
  }

  addSpecChangeLog(specId: number, entry: SpecChangeLog): void {
    this.changeLogs.push({ ...entry, spec_id: specId });
  }
}

const MATERIAL = 'LI2CO3';

function mapping(
  id: number,
  normalizedName: string,
  rawName: string,
  source: MappingRecord['source'],
  createdBy: string | null,
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

// 시안 5-2의 표기와 같은 값입니다. 서버는 초기값(seed)의 등록자를 null로 줍니다. 협력사, 환산 열은 서버에 없습니다.
const SEED_MAPPINGS: MappingRecord[] = [
  mapping(1, '순도', 'Assay', 'seed', null, '2026-03-11'),
  mapping(2, '순도', 'Purity', 'seed', null, '2026-03-11'),
  mapping(3, '순도', 'Li2CO3 (Assay)', 'seed', null, '2026-03-11'),
  mapping(4, '순도', 'Titration excess HCl', 'seed', null, '2026-04-02'),
  mapping(5, '순도', 'Li2CO3 content', 'seed', null, '2026-04-02'),

  mapping(10, 'Na', 'Na', 'seed', null, '2026-03-11'),
  mapping(11, 'Na', 'Sodium', 'seed', null, '2026-03-11'),
  mapping(12, 'Na', 'Na (ppm)', 'seed', null, '2026-04-02'),
  mapping(13, 'Na', 'Na2O', 'seed', null, '2026-06-18'),
  mapping(15, 'Na', '钠', 'manual', '김OO', '2026-10-05'),

  mapping(20, 'K', 'K', 'seed', null, '2026-03-11'),
  mapping(21, 'K', 'Potassium', 'seed', null, '2026-03-11'),
  mapping(22, 'K', 'K (ppm)', 'seed', null, '2026-04-02'),
  mapping(23, 'K', 'K2O', 'seed', null, '2026-06-18'),

  mapping(30, 'Fe', 'Fe', 'seed', null, '2026-03-11'),
  mapping(31, 'Fe', 'Iron', 'seed', null, '2026-03-11'),
  mapping(32, 'Fe', 'Fe (ppm)', 'seed', null, '2026-04-02'),
  mapping(33, 'Fe', 'Fe2O3', 'seed', null, '2026-06-18'),

  mapping(40, 'Ca', 'Ca', 'seed', null, '2026-03-11'),
  mapping(41, 'Ca', 'Calcium', 'seed', null, '2026-03-11'),
  mapping(42, 'Ca', 'CaO', 'seed', null, '2026-06-18'),

  mapping(50, 'Cl', 'Cl', 'seed', null, '2026-03-11'),
  mapping(51, 'Cl', 'Chloride', 'seed', null, '2026-03-11'),
  mapping(52, 'Cl', 'Chloride (Cl)', 'seed', null, '2026-04-02'),
  mapping(53, 'Cl', 'Cl-', 'seed', null, '2026-04-02'),

  mapping(70, '중금속 총량', 'Heavy metals (as Pb)', 'manual', '김OO', '2026-10-05'),

  mapping(60, '황산염', 'Sulfate', 'seed', null, '2026-03-11'),
  mapping(61, '황산염', 'Sulfur compounds (as SO4)', 'seed', null, '2026-04-02'),
  mapping(62, '황산염', 'SO3', 'seed', null, '2026-06-18'),
];

// 환산 계수는 서버 설정값입니다(백엔드 테스트의 값: % → ppm 10000, ppb → ppm 0.001, Na2O → Na 0.7419, Fe2O3 → Fe 0.6994, CaO → Ca 0.7147).
// K2O → K 0.8301은 일반적인 환산 계수로 가정했습니다. 시안 5-2의 SO3 → SO42−는 서버의 산화물 환산이 아니라서 뺐습니다.
const SEED_CONVERSIONS: ConversionsResponse = {
  units: [
    { from: '%', to: 'ppm', factor: 10000 },
    { from: 'ppb', to: 'ppm', factor: 0.001 },
    { from: 'mg/kg', to: 'ppm', factor: 1 },
  ],
  oxides: [
    { oxide: 'Na2O', element: 'Na', factor: 0.7419 },
    { oxide: 'K2O', element: 'K', factor: 0.8301 },
    { oxide: 'Fe2O3', element: 'Fe', factor: 0.6994 },
    { oxide: 'CaO', element: 'Ca', factor: 0.7147 },
  ],
};

// 규격 항목 id는 목업 규격(fixtures의 createSpecs)과 같습니다: K 3, 황산염 7. "최초 등록"은 변경 이력이 아니라 뺐습니다.
const SEED_CHANGE_LOGS: Array<SpecChangeLog & { spec_id: number }> = [
  {
    spec_id: 3,
    before_value: 'usl: 15',
    after_value: 'usl: 10',
    reason: 'Chengxin 납품 협약 개정 반영',
    user_name: '박OO',
    created_at: '2026-09-20T09:12:00+09:00',
  },
  {
    spec_id: 7,
    before_value: 'usl: 500',
    after_value: 'usl: 400',
    reason: '사내 D1 기준 정렬',
    user_name: '박OO',
    created_at: '2026-06-02T15:40:00+09:00',
  },
];
