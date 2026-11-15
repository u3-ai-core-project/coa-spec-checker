import type { Bbox } from '../types';

/**
 * 목업 원본 CoA PDF 생성기. 외부 파일 없이 두 쪽짜리 PDF 바이트를 만들고, 결과 칸의 좌표(bbox)도 같은
 * 레이아웃에서 계산해 하이라이트가 PDF와 어긋나지 않게 합니다.
 *
 * 페이지 크기는 시안의 원본 문서 영역(652×738)과 같게 두었습니다. 뷰어가 이 영역 너비에 맞춰 그리면
 * 배율이 1:1이 되어 시안의 위치와 크기(제목 20, 표 13, 쪽번호 10)가 그대로 나옵니다.
 * 좌표는 모두 시안 문서 영역의 왼쪽 위(265, 137)를 원점으로 한 값이고, bbox는 페이지 대비 0~1 비율입니다.
 */

const PAGE_W = 652;
const PAGE_H = 738;

// 표 열 위치(시안 기준, 문서 영역 원점)
const COL_LEFT = 40; // 문서 안쪽 여백
const COL_RIGHT = 612;
const COL_LABEL = 57; // 항목 열 글자 시작
const COL_SPEC = 256.5;
const COL_RESULT = 441.9;
const RESULT_INSET = 6; // 하이라이트가 있는 칸은 글자가 6만큼 안쪽에서 시작합니다.

const ROW_H = 44.5;
type Rgb = readonly [number, number, number];
const GRAY: Rgb = [91, 97, 106];
const LIGHT: Rgb = [138, 144, 153];
const DARK: Rgb = [31, 35, 40];
const BORDER: Rgb = [209, 213, 219];
const HEAD_FILL: Rgb = [249, 250, 251];

export interface PdfRow {
  /** 이 줄에 대응하는 항목. 하이라이트 좌표를 항목에 붙일 때 씁니다. */
  itemId: string | null;
  /** 아래 첨자는 _{2}, 위 첨자는 ^{2−}로 씁니다. 예: Li_{2}CO_{3} (Assay) */
  label: string;
  spec: string;
  result: string;
  /** 시안에서 하이라이트가 있는 칸처럼 결과 글자를 안쪽에서 시작할지 */
  inset: boolean;
}

export interface PdfDocInput {
  docNo: string;
  testDate: string;
  grade: string;
  product: string;
  page1: PdfRow[];
  page2: PdfRow[];
}

// ---------------------------------------------------------------------------
// 글자 폭(Helvetica, Helvetica-Bold). 가운데·오른쪽 정렬과 하이라이트 너비 계산에 씁니다.
// ---------------------------------------------------------------------------

const HELV =
  '278 278 355 556 556 889 667 191 333 333 389 584 278 333 278 278 556 556 556 556 556 556 556 556 556 556 278 278 584 584 584 556 1015 667 667 722 722 667 611 778 722 278 500 667 556 833 722 778 667 778 722 667 611 722 667 944 667 667 611 278 278 278 469 556 333 556 556 500 556 556 278 556 556 222 222 500 222 833 556 556 556 556 333 500 278 556 500 722 500 500 500 334 260 334 584'
    .split(' ')
    .map(Number);
const HELV_BOLD =
  '278 333 474 556 556 889 722 238 333 333 389 584 278 333 278 278 556 556 556 556 556 556 556 556 556 556 333 333 584 584 584 611 975 722 722 722 722 667 611 778 722 278 556 722 611 833 722 778 667 778 722 667 611 722 667 944 667 667 611 333 278 333 584 556 333 556 611 556 611 556 333 611 611 278 278 556 278 889 611 611 611 611 389 556 333 611 556 778 556 556 500 389 280 389 584'
    .split(' ')
    .map(Number);
const SYMBOL_WIDTH = 549; // ≤ ≥ −

function charWidth(char: string, bold: boolean): number {
  if (char === '≤' || char === '≥' || char === '−') return SYMBOL_WIDTH;
  const code = char.charCodeAt(0) - 32;
  const table = bold ? HELV_BOLD : HELV;
  return code >= 0 && code < table.length ? table[code] : 556;
}

export function textWidth(text: string, size: number, bold = false): number {
  let total = 0;
  for (const char of text) total += charWidth(char, bold);
  return (total * size) / 1000;
}

// ---------------------------------------------------------------------------
// 글자 조각: 보통 / 아래 첨자 / 위 첨자, 그리고 Helvetica에 없는 기호(≤ ≥ −)는 Symbol 글꼴
// ---------------------------------------------------------------------------

