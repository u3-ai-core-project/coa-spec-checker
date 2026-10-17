import type { MappingEntry, SpecHistoryEntry, UnitConversion } from './Api';
import type { ReviewLog } from './types';

/**
 * 백엔드 API가 없는 기능을 메모리에서 흉내 내는 저장소입니다.
 * TODO(백엔드 협의): 수정 사유, 규격 변경 이력, 매핑 사전, 단위 환산표 API가 정해지면 이 파일을 http 구현으로 대체합니다.
 */
export class LocalOnlyStore {
  private itemReasons = new Map<string, string>();
  private specHistory: SpecHistoryEntry[] = SEED_SPEC_HISTORY.map((entry) => ({ ...entry }));
  private mappings: MappingEntry[] = SEED_MAPPINGS.map((entry) => ({ ...entry }));
  private nextId = 1000;

  // --- 항목 수정 사유 ----------------------------------------------------

  saveItemReason(documentId: string, itemId: string, reason: string): void {
    this.itemReasons.set(`${documentId}|${itemId}`, reason);
  }

  /** 항목마다 가장 최근의 수정(edit) 이력에 사유를 붙입니다. */
  attachItemReasons(documentId: string, logs: ReviewLog[]): ReviewLog[] {
    const lastEdit = new Map<string, number>();
    logs.forEach((log, index) => {
      if (log.action === 'edit') lastEdit.set(log.item_id, index);
    });
    return logs.map((log, index) => {
      if (log.action !== 'edit' || lastEdit.get(log.item_id) !== index) return log;
      const reason = this.itemReasons.get(`${documentId}|${log.item_id}`);
      return reason ? { ...log, reason } : log;
    });
  }

  // --- 규격 변경 이력 (5-1) ------------------------------------------------

  listSpecHistory(materialCode: string): SpecHistoryEntry[] {
    return this.specHistory
      .filter((entry) => entry.materialCode === materialCode)
      .sort((a, b) => b.at.localeCompare(a.at));
  }

  addSpecHistory(entry: Omit<SpecHistoryEntry, 'id'>): void {
    this.specHistory.push({ ...entry, id: `sh-${this.nextId++}` });
  }

  // --- 매핑 사전 (5-2) -----------------------------------------------------

  listMappings(materialCode: string): MappingEntry[] {
    return this.mappings.filter((entry) => entry.materialCode === materialCode);
  }

  addMapping(entry: Omit<MappingEntry, 'id'>): MappingEntry {
    const created: MappingEntry = { ...entry, id: `mp-${this.nextId++}` };
    this.mappings.push(created);
    return created;
  }

  registerMapping(id: string, registeredBy: string): void {
    const entry = this.mappings.find((item) => item.id === id);
    if (!entry) return;
    entry.source = 'dictionary';
    entry.registeredBy = registeredBy;
  }

  deleteMapping(id: string): void {
    this.mappings = this.mappings.filter((entry) => entry.id !== id);
  }

  // --- 단위 환산표 (5-2, 조회 전용) ---------------------------------------

  listUnitConversions(): UnitConversion[] {
    return SEED_UNIT_CONVERSIONS.map((entry) => ({ ...entry }));
  }

  /** 시드 사유(시안 2-5와 같은 값)를 넣습니다. 목업 전용입니다. */
  seedItemReason(documentId: string, itemId: string, reason: string): void {
    this.saveItemReason(documentId, itemId, reason);
  }
}

const MATERIAL = 'LI2CO3';

const SEED_SPEC_HISTORY: SpecHistoryEntry[] = [
  {
    id: 'sh-1',
    materialCode: MATERIAL,
    title: 'K USL 15 → 10 ppm',
    by: '박OO',
    at: '2026-09-20T09:12:00+09:00',
    reason: 'Chengxin 납품 협약 개정 반영',
  },
  {
    id: 'sh-2',
    materialCode: MATERIAL,
    title: '황산염 USL 500 → 400 ppm',
    by: '박OO',
    at: '2026-06-02T15:40:00+09:00',
    reason: '사내 D1 기준 정렬',
  },
  {
    id: 'sh-3',
    materialCode: MATERIAL,
    title: '최초 등록',
    by: '이OO',
    at: '2026-03-11T10:05:00+09:00',
    reason: null,
  },
];

function mapping(
  id: string,
  standardName: string,
  rawName: string,
  source: MappingEntry['source'],
  conversion: string | null,
  registeredBy: string,
  registeredAt: string,
  supplier = '공통',
): MappingEntry {
  return { id, materialCode: MATERIAL, standardName, rawName, supplier, source, conversion, registeredBy, registeredAt };
}

