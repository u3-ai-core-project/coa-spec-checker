import { DOCUMENT_ISSUE_LABEL, REASON_CODE_LABEL } from '../../domain/exceptions';
import type {
  DocumentStatus,
  ExtractionResult,
  FollowUpLine,
  FollowUpsResponse,
  HoldFollowUp,
  InquiryDraft,
  OpenDocument,
} from '../types';
import type { MockDoc } from './fixtures';

/**
 * 후속 조치와 공급사 문의 초안 (GET /documents/{id}/follow-ups)의 목업 구현입니다.
 * 백엔드 services/inquiry_draft.py와 followup_service.py를 옮겼습니다(템플릿 초안만 있고 AI 초안은 없습니다).
 */

// 공급사에 요청해야 해결되는 사유(나머지는 담당자가 내부에서 확인)
const SUPPLIER_REASONS = new Set([
  'OUT_OF_SPEC',
  'CONVERTED_OOS',
  'BOUND_ABOVE_LIMIT',
  'ND_NO_LOD',
  'LOD_ABOVE_LIMIT',
  'LOWER_LIMIT_UNVERIFIABLE',
  'SPEC_COPIED',
  'MISSING_REQUIRED',
  'AMBIGUOUS_ANALYTE',
  'SUM_ONLY',
]);
const SUPPLIER_ISSUES = new Set(['LOT_MISMATCH', 'PRODUCT_MISMATCH', 'DATE_CONFLICT', 'SUPPLIER_CONFLICT']);

// 메일에 쓰는 공급사용 요청 문구. 없는 코드는 해결 조건(condition)을 그대로 씁니다.
const SUPPLIER_REQUEST: Record<string, string> = {
  OUT_OF_SPEC: '단위·표기 오류 여부와 재시험 가능 여부 확인',
  CONVERTED_OOS: '산화물 기준 결과의 원소 기준 값 또는 단위·표기 확인',
  SPEC_COPIED: '실측값이 기재된 CoA 재발행',
  MISSING_REQUIRED: '해당 항목의 시험 결과(별도 성적서) 송부',
};

// 보류 화면의 후속 조치 기본값 추천. 위에 있을수록 우선합니다.
const FOLLOW_UP_BY_CODE: Array<[string[], HoldFollowUp]> = [
  [['LOT_MISMATCH', 'PRODUCT_MISMATCH'], 'request_correct_coa'],
  [['SPEC_COPIED', 'DATE_CONFLICT'], 'request_reissue'],
  [['ND_NO_LOD', 'LOD_ABOVE_LIMIT'], 'request_detection_limit'],
  [['BOUND_ABOVE_LIMIT', 'LOWER_LIMIT_UNVERIFIABLE'], 'request_actual_value'],
  [['AMBIGUOUS_ANALYTE', 'SUM_ONLY'], 'request_single_value'],
  [['MISSING_REQUIRED'], 'internal_test'],
];

const OPEN_STATUSES: DocumentStatus[] = ['extracted', 'in_review', 'on_hold'];

interface FollowUps {
  supplierLines: FollowUpLine[];
  internalLines: FollowUpLine[];
}

interface LotRequest {
  lotNo: string | null;
  materialName: string | null;
  lines: FollowUpLine[];
}

/** 판정 결과 → 후속 조치 목록(부적합, 정합성 오류, 판정 불가, 누락, 확인 필요 순) */
export function buildFollowUps(result: ExtractionResult): FollowUps {
  const out: FollowUps = { supplierLines: [], internalLines: [] };
  const order: Record<string, number> = { fail: 0, undetermined: 2, missing: 3, check: 4 };

  for (const issue of result.document_issues) {
    const line: FollowUpLine = {
      target: '문서',
      code: issue.code,
      label: DOCUMENT_ISSUE_LABEL[issue.code] ?? issue.code,
      why: issue.message,
      condition: '올바른(최신) CoA 또는 공급사 확인',
      raw_value: null,
      to_supplier: SUPPLIER_ISSUES.has(issue.code),
    };
    (line.to_supplier ? out.supplierLines : out.internalLines).push(line);
  }

  const exceptions = result.items
    .filter((item) => item.reason_code !== null)
    .sort((a, b) => (order[a.judgement] ?? 9) - (order[b.judgement] ?? 9));
  for (const item of exceptions) {
    const code = item.reason_code as string;
    const line: FollowUpLine = {
      target: item.normalized_name,
      code,
      label: REASON_CODE_LABEL[item.reason_code!] ?? code,
      why: item.judgement_reason ?? '',
      condition: item.resolution?.condition ?? '',
      raw_value: item.raw_value,
      to_supplier: SUPPLIER_REASONS.has(code),
    };
    (line.to_supplier ? out.supplierLines : out.internalLines).push(line);
  }
  // 부적합을 맨 앞에, 문서 정합성 오류를 그 다음에 둡니다.
  const rank = (line: FollowUpLine) => (line.code === 'OUT_OF_SPEC' || line.code === 'CONVERTED_OOS' ? 0 : line.target === '문서' ? 1 : 2);
  out.supplierLines.sort((a, b) => rank(a) - rank(b));
  return out;
}

