import { DEFAULT_MATERIAL_CODE } from '../../domain/constants';
import type {
  Anomaly,
  ApprovalLog,
  DocumentDetail,
  DocumentIssue,
  DocumentStatus,
  ExtractionItem,
  ExtractionResult,
  FinalDecision,
  MappingSource,
  ReviewLog,
  Role,
  SpecItem,
  SpecSet,
  ValueQualifier,
} from '../types';
import { type PdfDocInput, type PdfRow, resultBbox } from './mockPdf';
import { evaluateItem, recommendLot, summarize } from './serverRules';

export interface MockUser {
  id: number;
  username: string;
  password: string;
  name: string;
  role: Role;
}

export interface MockDoc {
  detail: DocumentDetail;
  uploaderId: number;
  extraction: ExtractionResult | null;
  reviewLogs: ReviewLog[];
  approvalLogs: ApprovalLog[];
  anomalies: Anomaly[];
  pdf: PdfDocInput | null;
  fileSize: number;
  /** 시안 비교용 문서입니다. 검수 목록에는 나오지 않고 주소로만 열 수 있습니다. */
  hidden?: boolean;
}

export interface MockState {
  users: MockUser[];
  /** 규격 세트(등급, 버전). specs의 spec_set_code가 가리킵니다. item_count는 조회할 때 항목 수로 채웁니다. */
  specSets: Array<Omit<SpecSet, 'item_count'>>;
  specs: SpecItem[];
  docs: MockDoc[];
}

// 개발용 시드 계정입니다. 비밀번호는 아이디와 같습니다(목업 전용).
export const MOCK_USERS: MockUser[] = [
  { id: 1, username: 'admin', password: 'admin', name: '박OO', role: 'ADMIN' },
  { id: 2, username: 'user', password: 'user', name: '김OO', role: 'USER' },
  { id: 3, username: 'user2', password: 'user2', name: '이OO', role: 'USER' },
];

const MATERIAL_NAME = '탄산리튬 Li2CO3';
const D1 = 'YS/T 582-2023 D1';
const AGREEMENT = 'Chengxin 납품 협약';
/** [v1.4] 규격 버전과 세트. 탄산리튬 초기 세트는 YS/T 582-2023 D1 기반입니다(백엔드 seeds/spec_sets.csv와 같은 코드). */
const VERSION = 'YS/T 582-2023';
export const LI2CO3_SET_CODE = 'LI2CO3-D1-2023';

const LIOH_MATERIAL_CODE = 'LIOH';
const LIOH_MATERIAL_NAME = '수산화리튬 LiOH';
/** 목업의 LIOH 세트 코드는 임의 값입니다. 백엔드 시드의 LIOH 세트 코드는 LIOH-BG-V1이라 서로 다릅니다. */
const LIOH_SET_CODE = 'LIOH-D1-2020';

function spec(
  id: number,
  itemName: string,
  unit: string,
  lsl: number | null,
  usl: number | null,
  source: string,
  updatedAt: string,
  updatedBy: string,
): SpecItem {
  return {
    id,
    material_code: DEFAULT_MATERIAL_CODE,
    material_name: MATERIAL_NAME,
    item_name: itemName,
    unit,
    lsl,
    usl,
    spec_type: '정량',
    grade: 'D1',
    spec_set_code: LI2CO3_SET_CODE,
    version: VERSION,
    is_required: true,
    source,
    updated_by: updatedBy,
    updated_at: updatedAt,
  };
}

/**
 * [v1.4] 수산화리튬(LIOH, 보조 원자재) 규격 자리표시. 항목 이름과 단위만 두고 하한/상한은 비웠습니다.
 * 한계값이 정해지지 않은 항목은 화면에 "-"로 보입니다.
 */
function liohSpec(id: number, itemName: string, unit: string): SpecItem {
  return {
    id,
    material_code: LIOH_MATERIAL_CODE,
    material_name: LIOH_MATERIAL_NAME,
    item_name: itemName,
    unit,
    lsl: null,
    usl: null,
    spec_type: '정량',
    grade: 'D1',
    spec_set_code: LIOH_SET_CODE,
    version: 'GB/T 26008-2020',
    is_required: true,
    source: 'GB/T 26008-2020 D1 (규격표 수령 전 자리표시)',
    updated_by: null,
    updated_at: null,
  };
}

/** 규격 세트 목록(GET /specs/sets 응답의 item_count를 뺀 부분). 기본 세트가 원자재마다 하나씩입니다. */
export function createSpecSets(): MockState['specSets'] {
  return [
    {
      code: LI2CO3_SET_CODE,
      material_code: DEFAULT_MATERIAL_CODE,
      material_name: '탄산리튬',
      grade: 'D1',
      version: VERSION,
      source: D1,
      description: null,
      is_default: true,
    },
    {
      code: LIOH_SET_CODE,
      material_code: LIOH_MATERIAL_CODE,
      material_name: '수산화리튬',
      grade: 'D1',
      version: 'GB/T 26008-2020',
      source: 'GB/T 26008-2020 D1 (규격표 수령 전 자리표시)',
      description: '규격표 수령 전 자리표시. 항목 이름과 단위만 있고 한계값은 비어 있습니다.',
      is_default: true,
    },
  ];
}

/**
 * 개발용 시나리오 'sets'. 탄산리튬에 세트가 둘 이상일 때의 화면을 보려고 D1 항목을 복사한 D3 세트를 더합니다.
 * 한계값은 D1과 같고, 염화물(Cl) 상한만 8 ppm으로 낮춰 검수 화면에서 적용 규격을 바꿔 다시 판정하면 결과가 달라지게 했습니다.
 */
