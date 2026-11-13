"""[담당: 장수민] 일괄 접수 (멘토님 범위 정의서 UC01·UC07, UC10 의 검토 큐. 명세 v1.4 4.4-1, 4.4-2).

흐름
  1. POST /documents/batch : CoA 1~20개 + 입고 정보 CSV(선택)
       - CSV 는 파일을 저장하기 전에 전부 검사한다. 잘못된 행이 있으면 아무것도 저장하지 않고 400 VALIDATION_ERROR
       - CoA 파일은 한 건씩 검사한다. 잘못된 파일(형식·크기)은 그 파일만 빼고(rejected) 나머지는 접수한다 (오류 문서 격리)
       - CSV 의 file_name 이 업로드 파일명과 같으면 그 입고 정보로 바로 연결한다 (공급사, 원자재, 입고 로트, 규격 세트)
  2. 추출이 끝나면 (save_extraction → link_by_lot)
       - 아직 입고 정보가 없는 문서는 CoA 로트번호 = received_lot 인 입고 행과 연결한다
       - 입고 CSV 를 올렸는데 맞는 입고 행이 없으면 LOT_MISMATCH (입고 정보 없는 CoA → 보류 권고)
       - 로트는 맞는데 입고 원자재가 다르면 PRODUCT_MISMATCH (입고 건은 연결, 규격 세트는 그대로)
       - file_name 으로 연결된 문서는 입고 로트 ≠ CoA 로트를 document_checks.check_lot 이 검사한다
  3. GET /documents/batch/{batch_id} : 검토 큐
       부적합 → 서류 불일치 → 판정 불가·누락·확인 필요 → 정상 → 처리 중 순. 추출 실패 문서는 격리 목록,
       CoA 가 연결되지 않은 입고 행은 CoA 미접수 목록으로 따로 보여 준다.

입고 CSV 열 (멘토님 S02 receipts.csv)
  필수 : receipt_id, received_lot
  선택 : supplier, material(없으면 업로드의 material_code), spec_id(규격 세트 코드), received_date(YYYY-MM-DD), file_name
  received_lot_no, material_code, spec_set_code 처럼 서버 필드 이름으로 써도 된다. UTF-8(BOM 포함), CP949(엑셀 한글) 모두 읽는다.
"""
import csv
import io
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.config import settings
from app.core.enums import DocumentIssueCode as D, DocumentStatus, LotRecommendation
from app.core.errors import AppException, ErrorCode
from app.models import Batch, Document, Receipt, User
from app.schemas.batch import (
    BatchDetail, BatchQueueItem, BatchSummary, BatchUploadResponse, ReceiptOut, RejectedFile, UploadedDocument,
)
from app.schemas.extraction import DocumentIssue, ExtractionInput, Summary
from app.services import document_service, spec_service, storage_service
from app.services.judgement.document_checks import normalize_lot

REQUIRED_COLUMNS = ("receipt_id", "received_lot")
COLUMN_ALIASES = {"received_lot_no": "received_lot", "material_code": "material", "spec_set_code": "spec_id"}
MAX_RECEIPT_ROWS = 200
MAX_ERRORS_SHOWN = 5


# ---------------------------------------------------------------------------
# 입고 CSV
# ---------------------------------------------------------------------------
@dataclass
class ReceiptRow:
    line: int
    receipt_id: str
    received_lot: str
    material: str
    supplier: str | None = None
    spec_id: str | None = None
    received_date: date | None = None
    file_name: str | None = None