/** 보류할 때 기본으로 고를 후속 조치. 공급사 요청이 없으면 null입니다(부적합만 있으면 보류보다 처분 대상). */
export function suggestFollowUp(followUps: FollowUps): HoldFollowUp | null {
  const codes = new Set(followUps.supplierLines.map((line) => line.code));
  for (const [group, followUp] of FOLLOW_UP_BY_CODE) {
    if (group.some((code) => codes.has(code))) return followUp;
  }
  return followUps.internalLines.length > 0 && codes.size === 0 ? 'other' : null;
}

function requestLines(lines: FollowUpLine[], start = 1): string[] {
  const out: string[] = [];
  let n = start - 1;
  const missing = lines.filter((line) => line.code === 'MISSING_REQUIRED').map((line) => line.target);
  for (const line of lines.filter((entry) => entry.code !== 'MISSING_REQUIRED')) {
    n += 1;
    const cited = line.raw_value ? ` (CoA 기재: "${line.raw_value}")` : '';
    out.push(`${n}. ${line.target}${cited}`);
    out.push(`   - 사유: ${line.why || line.label}`);
    out.push(`   - 요청: ${SUPPLIER_REQUEST[line.code] ?? line.condition}`);
  }
  if (missing.length > 0) {
    n += 1;
    out.push(`${n}. 당사 필수 시험 항목 중 CoA 에 없는 항목: ${missing.join(', ')}`);
    out.push(`   - 요청: ${SUPPLIER_REQUEST.MISSING_REQUIRED}`);
  }
  return out;
}

// 처분은 담당자가 정하므로 초안에서 보류, 불합격 같은 처분을 단정하지 않습니다.
const CLOSING = ['', '확인 후 회신 부탁드립니다.', '', '감사합니다.'];

/** 템플릿 초안. 로트가 하나면 로트 1통, 여러 개면 같은 공급사의 요청을 메일 1통으로 묶습니다. */
function draftOf(supplierName: string | null, requests: LotRequest[]): InquiryDraft {
  const supplier = supplierName || '공급사';
  const lots = requests.filter((lot) => lot.lines.length > 0);
  const material = lots.find((lot) => lot.materialName)?.materialName ?? '원료';
  const lotNames = lots.map((lot) => lot.lotNo ?? '로트번호 미기재');

  if (lots.length === 1) {
    const subject = `[CoA 확인 요청] ${material} / Lot ${lotNames[0]}`;
    const intro = `귀사에서 송부하신 ${material} (Lot ${lotNames[0]}) 시험성적서(CoA)를 검토하는 중 아래 항목의 확인이 필요하여 요청드립니다.`;
    const body = [`${supplier} 품질 담당자님께,`, '', intro, '', ...requestLines(lots[0].lines), ...CLOSING];
    return { subject, body: body.join('\n'), source: 'template', lot_nos: lots.map((lot) => lot.lotNo) };
  }

  const subject = `[CoA 확인 요청] ${material} ${lots.length}개 로트 (${lotNames.join(', ')})`;
  const body = [
    `${supplier} 품질 담당자님께,`,
    '',
    `귀사에서 송부하신 ${material} 시험성적서(CoA) ${lots.length}건을 검토하는 중 아래 로트별 항목의 확인이 필요하여 요청드립니다.`,
    '',
  ];
  lots.forEach((lot, index) => {
    body.push(`[Lot ${lotNames[index]}]`, ...requestLines(lot.lines), '');
  });
  return { subject, body: [...body.slice(0, -1), ...CLOSING].join('\n'), source: 'template', lot_nos: lots.map((lot) => lot.lotNo) };
}

/** 문서 1건의 후속 조치, 보류 후속 조치 추천, 문의 초안, 같은 공급사의 열린 요청 묶음 */
export function getFollowUps(doc: MockDoc & { extraction: ExtractionResult }, allDocs: MockDoc[]): FollowUpsResponse {
  const followUps = buildFollowUps(doc.extraction);
  const thisLot: LotRequest = { lotNo: doc.detail.lot_no, materialName: doc.detail.material_name, lines: followUps.supplierLines };

  // 같은 공급사의 처리 중 문서(공급사명이 있을 때만, 대소문자와 앞뒤 공백은 무시)
  const openDocuments: OpenDocument[] = [];
  const lots: LotRequest[] = [];
  const supplier = doc.detail.supplier.trim().toLowerCase();
  if (supplier) {
    const others = allDocs
      .filter((entry) => entry.detail.supplier.trim().toLowerCase() === supplier && OPEN_STATUSES.includes(entry.detail.status))
      .sort((a, b) => a.detail.uploaded_at.localeCompare(b.detail.uploaded_at));
    for (const other of others) {
      if (!other.extraction) continue;
      const lines = other === doc ? thisLot.lines : buildFollowUps(other.extraction).supplierLines;
      if (lines.length === 0) continue;
      openDocuments.push({ document_id: other.detail.document_id, lot_no: other.detail.lot_no, status: other.detail.status, request_count: lines.length });
      lots.push(other === doc ? thisLot : { lotNo: other.detail.lot_no, materialName: other.detail.material_name, lines });
    }
  }

  return {
    document_id: doc.detail.document_id,
    supplier: doc.detail.supplier,
    lot_no: doc.detail.lot_no,
    suggested_follow_up: suggestFollowUp(followUps),
    supplier_lines: followUps.supplierLines,
    internal_lines: followUps.internalLines,
    draft: thisLot.lines.length > 0 ? draftOf(doc.detail.supplier, [thisLot]) : null,
    open_documents: openDocuments,
    combined_draft: lots.length >= 2 ? draftOf(doc.detail.supplier, lots) : null,
  };
}