export function createExtraLi2co3Set(specs: SpecItem[]): { set: MockState['specSets'][number]; items: SpecItem[] } {
  const code = 'LI2CO3-D3-2023';
  const base = specs.filter((entry) => entry.spec_set_code === LI2CO3_SET_CODE);
  const firstId = Math.max(...specs.map((entry) => entry.id)) + 1;
  return {
    set: {
      code,
      material_code: DEFAULT_MATERIAL_CODE,
      material_name: '탄산리튬',
      grade: 'D3',
      version: VERSION,
      source: 'YS/T 582-2023 D3 (목업 시험용 복사본)',
      description: '목업 시험용. D1 항목을 복사했고 염화물(Cl) 상한만 8 ppm으로 낮췄습니다.',
      is_default: false,
    },
    items: base.map((entry, index) => ({
      ...entry,
      id: firstId + index,
      spec_set_code: code,
      grade: 'D3',
      source: 'YS/T 582-2023 D3 (목업 시험용 복사본)',
      usl: entry.item_name === 'Cl' ? 8 : entry.usl,
    })),
  };
}

/**
 * 개발용 시나리오 'sets'. 서버 시드(LI2CO3-D1-STRICT, LI2CO3-D1-RELAXED)처럼 D1을 복사해 한도를 바꾼 비교용 세트입니다.
 * 한도는 목업 값이고 실제 서버 값과 같지 않습니다. 강화는 순도 하한과 염화물 상한을, 완화는 칼슘과 나트륨 상한을 바꿔
 * 검수 화면에서 기본·강화·완화를 바꿔 보면 판정이 달라지게 했습니다.
 */
export function createCompareLi2co3Set(specs: SpecItem[], variant: 'STRICT' | 'RELAXED'): { set: MockState['specSets'][number]; items: SpecItem[] } {
  const code = `LI2CO3-D1-${variant}`;
  const strict = variant === 'STRICT';
  const grade = strict ? 'D1-엄격' : 'D1-완화';
  const label = strict ? '한도 강화' : '한도 완화';
  const base = specs.filter((entry) => entry.spec_set_code === LI2CO3_SET_CODE);
  const firstId = Math.max(...specs.map((entry) => entry.id)) + 1;
  const limitOf = (entry: SpecItem): Pick<SpecItem, 'lsl' | 'usl'> => {
    if (strict && entry.item_name === '순도') return { lsl: 99.7, usl: entry.usl };
    if (strict && entry.item_name === 'Cl') return { lsl: entry.lsl, usl: 8 };
    if (!strict && entry.item_name === 'Ca') return { lsl: entry.lsl, usl: 150 };
    if (!strict && entry.item_name === 'Na') return { lsl: entry.lsl, usl: 100 };
    return { lsl: entry.lsl, usl: entry.usl };
  };
  return {
    set: {
      code,
      material_code: DEFAULT_MATERIAL_CODE,
      material_name: '탄산리튬',
      grade,
      version: VERSION,
      source: `D1 세트 복사 후 ${label} (목업 시험용)`,
      description: `목업 시험용 비교 기준. D1 항목을 복사하고 일부 ${label}했습니다. 규격 원문이 아닙니다.`,
      is_default: false,
    },
    items: base.map((entry, index) => ({ ...entry, ...limitOf(entry), id: firstId + index, spec_set_code: code, grade, source: `D1 세트 복사 후 ${label} (목업 시험용)` })),
  };
}

// 규격 항목은 명세 4.20 응답 형태 그대로입니다. 항목과 값은 확정 전이라 이 목업 한 곳에서만 정의합니다.
export function createSpecs(): SpecItem[] {
  return [
    spec(1, '순도', '%', 99.5, null, D1, '2026-03-11T10:05:00+09:00', '이OO'),
    spec(2, 'Na', 'ppm', null, 50, D1, '2026-03-11T10:05:00+09:00', '이OO'),
    spec(3, 'K', 'ppm', null, 10, AGREEMENT, '2026-09-20T09:12:00+09:00', '박OO'),
    spec(4, 'Fe', 'ppm', null, 5, D1, '2026-03-11T10:05:00+09:00', '이OO'),
    spec(5, 'Ca', 'ppm', null, 20, D1, '2026-03-11T10:05:00+09:00', '이OO'),
    spec(6, 'Cl', 'ppm', null, 20, D1, '2026-03-11T10:05:00+09:00', '이OO'),
    spec(7, '황산염', 'ppm', null, 400, AGREEMENT, '2026-06-02T15:40:00+09:00', '박OO'),
    liohSpec(8, '순도', '%'),
    liohSpec(9, 'Na', 'ppm'),
    liohSpec(10, 'K', 'ppm'),
  ];
}

// ---------------------------------------------------------------------------
// 문서 항목
// ---------------------------------------------------------------------------

interface ItemDef {
  id: string;
  name: string;
  rawName: string;
  rawValue: string;
  rawSpec: string;
  qualifier: ValueQualifier;
  /** 사내 규격 단위로 환산한 값 */
  value: number;
  confidence: number;
  source?: MappingSource;
}