const SEED_MAPPINGS: MappingEntry[] = [
  mapping('mp-1', '순도', 'Assay', 'dictionary', null, '박OO', '2026-03-11'),
  mapping('mp-2', '순도', 'Purity', 'dictionary', null, '박OO', '2026-03-11'),
  mapping('mp-3', '순도', 'Li2CO3 (Assay)', 'dictionary', null, '박OO', '2026-03-11'),
  mapping('mp-4', '순도', 'Titration excess HCl', 'dictionary', null, '박OO', '2026-04-02'),
  mapping('mp-5', '순도', 'Li2CO3 content', 'dictionary', null, '박OO', '2026-04-02'),

  mapping('mp-10', 'Na', 'Na', 'dictionary', null, '박OO', '2026-03-11'),
  mapping('mp-11', 'Na', 'Sodium', 'dictionary', null, '박OO', '2026-03-11'),
  mapping('mp-12', 'Na', 'Na (ppm)', 'dictionary', null, '이OO', '2026-04-02', 'Chengxin'),
  mapping('mp-13', 'Na', 'Na2O', 'dictionary', 'Na2O → Na', '박OO', '2026-06-18', 'Chengxin'),
  mapping('mp-14', 'Na', 'Natrium', 'ai', null, 'AI', '2026-09-30', '-'),
  mapping('mp-15', 'Na', '钠', 'manual', null, '김OO', '2026-10-05', 'Chengxin'),

  mapping('mp-20', 'K', 'K', 'dictionary', null, '박OO', '2026-03-11'),
  mapping('mp-21', 'K', 'Potassium', 'dictionary', null, '박OO', '2026-03-11'),
  mapping('mp-22', 'K', 'K (ppm)', 'dictionary', null, '이OO', '2026-04-02'),
  mapping('mp-23', 'K', 'K2O', 'dictionary', 'K2O → K', '박OO', '2026-06-18'),

  mapping('mp-30', 'Fe', 'Fe', 'dictionary', null, '박OO', '2026-03-11'),
  mapping('mp-31', 'Fe', 'Iron', 'dictionary', null, '박OO', '2026-03-11'),
  mapping('mp-32', 'Fe', 'Fe (ppm)', 'dictionary', null, '이OO', '2026-04-02'),
  mapping('mp-33', 'Fe', 'Fe2O3', 'dictionary', 'Fe2O3 → Fe', '박OO', '2026-06-18'),

  mapping('mp-40', 'Ca', 'Ca', 'dictionary', null, '박OO', '2026-03-11'),
  mapping('mp-41', 'Ca', 'Calcium', 'dictionary', null, '박OO', '2026-03-11'),
  mapping('mp-42', 'Ca', 'CaO', 'dictionary', 'CaO → Ca', '박OO', '2026-06-18'),

  mapping('mp-50', 'Cl', 'Cl', 'dictionary', null, '박OO', '2026-03-11'),
  mapping('mp-51', 'Cl', 'Chloride', 'dictionary', null, '박OO', '2026-03-11'),
  mapping('mp-52', 'Cl', 'Chloride (Cl)', 'dictionary', null, '이OO', '2026-04-02'),
  mapping('mp-53', 'Cl', 'Cl-', 'dictionary', null, '이OO', '2026-04-02'),

  mapping('mp-70', '중금속 총량', 'Heavy metals (as Pb)', 'manual', null, '김OO', '2026-10-05', 'Chengxin'),

  mapping('mp-60', '황산염', 'Sulfate', 'dictionary', null, '박OO', '2026-03-11'),
  mapping('mp-61', '황산염', 'Sulfur compounds (as SO4)', 'dictionary', null, '박OO', '2026-04-02'),
  mapping('mp-62', '황산염', 'SO3', 'dictionary', 'SO3 → SO42−', '박OO', '2026-06-18'),
];

const SEED_UNIT_CONVERSIONS: UnitConversion[] = [
  { id: 'uc-1', label: '% → ppm', formula: '1 % = 10,000 ppm', factor: '×10,000' },
  { id: 'uc-2', label: 'ppb → ppm', formula: '1,000 ppb = 1 ppm', factor: '÷1,000' },
  { id: 'uc-3', label: 'mg/kg → ppm', formula: '1 mg/kg = 1 ppm', factor: '×1' },
  { id: 'uc-4', label: 'Na2O → Na', formula: 'Na = Na2O × 0.7419', factor: '×0.7419' },
  { id: 'uc-5', label: 'K2O → K', formula: 'K = K2O × 0.8301', factor: '×0.8301' },
  { id: 'uc-6', label: 'SO3 → SO42−', formula: 'SO42− = SO3 × 1.1999', factor: '×1.1999' },
];