interface Piece {
  text: string;
  rise: number;
  scale: number;
}

function parseMarkup(text: string): Piece[] {
  const pieces: Piece[] = [];
  const pattern = /_\{([^}]*)\}|\^\{([^}]*)\}/g;
  let last = 0;
  let match: RegExpExecArray | null;
  while ((match = pattern.exec(text))) {
    if (match.index > last) pieces.push({ text: text.slice(last, match.index), rise: 0, scale: 1 });
    if (match[1] !== undefined) pieces.push({ text: match[1], rise: -2.2, scale: 0.75 });
    else pieces.push({ text: match[2], rise: 5.1, scale: 0.75 });
    last = pattern.lastIndex;
  }
  if (last < text.length) pieces.push({ text: text.slice(last), rise: 0, scale: 1 });
  return pieces;
}

/** 첨자 표시를 걷어낸 글자(너비 계산용) */
export function plainText(text: string): string {
  return parseMarkup(text)
    .map((piece) => piece.text)
    .join('');
}

function escapePdf(text: string): string {
  return text.replace(/\\/g, '\\\\').replace(/\(/g, '\\(').replace(/\)/g, '\\)');
}

const SYMBOL_CODE: Record<string, string> = { '≤': '\\243', '≥': '\\263', '−': '\\055' };

/** 한 조각을 Helvetica와 Symbol 구간으로 나눠 PDF 연산자로 만듭니다. */
function pieceOps(piece: Piece, size: number, bold: boolean): string {
  const fontSize = +(size * piece.scale).toFixed(2);
  const font = bold ? 'F2' : 'F1';
  let ops = `${piece.rise} Ts `;
  let buffer = '';
  const flush = () => {
    if (buffer) ops += `/${font} ${fontSize} Tf (${escapePdf(buffer)}) Tj `;
    buffer = '';
  };
  for (const char of piece.text) {
    const code = char.charCodeAt(0);
    if (SYMBOL_CODE[char]) {
      flush();
      ops += `/F3 ${fontSize} Tf (${SYMBOL_CODE[char]}) Tj `;
    } else if (code >= 32 && code <= 126) {
      buffer += char;
    }
    // Helvetica(WinAnsi)에 없는 글자는 건너뜁니다.
  }
  flush();
  return ops;
}

class Canvas {
  private ops: string[] = [];

  private color(rgb: Rgb, stroke = false): string {
    return `${rgb.map((v) => +(v / 255).toFixed(3)).join(' ')} ${stroke ? 'RG' : 'rg'}`;
  }

  /** 글자. x는 왼쪽, yTop은 위에서 잰 글자 바닥선(baseline) 위치입니다. */
  text(x: number, yTop: number, size: number, value: string, color: Rgb, bold = false): void {
    const body = parseMarkup(value)
      .map((piece) => pieceOps(piece, size, bold))
      .join('');
    this.ops.push(`BT ${this.color(color)} ${x} ${PAGE_H - yTop} Td ${body}0 Ts ET`);
  }

  /** 가로 가운데(center) 또는 오른쪽 끝(right) 기준으로 글자를 놓습니다. */
  textAt(anchor: 'center' | 'right', x: number, yTop: number, size: number, value: string, color: Rgb, bold = false): void {
    const width = textWidth(plainText(value), size, bold);
    this.text(anchor === 'center' ? x - width / 2 : x - width, yTop, size, value, color, bold);
  }

  line(x1: number, y1: number, x2: number, y2: number, width: number, color: Rgb): void {
    this.ops.push(`${width} w ${this.color(color, true)} ${x1} ${PAGE_H - y1} m ${x2} ${PAGE_H - y2} l S`);
  }

  strokeRect(x: number, y: number, w: number, h: number, color: Rgb, width = 1): void {
    this.ops.push(`${width} w ${this.color(color, true)} ${x} ${PAGE_H - y - h} ${w} ${h} re S`);
  }

  fillRect(x: number, y: number, w: number, h: number, color: Rgb): void {
    this.ops.push(`${this.color(color)} ${x} ${PAGE_H - y - h} ${w} ${h} re f`);
  }