/** 항목 하나. resolved는 담당자가 확인(confirm)한 항목, edited는 담당자가 값을 직접 고쳐 쓴 항목입니다. */
function makeItem(def: ItemDef, specs: SpecItem[], resolved = false, edited = false): ExtractionItem {
  const specItem = specs.find((entry) => entry.item_name === def.name);
  const base: ExtractionItem = {
    item_id: def.id,
    raw_name: def.rawName,
    normalized_name: def.name,
    mapping_source: def.source ?? 'dictionary',
    raw_value: def.rawValue,
    raw_spec: def.rawSpec,
    unit: specItem?.unit ?? null,
    spec_unit: specItem?.unit ?? null,
    value_qualifier: def.qualifier,
    converted_value: def.qualifier === 'not_detected' ? null : def.value,
    detection_limit: null,
    spec_lsl: null,
    spec_usl: null,
    judgement: 'pass',
    judgement_reason: null,
    deviation: null,
    reason_code: null,
    resolution: null,
    confidence: def.confidence,
    bbox: null,
    reviewed: false,
    value_source: null,
  };
  const judged = edited
    ? evaluateItem(base, specItem, { override: { qualifier: def.qualifier, value: def.value, detectionLimit: null }, valueSource: 'correction' })
    : evaluateItem(base, specItem, { reviewed: resolved });
  // 시안과 같은 판정 근거 문구(목업 데이터). 상한값만 기재된 항목이 사내 상한을 넘는 경우입니다.
  if (judged.reason_code === 'BOUND_ABOVE_LIMIT' && def.qualifier === 'less_than' && specItem?.usl != null) {
    const unit = specItem.unit;
    judged.judgement_reason = `${def.name} <${def.value} ${unit}, 사내 상한 ${specItem.usl} ${unit}보다 커서 실제 값을 확인할 수 없습니다.`;
  }
  return judged;
}

/** 누락 항목. 시안은 "원문:" 자리에 사전의 영문 표기(황산염 → Sulfate)를 보여 주므로 목업에서는 rawName으로 채웁니다. */
function makeMissing(id: string, name: string, specs: SpecItem[], rawName: string | null = null): ExtractionItem {
  const specItem = specs.find((entry) => entry.item_name === name);
  const base: ExtractionItem = {
    item_id: id,
    raw_name: rawName,
    normalized_name: name,
    mapping_source: 'spec',
    raw_value: null,
    raw_spec: null,
    unit: specItem?.unit ?? null,
    spec_unit: specItem?.unit ?? null,
    value_qualifier: null,
    converted_value: null,
    detection_limit: null,
    spec_lsl: null,
    spec_usl: null,
    judgement: 'missing',
    judgement_reason: null,
    deviation: null,
    reason_code: null,
    resolution: null,
    confidence: null,
    bbox: null,
    reviewed: false,
    value_source: null,
  };
  // 필수 항목이 CoA에 없으면 MISSING_REQUIRED(누락)이고 해결은 별도 성적서 값 또는 자체 시험값입니다.
  return evaluateItem(base, specItem);
}

const LI: ItemDef = { id: 'li', name: '순도', rawName: 'Li2CO3', rawValue: '99.6 %', rawSpec: '>= 99.0 %', qualifier: 'exact', value: 99.6, confidence: 0.96 };
const NA: ItemDef = { id: 'na', name: 'Na', rawName: 'Sodium', rawValue: '25.6 ppm', rawSpec: '<= 200 ppm', qualifier: 'exact', value: 25.6, confidence: 0.62 };
const K: ItemDef = { id: 'k', name: 'K', rawName: 'Potassium', rawValue: '< 100 ppm', rawSpec: '<= 100 ppm', qualifier: 'less_than', value: 100, confidence: 0.93 };
const FE: ItemDef = { id: 'fe', name: 'Fe', rawName: 'Iron', rawValue: '3 ppm', rawSpec: '<= 20 ppm', qualifier: 'exact', value: 3, confidence: 0.71 };
const CA: ItemDef = { id: 'ca', name: 'Ca', rawName: 'Calcium', rawValue: '0.01 %', rawSpec: '<= 0.01 %', qualifier: 'exact', value: 100, confidence: 0.85 };
const CL: ItemDef = { id: 'cl', name: 'Cl', rawName: 'Chloride', rawValue: '0.001 %', rawSpec: '<= 0.005 %', qualifier: 'exact', value: 10, confidence: 0.88 };

/** 문서 A(A0266047): 시안 2-1 기본 상태. 적합 2, 부적합 1, 판정 불가 1, 누락 1, 확인 필요 2 */
function itemsA(specs: SpecItem[]): ExtractionItem[] {
  return [
    makeItem(LI, specs),
    makeItem(NA, specs),
    makeItem(K, specs),
    makeItem(FE, specs),
    makeItem(CA, specs),
    makeItem(CL, specs),
    makeMissing('so4', '황산염', specs, 'Sulfate'),
  ];
}

/** 문서 A의 이상 패턴 변형(시안 2-10): Fe 결과 칸이 규격 문구와 같음 */
function itemsAnomaly(specs: SpecItem[]): ExtractionItem[] {
  const fe: ItemDef = { ...FE, rawValue: '<= 20 ppm', qualifier: 'less_equal', value: 20, confidence: 0.85 };
  return [
    makeItem(LI, specs),
    makeItem(NA, specs),
    makeItem(K, specs),
    makeItem(fe, specs),
    makeItem(CA, specs),
    makeItem(CL, specs),
    makeMissing('so4', '황산염', specs, 'Sulfate'),
  ];
}