def _decode(content: bytes) -> str:
    for encoding in ("utf-8-sig", "cp949"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise AppException(ErrorCode.VALIDATION_ERROR, "입고 CSV 는 UTF-8 또는 CP949 로 저장해야 합니다")


def _parse_date(value: str) -> date:
    return date.fromisoformat(value.replace("/", "-").replace(".", "-"))


def parse_receipts_csv(db: Session, content: bytes, *, default_material: str) -> list[ReceiptRow]:
    """입고 CSV → 행 목록. 잘못된 행이 하나라도 있으면 400 VALIDATION_ERROR (행 번호 포함, 최대 5개)."""
    reader = csv.DictReader(io.StringIO(_decode(content)))
    headers = [COLUMN_ALIASES.get(h.strip().lower(), h.strip().lower()) for h in (reader.fieldnames or [])]
    missing = [c for c in REQUIRED_COLUMNS if c not in headers]
    if missing:
        raise AppException(ErrorCode.VALIDATION_ERROR, f"입고 CSV 에 {', '.join(missing)} 열이 필요합니다")
    reader.fieldnames = headers

    rows: list[ReceiptRow] = []
    errors: list[str] = []
    seen_ids: set[str] = set()
    seen_lots: set[tuple[str, str]] = set()
    seen_files: set[str] = set()
    for line, raw in enumerate(reader, start=2):
        values = {k: (v or "").strip() for k, v in raw.items() if k}
        if not any(values.values()):
            continue  # 빈 줄
        receipt_id, lot = values.get("receipt_id", ""), values.get("received_lot", "")
        material = values.get("material") or default_material
        problem = None
        if not receipt_id or not lot:
            problem = "receipt_id, received_lot 은 비울 수 없습니다"
        elif receipt_id in seen_ids:
            problem = f"receipt_id {receipt_id} 가 중복됩니다"
        elif (material, normalize_lot(lot)) in seen_lots:
            problem = f"입고 로트 {lot} 가 중복됩니다 (CoA 로트로 연결할 때 구분할 수 없음)"
        elif values.get("file_name") and values["file_name"].lower() in seen_files:
            problem = f"file_name {values['file_name']} 이 중복됩니다"
        received_date = None
        if problem is None and values.get("received_date"):
            try:
                received_date = _parse_date(values["received_date"])
            except ValueError:
                problem = f"received_date 는 YYYY-MM-DD 형식이어야 합니다: {values['received_date']}"
        if problem is None:
            try:
                spec_service.resolve_spec_set(db, material, values.get("spec_id") or None)
            except AppException as e:
                problem = e.message
        if problem:
            errors.append(f"{line}행: {problem}")
            continue
        seen_ids.add(receipt_id)
        seen_lots.add((material, normalize_lot(lot)))
        if values.get("file_name"):
            seen_files.add(values["file_name"].lower())
        rows.append(ReceiptRow(line=line, receipt_id=receipt_id, received_lot=lot, material=material,
                               supplier=values.get("supplier") or None, spec_id=values.get("spec_id") or None,
                               received_date=received_date, file_name=values.get("file_name") or None))
    if errors:
        more = f" 외 {len(errors) - MAX_ERRORS_SHOWN}건" if len(errors) > MAX_ERRORS_SHOWN else ""
        raise AppException(ErrorCode.VALIDATION_ERROR,
                           "입고 CSV 오류 — " + "; ".join(errors[:MAX_ERRORS_SHOWN]) + more)
    if len(rows) > MAX_RECEIPT_ROWS:
        raise AppException(ErrorCode.VALIDATION_ERROR, f"입고 CSV 는 {MAX_RECEIPT_ROWS}행까지 올릴 수 있습니다")
    return rows


# ---------------------------------------------------------------------------
# 일괄 업로드
# ---------------------------------------------------------------------------
@dataclass
class UploadFile:
    name: str
    content: bytes


@dataclass
class BatchCreated:
    batch: Batch
    documents: list[tuple[Document, str | None]] = field(default_factory=list)  # (문서, 연결된 receipt_id)
    rejected: list[RejectedFile] = field(default_factory=list)


def create_batch(
    db: Session,
    *,
    user: User,
    files: list[UploadFile],
    material_code: str,
    spec_set_code: str | None = None,
    receipts_csv: bytes | None = None,
) -> BatchCreated:
    """묶음을 만들고 파일을 한 건씩 접수한다. 파일 처리(추출)는 호출한 쪽이 백그라운드로 등록한다."""
    if not files:
        raise AppException(ErrorCode.VALIDATION_ERROR, "CoA 파일을 1개 이상 올려야 합니다")
    if len(files) > settings.MAX_BATCH_FILES:
        raise AppException(ErrorCode.VALIDATION_ERROR, f"한 번에 {settings.MAX_BATCH_FILES}개까지 올릴 수 있습니다")
    # 운영 정책 1장: 묶음 전체를 받아도 차단 기준(95%)을 넘지 않는지 먼저 본다. 넘으면 묶음을 만들지 않고 507
    storage_service.ensure_capacity(sum(len(f.content) for f in files))
    material_code = material_code.strip()
    spec_set_code = (spec_set_code or "").strip() or None
    spec_service.resolve_spec_set(db, material_code, spec_set_code)  # 기본값부터 검사 (UNKNOWN_MATERIAL 등)
    rows = parse_receipts_csv(db, receipts_csv, default_material=material_code) if receipts_csv else []

    batch = Batch(material_code=material_code, created_by=user.id)
    batch.receipts = [
        Receipt(receipt_id=r.receipt_id, supplier=r.supplier, material_code=r.material, received_lot_no=r.received_lot,
                spec_set_code=r.spec_id, received_date=r.received_date, file_name=r.file_name)
        for r in rows
    ]
    db.add(batch)
    db.commit()

    by_file = {r.file_name.lower(): r for r in batch.receipts if r.file_name}
    out = BatchCreated(batch=batch)
    for f in files:
        receipt = by_file.pop(f.name.lower(), None)  # 같은 이름 파일이 둘이면 첫 파일만 연결
        material, spec, supplier, lot = material_code, spec_set_code, None, None
        if receipt:
            material, supplier, lot = receipt.material_code, receipt.supplier, receipt.received_lot_no
            # 입고 행의 규격 세트 우선. 없으면 업로드 기본 세트 (원자재가 다르면 그 원자재의 기본 세트)
            spec = receipt.spec_set_code or (spec_set_code if material == material_code else None)
        try:
            doc = document_service.create_document(
                db, user=user, file_name=f.name, content=f.content, material_code=material,
                supplier=supplier, received_lot_no=lot, spec_set_code=spec, batch_id=batch.id,
            )
        except AppException as e:
            db.rollback()
            out.rejected.append(RejectedFile(file_name=f.name, code=e.code.name, message=e.message))
            continue
        if receipt:
            receipt.document_id = doc.id
            db.commit()
        out.documents.append((doc, receipt.receipt_id if receipt else None))
    return out


def to_upload_response(created: BatchCreated) -> BatchUploadResponse:
    return BatchUploadResponse(
        batch_id=created.batch.id,
        documents=[UploadedDocument(document_id=d.id, file_name=d.file_name, status=d.status, receipt_id=rid)
                   for d, rid in created.documents],
        rejected=created.rejected,
        receipts=len(created.batch.receipts),
        linked_by_file=sum(1 for _, rid in created.documents if rid),
    )


# ---------------------------------------------------------------------------
# 추출 후 입고 정보 연결 (save_extraction 에서 판정 전에 부른다)
# ---------------------------------------------------------------------------
def link_by_lot(db: Session, document: Document, extraction: ExtractionInput) -> list[DocumentIssue]:
    """일괄 접수 문서를 CoA 로트번호로 입고 행과 연결한다. 연결하지 못하면 LOT_MISMATCH 를 돌려준다.

    연결되면 문서의 입고 로트·공급사(비어 있을 때)·규격 세트(입고 행에 spec_id 가 있을 때)를 입고 정보로 채운다.
    """
    if not document.batch_id:
        return []
    receipts = list(db.scalars(select(Receipt).where(Receipt.batch_id == document.batch_id)
                               .order_by(Receipt.id).with_for_update()))
    if not receipts or any(r.document_id == document.id for r in receipts):
        return []  # 입고 CSV 없음, 또는 file_name 으로 이미 연결 (로트 비교는 check_lot)

    key = normalize_lot(extraction.lot_no)
    if not key:
        return [DocumentIssue(code=D.LOT_MISMATCH, message="CoA 에서 로트번호를 찾지 못해 입고 정보와 연결하지 못했습니다")]
    same_lot = [r for r in receipts if normalize_lot(r.received_lot_no) == key and r.material_code == document.material_code]
    free = [r for r in same_lot if r.document_id is None]
    if not free:
        if same_lot:
            return [DocumentIssue(code=D.LOT_MISMATCH,
                                  message=f"입고 로트 {same_lot[0].received_lot_no} 는 이미 다른 CoA 와 연결됨 (같은 로트 CoA 중복)")]
        other_material = [r for r in receipts if normalize_lot(r.received_lot_no) == key and r.document_id is None]
        if other_material:
            # 로트는 맞는데 입고 원자재가 다름 (생성기 v2 MATERIAL_MISMATCH). 입고 건은 연결해 두고 규격 세트는 바꾸지 않는다
            receipt = other_material[0]
            receipt.document_id = document.id
            document.received_lot_no = receipt.received_lot_no
            document.supplier = document.supplier or receipt.supplier
            return [DocumentIssue(code=D.PRODUCT_MISMATCH,
                                  message=f"입고 원자재 {receipt.material_code} ≠ 접수 원자재 {document.material_code} "
                                          f"(로트 {receipt.received_lot_no})")]
        return [DocumentIssue(code=D.LOT_MISMATCH, message=f"입고 정보에 CoA 로트 {extraction.lot_no.strip()} 가 없습니다")]

    receipt = free[0]
    receipt.document_id = document.id
    document.received_lot_no = receipt.received_lot_no
    document.supplier = document.supplier or receipt.supplier
    if receipt.spec_set_code:
        document.spec_set = spec_service.resolve_spec_set(db, document.material_code, receipt.spec_set_code)
    return []


def receipt_of(db: Session, document: Document) -> Receipt | None:
    """문서와 연결된 입고 행 (일괄 접수가 아니거나 연결되지 않았으면 None)."""
    if not document.batch_id:
        return None
    db.flush()  # 방금 link_by_lot 이 연결한 행도 찾도록 (세션 autoflush 꺼져 있음)
    return db.scalar(select(Receipt).where(Receipt.document_id == document.id))


# ---------------------------------------------------------------------------
# 검토 큐
# ---------------------------------------------------------------------------
PRIORITY_LABELS = {1: "부적합", 2: "서류 불일치", 3: "판정 불가·누락·확인 필요", 4: "정상", 5: "처리 중"}


def _issues(doc: Document) -> list[str]:
    if doc.extraction is None:
        return []
    return [i["code"] for i in doc.extraction.result.get("document_issues", [])]


def _priority(doc: Document, issues: list[str]) -> int:
    if doc.status in (DocumentStatus.QUEUED, DocumentStatus.PROCESSING):
        return 5
    if doc.lot_recommendation == LotRecommendation.REJECT:
        return 1
    if issues:
        return 2
    if doc.lot_recommendation == LotRecommendation.HOLD:
        return 3
    return 4


def get_batch(db: Session, batch_id: str) -> BatchDetail:
    batch = db.get(Batch, batch_id, options=[joinedload(Batch.creator), joinedload(Batch.receipts)])
    if batch is None:
        raise AppException(ErrorCode.NOT_FOUND, "존재하지 않는 일괄 접수입니다")
    docs = list(db.scalars(
        select(Document).where(Document.batch_id == batch_id)
        .options(joinedload(Document.extraction), joinedload(Document.spec_set)).order_by(Document.uploaded_at)
    ).unique())
    receipt_of = {r.document_id: r for r in batch.receipts if r.document_id}

    queue: list[BatchQueueItem] = []
    isolated: list[BatchQueueItem] = []
    for doc in docs:
        issues = _issues(doc)
        failed = doc.status == DocumentStatus.FAILED
        priority = 0 if failed else _priority(doc, issues)
        receipt = receipt_of.get(doc.id)
        item = BatchQueueItem(
            priority=priority, priority_label="격리(추출 실패)" if failed else PRIORITY_LABELS[priority],
            document_id=doc.id, file_name=doc.file_name, supplier=doc.supplier, lot_no=doc.lot_no,
            received_lot_no=doc.received_lot_no, receipt_id=receipt.receipt_id if receipt else None,
            spec_set_code=doc.spec_set.code if doc.spec_set else None, status=doc.status,
            lot_recommendation=doc.lot_recommendation, document_issues=issues,
            summary=Summary.model_validate(doc.extraction.result["summary"]) if doc.extraction else None,
            error_message=doc.error_message,
        )
        (isolated if failed else queue).append(item)
    queue.sort(key=lambda i: i.priority)  # 같은 순위는 업로드 순 (정렬 안정성)

    counts = {p: sum(1 for i in queue if i.priority == p) for p in PRIORITY_LABELS}
    return BatchDetail(
        batch_id=batch.id, material_code=batch.material_code, created_by=batch.creator.name, created_at=batch.created_at,
        summary=BatchSummary(total=len(docs), reject=counts[1], document_issue=counts[2], hold=counts[3],
                             approve=counts[4], processing=counts[5], isolated=len(isolated)),
        queue=queue, isolated=isolated,
        unmatched_receipts=[ReceiptOut(receipt_id=r.receipt_id, supplier=r.supplier, material_code=r.material_code,
                                       received_lot_no=r.received_lot_no, spec_set_code=r.spec_set_code,
                                       received_date=r.received_date, file_name=r.file_name)
                            for r in batch.receipts if r.document_id is None],
    )