  strokeCircle(cx: number, cy: number, r: number, width: number, color: Rgb, alpha: number): void {
    const k = 0.5523 * r;
    const y = PAGE_H - cy;
    const mixed = color.map((v) => Math.round(v * alpha + 255 * (1 - alpha))) as unknown as Rgb;
    this.ops.push(
      `${width} w ${this.color(mixed, true)} ${cx + r} ${y} m ${cx + r} ${y + k} ${cx + k} ${y + r} ${cx} ${y + r} c ` +
        `${cx - k} ${y + r} ${cx - r} ${y + k} ${cx - r} ${y} c ${cx - r} ${y - k} ${cx - k} ${y - r} ${cx} ${y - r} c ` +
        `${cx + k} ${y - r} ${cx + r} ${y - k} ${cx + r} ${y} c S`,
    );
  }

  build(): string {
    return this.ops.join('\n');
  }
}

// ---------------------------------------------------------------------------
// 레이아웃 (시안 좌표)
// ---------------------------------------------------------------------------

/** 결과 표의 위치와 첫 줄 글자 바닥선(위에서 잰 값). 2쪽은 정보 표가 없어 표가 위에서 시작합니다. */
const TABLE = {
  1: { top: 362.5, firstBaseline: 429.9 },
  2: { top: 179.5, firstBaseline: 246.9 },
} as const;

const HEAD_BASELINE_GAP = 42.5; // 머리글 바닥선은 첫 줄 바닥선보다 이만큼 위
const RESULT_SIZE = 13;

function rowBaseline(page: 1 | 2, index: number): number {
  return TABLE[page].firstBaseline + ROW_H * index;
}

/** 결과 칸의 원본 근거 좌표(하이라이트 상자). 상자는 글자 양쪽에 6씩 여백을 둡니다. */
export function resultBbox(page: 1 | 2, index: number, result: string): Bbox {
  const baseline = rowBaseline(page, index);
  const width = textWidth(result, RESULT_SIZE, true) + RESULT_INSET * 2;
  return {
    page,
    x: COL_RESULT / PAGE_W,
    y: (baseline - 11.9) / PAGE_H,
    w: width / PAGE_W,
    h: 15 / PAGE_H,
  };
}

function letterhead(canvas: Canvas, docNo: string): void {
  canvas.text(COL_LEFT, 54.2, 20, 'Chengxin Co., Ltd.', DARK, true);
  canvas.text(COL_LEFT, 77.4, 11, 'Quality Assurance Dept.', LIGHT);
  canvas.textAt('right', COL_RIGHT, 43.4, 11, `No. ${docNo}`, GRAY);
  canvas.line(COL_LEFT, 98.5, COL_RIGHT, 98.5, 2, DARK);
  canvas.textAt('center', (COL_LEFT + COL_RIGHT) / 2, 138.7, 20, 'Certificate of Analysis', DARK, true);
  canvas.line(COL_LEFT, 159.5, COL_RIGHT, 159.5, 1, DARK);
}

function resultTable(canvas: Canvas, page: 1 | 2, rows: PdfRow[]): void {
  const top = TABLE[page].top;
  const height = 41 + ROW_H * rows.length + 0.5;
  canvas.fillRect(COL_LEFT + 0.5, top + 0.5, COL_RIGHT - COL_LEFT - 1, 40.5, HEAD_FILL);
  canvas.strokeRect(COL_LEFT, top, COL_RIGHT - COL_LEFT, height, BORDER, 1);
  const headBaseline = TABLE[page].firstBaseline - HEAD_BASELINE_GAP;
  canvas.text(COL_LABEL, headBaseline, 13, 'Item', GRAY, true);
  canvas.text(COL_SPEC, headBaseline, 13, 'Specification', GRAY, true);
  canvas.text(COL_RESULT, headBaseline, 13, 'Result', GRAY, true);
  rows.forEach((row, index) => {
    const baseline = rowBaseline(page, index);
    const separator = top + 41 + ROW_H * index;
    canvas.line(COL_LEFT + 0.5, separator, COL_RIGHT - 0.5, separator, 1, BORDER);
    canvas.text(COL_LABEL, baseline, 13, row.label, GRAY);
    canvas.text(COL_SPEC, baseline, 13, row.spec, GRAY);
    canvas.text(COL_RESULT + (row.inset ? RESULT_INSET : 0), baseline, 13, row.result, DARK, true);
  });
}