/** 문서 B(A0481544): 시안 2-9. 적합 7, 확인 필요 1(중금속 항목명 매핑 확인) */
function itemsB(specs: SpecItem[]): ExtractionItem[] {
  const defs: ItemDef[] = [
    { id: 'li', name: '순도', rawName: 'Li2CO3', rawValue: '99.7 %', rawSpec: '>= 99.0 %', qualifier: 'exact', value: 99.7, confidence: 0.97 },
    { id: 'na', name: 'Na', rawName: 'Sodium', rawValue: '12 ppm', rawSpec: '<= 200 ppm', qualifier: 'exact', value: 12, confidence: 0.95 },
    { id: 'k', name: 'K', rawName: 'Potassium', rawValue: '6 ppm', rawSpec: '<= 100 ppm', qualifier: 'exact', value: 6, confidence: 0.94 },
    { id: 'fe', name: 'Fe', rawName: 'Iron', rawValue: '4 ppm', rawSpec: '<= 20 ppm', qualifier: 'exact', value: 4, confidence: 0.92 },
    { id: 'ca', name: 'Ca', rawName: 'Calcium', rawValue: '15 ppm', rawSpec: '<= 0.01 %', qualifier: 'exact', value: 15, confidence: 0.93 },
    { id: 'cl', name: 'Cl', rawName: 'Chloride', rawValue: '0.001 %', rawSpec: '<= 0.005 %', qualifier: 'exact', value: 10, confidence: 0.91 },
    { id: 'so4', name: '황산염', rawName: 'Sulfate', rawValue: '< 0.02 %', rawSpec: '<= 0.05 %', qualifier: 'less_than', value: 200, confidence: 0.92 },
  ];
  const items = defs.map((def) => makeItem(def, specs));
  // AI가 항목명을 'Pb'로 추정했지만 사내 규격에는 없는 이름입니다. 신뢰도가 낮아 확인 필요로 내려 준 시연용 항목입니다.
  items.push({
    item_id: 'hm',
    raw_name: 'Heavy metals (as Pb)',
    normalized_name: 'Pb',
    mapping_source: 'ai',
    raw_value: '< 10 ppm',
    raw_spec: '<= 10 ppm',
    unit: 'ppm',
    spec_unit: null, // 사내 규격에 없는 항목이라 규격 단위가 없습니다.
    value_qualifier: 'less_than',
    converted_value: 10,
    detection_limit: null,
    spec_lsl: null,
    spec_usl: null,
    judgement: 'check',
    judgement_reason: '추출 신뢰도 낮음(0.72)',
    deviation: null,
    reason_code: 'LOW_CONFIDENCE',
    resolution: { type: 'confirm', target_item: 'Pb', condition: '원문 하이라이트와 대조해 값 확인' },
    confidence: 0.72,
    bbox: null,
    reviewed: false,
    value_source: null,
  });
  return items;
}

/** 문서 C(A0355164): 시안 2-5. 문서 A에서 Na 수정, Fe 확인을 마치고 불합격 처분한 상태 */
function itemsC(specs: SpecItem[]): ExtractionItem[] {
  const na = { ...NA, value: 2.56 };
  return [
    makeItem(LI, specs),
    makeItem(na, specs, false, true),
    makeItem(K, specs),
    makeItem(FE, specs, true),
    makeItem(CA, specs),
    makeItem(CL, specs),
    makeMissing('so4', '황산염', specs, 'Sulfate'),
  ];
}

/** 'nd'는 Fe가 "N.D."이고 검출한계가 적혀 있지 않은 문서(시안 2-11, 2-12). 예외는 Fe 하나뿐이라 회신값을 넣으면 승인 권고가 됩니다. */
type Variant = 'allpass' | 'hold' | 'reject' | 'nd';

/**
 * 신뢰도가 낮은 추가 항목. 'reference'는 사내 규격에 없는 참고 항목(판정하지 않으므로 처분을 막지 않음),
 * 'unmapped'는 AI가 이름을 추정한 미등록 항목(UNMAPPED_ITEM, 확인 전에는 처분을 막음)입니다.
 */
type Extra = 'reference' | 'unmapped';

const EXTRA_ITEMS: Record<Extra, ItemDef> = {
  reference: { id: 'b', name: 'B', rawName: 'Boron', rawValue: '5 ppm', rawSpec: '-', qualifier: 'exact', value: 5, confidence: 0.55 },
  unmapped: { id: 'xyz', name: 'Xyz', rawName: 'Xyz', rawValue: '5 ppm', rawSpec: '-', qualifier: 'exact', value: 5, confidence: 0.55, source: 'ai' },
};

/** 목록에만 보이던 나머지 문서용 표준 항목 */
function itemsStandard(specs: SpecItem[], variant: Variant, extra: Extra | null = null): ExtractionItem[] {
  const pass = (def: ItemDef, value: number, rawValue: string): ItemDef => ({ ...def, value, rawValue, confidence: 0.95 });
  const defs: ItemDef[] = [
    pass(LI, 99.7, '99.7 %'),
    pass(NA, 12, '12 ppm'),
    variant === 'hold' ? { ...K, confidence: 0.94 } : pass(K, 6, '6 ppm'),
    variant === 'nd' ? { ...FE, rawValue: 'N.D.', qualifier: 'not_detected', value: 0, confidence: 0.95 } : pass(FE, 4, '4 ppm'),
    variant === 'reject' ? { ...CA, confidence: 0.92 } : pass(CA, 15, '15 ppm'),
    pass(CL, 10, '0.001 %'),
  ];
  const items = [...defs.map((def) => makeItem(def, specs)), makeItem(
    { id: 'so4', name: '황산염', rawName: 'Sulfate', rawValue: '100 ppm', rawSpec: '<= 500 ppm', qualifier: 'exact', value: 100, confidence: 0.95 },
    specs,
  )];
  if (extra) items.push(makeItem(EXTRA_ITEMS[extra], specs));
  return items;
}

// ---------------------------------------------------------------------------
// 원본 PDF 내용과 bbox
// ---------------------------------------------------------------------------

/** 원본 문서(종이)에 적힌 내용. 항목의 AI 추출값과 다를 수 있습니다(예: 종이에는 2.56 ppm, AI는 25.6 ppm으로 읽음). */
interface Paper {
  page1: PdfRow[];
  page2: PdfRow[];
}

