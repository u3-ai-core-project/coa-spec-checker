"""대표 데모 20 로트 시연용 가상 CoA PDF 만들기 (범위 정의서 6장).

    cd backend
    python -m evaluation.demo20_pdfs [--out <폴더>]

수용 테스트(tests/api/test_demo20_acceptance.py)와 같은 시나리오 값(tests/fixtures/demo20_scenarios.json)을
로트마다 서로 다른 가상 협력사의 CoA PDF로 만듭니다. .env 에 EXTRACTOR=ai 를 넣고 업로드하면 PDF와 추출 값이 일치합니다.

- 1~19번: demo01.pdf ~ demo19.pdf (로트 번호 DEMO-L01 ~ DEMO-L19)
- 20번: 같은 협력사의 로트 3개 (demo20_DEMO-L20-1.pdf ~ -3.pdf). 모두 올리면 같은 값 반복 경고가 나온다
- 17번: 글자 층이 없는 흐린 스캔 PDF (OCR로 읽으므로 확인 필요, 보류)
- 12번은 업로드할 때 입고 로트를 DEMO-L99 로, 18번은 규격 세트를 LI2CO3-2013 으로 지정해야 한다 (수용 테스트와 같음)
- 21·22번은 팀이 추가한 사례다. 21번은 규격 세트를 LI2CO3-SUPPLIER-V1 으로 올리면 적합, 지정하지 않으면(기본 D1) 부적합이다.
  22번은 수산화리튬 CoA 라서 업로드할 때 원자재를 LIOH 로 고르고 규격 세트는 지정하지 않는다 (기본 LIOH-BG-V1 적용)

PDF는 단순한 표 형식 하나이고 실제 협력사 양식이 아니다. 항목명은 팀 항목 사전에 있는 영문 표기를 쓴다 (자성이물은 'Magnetic substance').
필요한 패키지: reportlab, pillow, pypdfium2 (requirements.txt)
"""
import argparse
import io
from pathlib import Path

import pypdfium2 as pdfium
from PIL import ImageFilter
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from tests.api.test_demo20_acceptance import CASES, build_coa

BLURRY_CASE = 17
SUPPLIERS = [
    "Arvelle Lithium Pty Ltd", "Selmora Lithium S.A.", "Ruilan Lithium Co., Ltd.", "Corvane Refining Pty Ltd",
    "Norden Mineral AB", "Kestrel Chemicals Ltd", "Tamsin Resources Inc.", "Hallow Lithium GmbH",
    "Quorra Materials Co.", "Brenmoor Lithium Ltd", "Valtera Chemical S.A.", "Oskar Lithium Oy",
    "Pinegate Minerals LLC", "Zephra Lithium Co.", "Maribel Lithium S.A.", "Dunmore Chemicals Ltd",
    "Ikaros Lithium Corp.", "Lumen Battery Materials", "Sorrel Lithium Pty Ltd", "Yarrow Chemicals AG",
    "Bexley Lithium Ltd", "Corrin Hydroxide Co.",
]
LABEL = {
    "순도": "Li2CO3 Assay", "Na": "Sodium (Na)", "K": "Potassium (K)", "Fe": "Iron (Fe)", "Ca": "Calcium (Ca)",
    "Mg": "Magnesium (Mg)", "Pb": "Lead (Pb)", "염화물": "Chloride (Cl)", "황산염": "Sulfate (SO4)",
    "자성이물": "Magnetic substance", "Na+K": "Na+K",
    "외관": "Appearance", "수분": "Moisture", "입도 D50": "D50", "LiOH 함량": "LiOH Content", "탄산": "Carbonate",
}
PRODUCT = {"LI2CO3": "Lithium Carbonate Battery Grade", "LIOH": "Lithium Hydroxide Monohydrate Battery Grade"}


def render(coa: dict, product: str = PRODUCT["LI2CO3"]) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    _, height = A4
    c.setFont("Helvetica-Bold", 16)
    c.drawString(50, height - 60, "CERTIFICATE OF ANALYSIS")
    c.setFont("Helvetica", 10)
    y = height - 90
    for key, value in [("Supplier", coa["supplier"]), ("Lot No.", coa["lot_no"]), ("Test Date", coa["test_date"]),
                       ("Issue Date", coa["issue_date"]), ("Standard", coa["applied_standard"]),
                       ("Product", product)]:
        c.drawString(50, y, f"{key}: {value}")
        y -= 15
    y -= 15
    c.setFont("Helvetica-Bold", 10)
    for x, title in [(50, "Test Item"), (270, "Specification"), (400, "Result"), (480, "Unit")]:
        c.drawString(x, y, title)
    c.line(50, y - 4, 545, y - 4)
    y -= 20
    c.setFont("Helvetica", 10)
    for item in coa["items"]:
        written = item["raw_name"].isascii() and item["raw_name"] != item["normalized_name"]
        name = item["raw_name"] if written else LABEL.get(item["normalized_name"], item["raw_name"])
        c.drawString(50, y, name)
        c.drawString(270, y, item.get("raw_spec", ""))
        c.drawString(400, y, item["raw_value"])
        c.drawString(480, y, item.get("unit") or "")
        y -= 20
    c.save()
    return buf.getvalue()


def blurry_scan(pdf: bytes) -> bytes:
    """글자 층이 없는 흐린 스캔 PDF (200dpi, 가우시안 1.5)."""
    page = pdfium.PdfDocument(pdf)[0]
    image = page.render(scale=200 / 72).to_pil().convert("RGB").filter(ImageFilter.GaussianBlur(1.5))
    out = io.BytesIO()
    image.save(out, format="PDF", resolution=200)
    return out.getvalue()


def make_all(out: Path) -> list[Path]:
    out.mkdir(parents=True, exist_ok=True)
    written = []
    for case in CASES:
        number = int(case["id"])
        if "repeat_lots" in case:  # 20번: 같은 협력사의 로트 여러 개
            for lot in case["repeat_lots"]:
                lot = lot.replace("DEMO-L0", "DEMO-L20-")  # 1~19번 로트 번호와 겹치지 않게
                coa = build_coa(case.get("patch"), lot_no=lot)
                coa["supplier"] = SUPPLIERS[number - 1]
                path = out / f"demo20_{lot}.pdf"
                path.write_bytes(render(coa))
                written.append(path)
            continue
        coa = build_coa(case.get("patch"), lot_no=f"DEMO-L{number:02d}", base=case.get("base", "base"))
        coa["supplier"] = SUPPLIERS[number - 1]
        pdf = render(coa, PRODUCT[case.get("material_code", "LI2CO3")])
        path = out / f"demo{case['id']}.pdf"
        path.write_bytes(blurry_scan(pdf) if number == BLURRY_CASE else pdf)
        written.append(path)
    return written


def main(argv: list[str] | None = None) -> Path:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=Path(__file__).parent / "reports" / "demo20_pdfs", help="PDF 저장 폴더")
    args = ap.parse_args(argv)
    files = make_all(args.out)
    print(f"{len(files)}개 저장: {args.out}")
    return args.out


if __name__ == "__main__":
    main()