function pageOne(input: PdfDocInput): string {
  const canvas = new Canvas();
  letterhead(canvas, input.docNo);
  const info: Array<[string, string]> = [
    ['Product', input.product],
    ['Grade', input.grade],
    ['Batch / Lot No.', input.docNo],
    ['Date of Test', input.testDate],
  ];
  canvas.strokeRect(COL_LEFT, 179.5, COL_RIGHT - COL_LEFT, 163, BORDER, 1);
  info.forEach(([label, value], index) => {
    const y = 180.5 + 40.5 * index;
    canvas.fillRect(COL_LEFT + 1, y, 144, 39.5, HEAD_FILL);
    if (index > 0) canvas.line(COL_LEFT + 1, y - 0.5, COL_RIGHT - 1, y - 0.5, 1, BORDER);
    canvas.text(COL_LABEL, 204.4 + 40.5 * index, 13, label, GRAY);
    canvas.text(201, 204.4 + 40.5 * index, 13, value, DARK);
  });
  resultTable(canvas, 1, input.page1);
  canvas.text(COL_LEFT, 717.6, 10, 'Page 1 of 2', LIGHT);
  return canvas.build();
}

function pageTwo(input: PdfDocInput): string {
  const canvas = new Canvas();
  letterhead(canvas, input.docNo);
  resultTable(canvas, 2, input.page2);
  const tableBottom = TABLE[2].top + 41 + ROW_H * input.page2.length + 0.5;
  const remarksTop = tableBottom + 20;
  canvas.strokeRect(COL_LEFT, remarksTop, COL_RIGHT - COL_LEFT, 44, BORDER, 1);
  canvas.text(COL_LABEL, remarksTop + 26.1, 12, 'Remarks: Packing 25 kg net / bag. Storage in dry and ventilated place.', GRAY);
  const signTop = remarksTop + 44 + 24;
  canvas.strokeRect(COL_LEFT, signTop, COL_RIGHT - COL_LEFT, 52, BORDER, 1);
  canvas.line(231, signTop + 1, 231, signTop + 51, 1, BORDER);
  canvas.line(421, signTop + 1, 421, signTop + 51, 1, BORDER);
  const signBaseline = signTop + 30.1;
  canvas.text(COL_LABEL, signBaseline, 12, 'Analyst: ____', DARK);
  canvas.text(247, signBaseline, 12, 'Reviewer: ____', DARK);
  canvas.text(437, signBaseline, 12, `Issued: ${input.testDate}`, DARK);
  canvas.strokeCircle(593.95, 647.95, 27.9, 3, [192, 52, 46], 0.6);
  canvas.textAt('center', 593.95, 652.1, 11, 'QA', [192, 52, 46], true);
  canvas.text(COL_LEFT, 717.6, 10, 'Page 2 of 2', LIGHT);
  return canvas.build();
}

/** PDF 바이트(문자열). 모두 ASCII라 문자 수와 바이트 수가 같습니다. */
export function buildPdf(input: PdfDocInput): string {
  const stream = (content: string) => `<< /Length ${content.length} >>\nstream\n${content}\nendstream`;
  const resources = '<< /Font << /F1 5 0 R /F2 6 0 R /F3 9 0 R >> >>';
  const objects = [
    '<< /Type /Catalog /Pages 2 0 R >>',
    '<< /Type /Pages /Kids [3 0 R 4 0 R] /Count 2 >>',
    `<< /Type /Page /Parent 2 0 R /MediaBox [0 0 ${PAGE_W} ${PAGE_H}] /Resources ${resources} /Contents 7 0 R >>`,
    `<< /Type /Page /Parent 2 0 R /MediaBox [0 0 ${PAGE_W} ${PAGE_H}] /Resources ${resources} /Contents 8 0 R >>`,
    '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>',
    '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>',
    stream(pageOne(input)),
    stream(pageTwo(input)),
    '<< /Type /Font /Subtype /Type1 /BaseFont /Symbol >>',
  ];

  let body = '%PDF-1.4\n';
  const offsets: number[] = [];
  objects.forEach((object, index) => {
    offsets.push(body.length);
    body += `${index + 1} 0 obj\n${object}\nendobj\n`;
  });
  const xrefStart = body.length;
  body += `xref\n0 ${objects.length + 1}\n0000000000 65535 f \n`;
  for (const offset of offsets) body += `${String(offset).padStart(10, '0')} 00000 n \n`;
  body += `trailer\n<< /Size ${objects.length + 1} /Root 1 0 R >>\nstartxref\n${xrefStart}\n%%EOF\n`;
  return body;
}

export function buildPdfBlob(input: PdfDocInput): Blob {
  return new Blob([buildPdf(input)], { type: 'application/pdf' });
}