const PRODUCT = 'Lithium Carbonate (Li_{2}CO_{3})';
const row = (itemId: string, label: string, spec: string, result: string, inset = false): PdfRow => ({ itemId, label, spec, result, inset });

/** 문서 A(A0266047)와 C(A0355164)의 종이. 시안 2-1, 2-5와 같은 값입니다. */
function paperA(): Paper {
  return {
    page1: [
      row('li', 'Li_{2}CO_{3} (Assay)', '≥ 99.0 %', '99.6 %'),
      row('na', 'Na', '≤ 200 ppm', '2.56 ppm', true),
      row('k', 'K', '≤ 100 ppm', '< 100 ppm', true),
      row('fe', 'Fe', '≤ 20 ppm', '3 ppm', true),
    ],
    page2: [row('ca', 'Ca', '≤ 0.01 %', '0.01 %', true), row('cl', 'Cl', '≤ 0.005 %', '0.001 %')],
  };
}

/** 이상 패턴 시나리오의 A0266047: Fe 결과 칸에 규격 문구가 그대로 적혀 있습니다(시안 2-10). */
function paperAnomaly(): Paper {
  const paper = paperA();
  paper.page1[3] = row('fe', 'Fe', '≤ 20 ppm', '≤ 20 ppm', true);
  return paper;
}

/** 문서 B(A0481544)의 종이. 시안 2-9와 같은 값입니다. */
function paperB(): Paper {
  return {
    page1: [
      row('li', 'Li_{2}CO_{3} (Assay)', '≥ 99.0 %', '99.7 %'),
      row('na', 'Na', '≤ 200 ppm', '12 ppm'),
      row('k', 'K', '≤ 100 ppm', '6 ppm'),
      row('fe', 'Fe', '≤ 20 ppm', '4 ppm'),
    ],
    page2: [
      row('ca', 'Ca', '≤ 0.01 %', '15 ppm'),
      row('cl', 'Cl', '≤ 0.005 %', '0.001 %'),
      row('so4', 'SO_{4}^{2−}', '≤ 0.05 %', '< 0.02 %'),
      row('hm', 'Heavy metals (as Pb)', '≤ 10 ppm', '< 10 ppm', true),
    ],
  };
}

/** 목록에만 보이는 나머지 문서: 항목의 원문 표기로 종이를 만듭니다. */
function paperFromItems(items: ExtractionItem[]): Paper {
  const symbols = (text: string) => text.replace(/<=/g, '≤').replace(/>=/g, '≥');
  const found = items.filter((item) => item.mapping_source !== 'spec');
  const toRow = (item: ExtractionItem) =>
    row(item.item_id, item.raw_name ?? item.normalized_name, symbols(item.raw_spec ?? ''), symbols(item.raw_value ?? ''));
  return { page1: found.slice(0, 4).map(toRow), page2: found.slice(4).map(toRow) };
}

/** 종이의 결과 칸 좌표를 항목 bbox로 붙이고, PDF 입력을 만듭니다. */
function attachPdf(docNo: string, testDate: string, items: ExtractionItem[], paper: Paper): PdfDocInput {
  const attach = (rows: PdfRow[], page: 1 | 2) =>
    rows.forEach((paperRow, index) => {
      const item = items.find((entry) => entry.item_id === paperRow.itemId);
      if (item) item.bbox = resultBbox(page, index, paperRow.result);
    });
  attach(paper.page1, 1);
  attach(paper.page2, 2);
  return { docNo, testDate, grade: 'D3', product: PRODUCT, page1: paper.page1, page2: paper.page2 };
}

// ---------------------------------------------------------------------------
// 문서 메타와 로그
// ---------------------------------------------------------------------------

interface DocMeta {
  lot: string;
  supplier: string;
  po: string;
  testDate: string;
  uploadedAt: string;
  status: DocumentStatus;
  finalDecision?: FinalDecision;
  decisionReason?: string;
  approvedBy?: string;
  approvedAt?: string;
  errorMessage?: string;
  /** 백엔드 #61의 실패 정보(실패 문서 시나리오에서만 채웁니다) */
  failure?: Pick<DocumentDetail, 'attempt_count' | 'failed_stage' | 'error_kind'>;
  /** 백엔드 #65의 방치 표시(방치 시나리오에서만 채웁니다) */
  stale?: Pick<DocumentDetail, 'is_stale' | 'stale_notified_at' | 'last_activity_at'>;
  fileSize: number;
}

const UPLOADER = { id: 2, name: '김OO' };

function buildDetail(meta: DocMeta, id: string, recommendation: ExtractionResult['lot_recommendation'] | null): DocumentDetail {
  return {
    document_id: id,
    file_name: `coa_${meta.lot}_${meta.supplier}.pdf`,
    supplier: meta.supplier,
    material_code: DEFAULT_MATERIAL_CODE,
    material_name: MATERIAL_NAME,
    po_no: meta.po,
    lot_no: meta.lot,
    received_lot_no: meta.lot,
    test_date: meta.testDate,
    origin: '중국',
    applied_standard: 'D3',
    spec_grade: 'D1',
    spec_set_code: LI2CO3_SET_CODE,
    spec_version: VERSION,
    status: meta.status,
    lot_recommendation: recommendation,
    final_decision: meta.finalDecision ?? null,
    decision_reason: meta.decisionReason ?? null,
    error_message: meta.errorMessage ?? null,
    uploaded_by: UPLOADER.name,
    uploaded_at: meta.uploadedAt,
    approved_by: meta.approvedBy ?? null,
    approved_at: meta.approvedAt ?? null,
    // 새 필드는 시나리오에서만 채워, 지정하지 않으면 예전 서버 응답처럼 필드가 없습니다.
    ...meta.failure,
    ...meta.stale,
  };
}

function buildDoc(
  meta: DocMeta,
  items: ExtractionItem[] | null,
  options: { id?: string; hidden?: boolean; paper?: Paper; reviewLogs?: ReviewLog[]; approvalLogs?: ApprovalLog[]; anomalies?: Anomaly[]; documentIssues?: DocumentIssue[] } = {},
): MockDoc {
  const id = options.id ?? meta.lot;
  if (!items) {
    return {
      detail: buildDetail(meta, id, null),
      uploaderId: UPLOADER.id,
      extraction: null,
      reviewLogs: [],
      approvalLogs: [],
      anomalies: [],
      pdf: null,
      fileSize: meta.fileSize,
      hidden: options.hidden,
    };
  }
  const pdf = attachPdf(meta.lot, meta.testDate, items, options.paper ?? paperFromItems(items));
  const summary = summarize(items);
  const documentIssues = options.documentIssues ?? [];
  const recommendation = recommendLot(summary, documentIssues.length);
  const extraction: ExtractionResult = {
    document_id: id,
    supplier: meta.supplier,
    lot_no: meta.lot,
    test_date: meta.testDate,
    origin: '중국',
    applied_standard: 'D3',
    items,
    document_issues: documentIssues,
    lot_recommendation: recommendation,
    summary,
    review_status: meta.status === 'approved' ? 'approved' : meta.status === 'on_hold' ? 'on_hold' : meta.status === 'in_review' ? 'in_review' : 'pending',
  };
  return {
    detail: buildDetail(meta, id, recommendation),
    uploaderId: UPLOADER.id,
    extraction,
    reviewLogs: options.reviewLogs ?? [],
    approvalLogs: options.approvalLogs ?? [],
    anomalies: options.anomalies ?? [],
    pdf,
    fileSize: meta.fileSize,
    hidden: options.hidden,
  };
}

/** 목업 서버의 초기 상태. 문서 A0266047, A0481544, A0355164는 시안과 같은 값입니다. */
export interface MockOptions {
  /** 문서가 하나도 없는 상태(시안 2-0) */
  empty?: boolean;
  /**
   * 'anomaly': A0266047이 이상 패턴(결과 칸이 규격 문구와 같음, 같은 값 반복)을 가진 상태(시안 2-10)
   * 'issues': [v1.4] 모든 항목이 적합한 A0390221에 문서 수준 문제(로트 불일치, 날짜 충돌)가 있어 로트 권고가 보류인 상태
   */
  /** 'sets': 탄산리튬에 규격 세트가 둘(D1, D3)인 상태. 규격 관리 화면의 세트 선택을 볼 때 씁니다. */
  scenario?: 'anomaly' | 'issues' | 'sets' | 'failed-transient' | 'failed-permanent' | 'multilot' | 'reissue-conflict' | 'reissue-review' | 'stale';
  /**
   * 'failed-transient': 실패 문서가 일시 오류(처리 시간 초과, 서버 재시작으로 중단)인 상태
   * 'failed-permanent': 실패 문서가 영구 오류(추출 실패, 판정 실패: 파일을 고쳐 다시 올려야 함)인 상태
   * 'reissue-conflict': A0266047과 같은 로트의 CoA가 2건 더 있어(총 3개 버전, 모두 처분 전) 기준 버전을 골라야 하는 상태
   * 'reissue-review': 이미 처분된 A0355190에 같은 로트의 재발행본이 들어온 상태(총 2개 버전, 기존 처분은 그대로)
   * 'stale': 처분 전 문서 2건(A0377415 보류, A0377402 검수 중)이 30일 넘게 처리되지 않아 서버가 방치(정리 대상)로 표시한 상태
   * 'multilot': A0266047이 한 문서에서 로트 2개가 읽힌 복수 로트 상태(lot_no는 null, lot_nos와 is_multi_lot, 문서 수준 문제 MULTI_LOT)
   */
}

/** [v1.4] 시나리오 'issues'에 쓰는 문서 수준 문제 예시 문구(목업) */
const ISSUES_SAMPLE: DocumentIssue[] = [
  { code: 'LOT_MISMATCH', message: 'CoA의 로트번호(A0390221)와 입고 로트번호(A0390222)가 다릅니다.' },
  { code: 'DATE_CONFLICT', message: 'CoA 발행일(2026-09-28)이 시험일(2026-09-29)보다 이전입니다.' },
];

export function createMockState(options: MockOptions = {}): MockState {
  const specs = createSpecs();

  const metaA: DocMeta = { lot: 'A0266047', supplier: 'Chengxin', po: 'PO-2026-1104', testDate: '2026-09-28', uploadedAt: '2026-10-05T17:20:00+09:00', status: 'extracted', fileSize: 524_000 };
  const docA =
    options.scenario === 'anomaly'
      ? buildDoc(metaA, itemsAnomaly(specs), {
          paper: paperAnomaly(),
          anomalies: [
            { type: 'spec_text_as_result', item_name: 'Fe', message: '결과 칸이 규격 문구와 같음 · 실측값이 아닌 규격 문구를 옮겨 적었을 수 있습니다.', related_document_ids: [] },
            { type: 'identical_values', item_name: 'Cl', message: '이전 로트(A0481544)와 값이 같음 · Cl 10 ppm이 동일합니다.', related_document_ids: ['A0481544'] },
          ],
        })
      : buildDoc(metaA, itemsA(specs), { paper: paperA() });

  const docs: MockDoc[] = [
    buildDoc({ lot: 'A0511902', supplier: '서진소재', po: 'PO-2026-1131', testDate: '2026-10-05', uploadedAt: '2026-10-06T09:02:00+09:00', status: 'queued', fileSize: 412_000 }, null),
    buildDoc({ lot: 'A0511877', supplier: 'Chengxin', po: 'PO-2026-1128', testDate: '2026-10-04', uploadedAt: '2026-10-06T08:47:00+09:00', status: 'processing', fileSize: 388_000 }, null),
    docA,
    buildDoc({ lot: 'A0481544', supplier: 'Chengxin', po: 'PO-2026-1121', testDate: '2026-09-30', uploadedAt: '2026-10-05T15:41:00+09:00', status: 'extracted', fileSize: 497_000 }, itemsB(specs), { paper: paperB() }),
    buildDoc(
      { lot: 'A0390221', supplier: '대흥리튬', po: 'PO-2026-1115', testDate: '2026-09-29', uploadedAt: '2026-10-05T14:10:00+09:00', status: 'extracted', fileSize: 455_000 },
      itemsStandard(specs, 'allpass', 'reference'),
      { documentIssues: options.scenario === 'issues' ? ISSUES_SAMPLE : [] },
    ),
    buildDoc({ lot: 'A0390188', supplier: '대흥리튬', po: 'PO-2026-1112', testDate: '2026-09-29', uploadedAt: '2026-10-05T11:36:00+09:00', status: 'extracted', fileSize: 462_000 }, itemsStandard(specs, 'hold', 'unmapped')),
    buildDoc(
      { lot: 'A0377415', supplier: '서진소재', po: 'PO-2026-1108', testDate: '2026-09-27', uploadedAt: '2026-10-04T16:22:00+09:00', status: 'on_hold', fileSize: 431_000 },
      itemsStandard(specs, 'nd'),
      {
        approvalLogs: [
          { action: 'hold', decision: null, follow_up: 'request_detection_limit', user_name: '김OO', reason: 'Fe 검출한계 회신 대기', created_at: '2026-10-05T10:20:00+09:00' },
        ],
      },
    ),
    buildDoc({ lot: 'A0377402', supplier: '서진소재', po: 'PO-2026-1107', testDate: '2026-09-27', uploadedAt: '2026-10-04T13:05:00+09:00', status: 'in_review', fileSize: 440_000 }, itemsStandard(specs, 'reject')),
    buildDoc(
      {
        lot: 'A0355190', supplier: 'Chengxin', po: 'PO-2026-1095', testDate: '2026-09-25', uploadedAt: '2026-10-03T10:18:00+09:00', status: 'approved',
        finalDecision: 'accept', approvedBy: '김OO', approvedAt: '2026-10-03T11:02:00+09:00', fileSize: 470_000,
      },
      itemsStandard(specs, 'allpass'),
      { approvalLogs: [{ action: 'approve', decision: 'accept', follow_up: null, user_name: '김OO', reason: null, created_at: '2026-10-03T11:02:00+09:00' }] },
    ),
    buildDoc(
      {
        lot: 'A0355164', supplier: 'Chengxin', po: 'PO-2026-1089', testDate: '2026-09-26', uploadedAt: '2026-10-02T17:50:00+09:00', status: 'approved',
        finalDecision: 'reject', decisionReason: 'Ca 100 ppm이 사내 상한 20 ppm을 초과합니다.', approvedBy: '김OO', approvedAt: '2026-10-05T15:02:00+09:00', fileSize: 509_000,
      },
      itemsC(specs),
      {
        paper: paperA(),
        reviewLogs: [
          { item_id: 'na', action: 'edit', before_value: '25.6', after_value: '2.56', value_source: 'correction', reviewer_name: '김OO', reviewed_at: '2026-10-05T14:32:00+09:00', reason: 'OCR 오인식 정정' },
          { item_id: 'fe', action: 'confirm', before_value: '3', after_value: '3', reviewer_name: '김OO', reviewed_at: '2026-10-05T14:35:00+09:00' },
        ],
        approvalLogs: [
          { action: 'hold', decision: null, follow_up: 'request_actual_value', user_name: '김OO', reason: '판정 불가 · 누락 항목 후속 조치 대기', created_at: '2026-10-05T10:40:00+09:00' },
          { action: 'approve', decision: 'reject', follow_up: null, user_name: '김OO', reason: 'Ca 100 ppm이 사내 상한 20 ppm을 초과합니다.', created_at: '2026-10-05T15:02:00+09:00' },
        ],
      },
    ),
    buildDoc(
      {
        lot: 'A0340871', supplier: '대흥리튬', po: 'PO-2026-1075', testDate: '2026-09-24', uploadedAt: '2026-10-02T09:33:00+09:00', status: 'approved',
        finalDecision: 'conditional_accept', decisionReason: 'K 실측값 회신 후 재확인 조건으로 승인합니다.', approvedBy: '김OO', approvedAt: '2026-10-02T14:20:00+09:00', fileSize: 452_000,
      },
      itemsStandard(specs, 'hold'),
      { approvalLogs: [{ action: 'approve', decision: 'conditional_accept', follow_up: null, user_name: '김OO', reason: 'K 실측값 회신 후 재확인 조건으로 승인합니다.', created_at: '2026-10-02T14:20:00+09:00' }] },
    ),
    buildDoc({ lot: 'A0340850', supplier: '대흥리튬', po: 'PO-2026-1074', testDate: '2026-09-24', uploadedAt: '2026-10-01T15:12:00+09:00', status: 'failed', errorMessage: '문서에서 시험 항목을 찾을 수 없습니다.', fileSize: 120_000 }, null),
  ];

  // 실패 문서 시나리오: 기본 오류 문서에 실패 단계와 종류를 채우고, 같은 종류의 실패 문서를 하나 더 둡니다.
  if (options.scenario === 'failed-transient' || options.scenario === 'failed-permanent') {
    const transient = options.scenario === 'failed-transient';
    const first = docs.find((entry) => entry.detail.document_id === 'A0340850');
    if (first) {
      Object.assign(first.detail, {
        error_message: transient ? '추출 서버가 제한 시간 안에 응답하지 않았습니다.' : '파일이 손상되어 읽을 수 없습니다.',
        attempt_count: transient ? 3 : 1,
        failed_stage: transient ? 'timeout' : 'extract',
        error_kind: transient ? 'transient' : 'permanent',
      } satisfies Partial<DocumentDetail>);
    }
    docs.push(
      buildDoc(
        {
          lot: 'A0340851', supplier: '대흥리튬', po: 'PO-2026-1076', testDate: '2026-09-24', uploadedAt: '2026-10-01T15:30:00+09:00', status: 'failed', fileSize: 98_000,
          errorMessage: transient ? '서버가 재시작되어 처리가 중단되었습니다.' : '판정에 필요한 규격 항목을 찾지 못했습니다.',
          failure: transient
            ? { attempt_count: 1, failed_stage: 'interrupted', error_kind: 'transient' }
            : { attempt_count: 2, failed_stage: 'judge', error_kind: 'permanent' },
        },
        null,
      ),
    );
  }
  // 재발행 시나리오: 같은 로트(대소문자와 구분 기호만 다른 로트번호 포함)의 CoA를 더해 서버가 conflict, review_needed로 판정하게 합니다.
  if (options.scenario === 'reissue-conflict' || options.scenario === 'reissue-review') {
    const conflict = options.scenario === 'reissue-conflict';
    const baseId = conflict ? 'A0266047' : 'A0355190';
    const base = docs.find((entry) => entry.detail.document_id === baseId);
    if (base) {
      const lotVariants = conflict ? ['a0266047', 'A0266-047'] : ['A0355-190'];
      lotVariants.forEach((lot, index) => {
        const copy = buildDoc(
          {
            lot: baseId, supplier: base.detail.supplier, po: base.detail.po_no ?? '', testDate: base.detail.test_date ?? '2026-09-28',
            uploadedAt: `2026-10-06T1${index}:30:00+09:00`, status: conflict && index === 1 ? 'in_review' : 'extracted', fileSize: 505_000 + index * 11_000,
          },
          itemsStandard(specs, 'allpass'),
          { id: `${baseId}-R${index + 1}` },
        );
        copy.detail.file_name = `coa_${baseId}_${base.detail.supplier}_재발행${index + 1}.pdf`;
        copy.detail.lot_no = lot;
        copy.detail.received_lot_no = lot;
        if (copy.extraction) copy.extraction.lot_no = lot;
        docs.push(copy);
      });
    }
  }
  // 시나리오 'stale': 서버가 방치로 표시한 문서(is_stale, 표시 시각, 마지막 활동 시각)를 채웁니다.
  if (options.scenario === 'stale') {
    const stale: Record<string, Pick<DocumentDetail, 'is_stale' | 'stale_notified_at' | 'last_activity_at'>> = {
      A0377415: { is_stale: true, stale_notified_at: '2026-11-04T09:00:00+09:00', last_activity_at: '2026-10-04T16:22:00+09:00' },
      A0377402: { is_stale: true, stale_notified_at: '2026-11-04T09:00:00+09:00', last_activity_at: '2026-10-04T13:05:00+09:00' },
    };
    for (const [id, fields] of Object.entries(stale)) {
      const target = docs.find((entry) => entry.detail.document_id === id);
      if (target) Object.assign(target.detail, fields);
    }
  }
  // 시나리오 'multilot': 한 문서에서 로트가 2개 읽혀 lot_no가 null이고, 서버가 문서 수준 문제 MULTI_LOT을 내려 준 상태입니다.
  if (options.scenario === 'multilot') {
    const target = docs.find((entry) => entry.detail.document_id === 'A0266047');
    if (target?.extraction) {
      Object.assign(target.detail, { lot_no: null, received_lot_no: null, lot_nos: ['A0266047', 'A0266048'], is_multi_lot: true } satisfies Partial<DocumentDetail>);
      target.extraction.document_issues = [{ code: 'MULTI_LOT', message: '한 문서에서 로트번호가 2개 읽혔습니다: A0266047, A0266048' }];
      target.extraction.lot_recommendation = recommendLot(target.extraction.summary, target.extraction.document_issues.length);
      target.detail.lot_recommendation = target.extraction.lot_recommendation;
    }
  }
  // 시나리오 'issues'의 경고 문구(로트 불일치, 날짜 충돌)와 문서 데이터가 맞도록 입고 로트번호와 발행일을 같이 바꿉니다.
  if (options.scenario === 'issues') {
    const target = docs.find((entry) => entry.detail.document_id === 'A0390221');
    if (target) {
      target.detail.received_lot_no = 'A0390222';
      if (target.extraction) target.extraction.issue_date = '2026-09-28';
    }
  }
  const specSets = createSpecSets();
  if (options.scenario === 'sets') {
    // 세트를 하나씩 더하며 규격 항목 번호를 이어 갑니다.
    const makers = [createExtraLi2co3Set, (all: SpecItem[]) => createCompareLi2co3Set(all, 'STRICT'), (all: SpecItem[]) => createCompareLi2co3Set(all, 'RELAXED')];
    for (const make of makers) {
      const extra = make(specs);
      specSets.push(extra.set);
      specs.push(...extra.items);
    }
  }
  return { users: MOCK_USERS.map((user) => ({ ...user })), specSets, specs, docs: options.empty ? [] : docs };
}
