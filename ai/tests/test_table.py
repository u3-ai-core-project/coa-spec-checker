"""[담당: 고도영] 시험 항목 표 복원. 가상 CoA 3장은 정답 라벨(소성훈 님, 항목 52개)과 같은 행을 기대한다."""
import pytest

from coa_ai.pdf_text import read_pages
from coa_ai.table import CONF_CLEAN, CONF_FIXED, CONF_LIST, _spec_from_min_max, find_headers, parse_tables, role_of

SYNTHETIC_A = [
    ("Appearance", "Conforms", "White crystalline powder", None),
    ("Lithium Hydroxide (as LiOH)", "56.84 %", "56.5 – 57.5 %", None),
    ("Carbonate (as CO₃)", "0.36 %", "≤ 0.40 %", None),
    ("Sodium (Na)", "12.5 ppm", "≤ 50 ppm", None),
    ("Potassium (K)", "11.3 ppm", "≤ 30 ppm", None),
    ("Calcium (Ca)", "4.9 ppm", "≤ 20 ppm", None),
    ("Magnesium (Mg)", "2.3 ppm", "≤ 10 ppm", None),
    ("Iron (Fe)", "4.8 ppm", "≤ 7 ppm", None),
    ("Copper (Cu)", "0.21 ppm", "≤ 1 ppm", None),
    ("Manganese (Mn)", "1.5 ppm", "≤ 10 ppm", None),
    ("Silicon (Si)", "7.7 ppm", "≤ 50 ppm", None),
    ("Chloride (Cl⁻)", "14.5 ppm", "≤ 20 ppm", None),
    ("Sulfate (SO₄²⁻)", "47 ppm", "≤ 80 ppm", None),
    ("Magnetic Impurities", "26 ppb", "≤ 50 ppb", None),
    ("Particle Size D50", "8.5 μm", "3 – 20 µm", None),
]
SYNTHETIC_B = [
    ("外观Appearance", "符合", "白色结晶粉末，无可见 杂质", None),
    ("氢氧化锂LiOH", "56.96", "56.5～57.5", "%"),
    ("碳酸根CO₃²⁻", "0.38", "≤0.40", "%"),
    ("钠Na", "0.0018", "≤0.0050", "%"),
    ("钾K", "0.0004", "≤0.0030", "%"),
    ("铁Fe", "0.00015", "≤0.0007", "%"),
    ("钙Ca", "0.0007", "≤0.0020", "%"),
    ("铜Cu", "0.00004", "≤0.0001", "%"),
    ("镁Mg", "0.00038", "≤0.0010", "%"),
    ("锰Mn", "0.00024", "≤0.0010", "%"),
    ("硅Si", "0.0019", "≤0.0050", "%"),
    ("氯离子Cl⁻", "0.0007", "≤0.0020", "%"),
    ("硫酸根SO₄²⁻", "0.0062", "≤0.0080", "%"),
    ("硼B", "0.0008", "≤0.0050", "%"),
    ("酸不溶物Acid Insoluble", "0.0010", "≤0.0050", "%"),
    ("磁性物质Magnetic Substance", "17", "≤50", "μg/kg"),
    ("粒度 D50 Particle Size", "3.9", "3.0～20.0", "μm"),
]
SYNTHETIC_D = [
    ("Appearance", "Conforms", "White crystalline powder", None),
    ("LiOH (as LiOH)", "56.99", "56.50 – 57.50", "% w/w"),
    ("Carbonate (as CO3)", "0.17", "≤ 0.50", "% w/w"),
    ("Chloride (Cl)", "12", "≤ 30", "mg/kg"),
    ("Sulfate (SO4)", "26", "≤ 100", "mg/kg"),
    ("Sodium (Na)", "10", "≤ 40", "mg/kg"),
    ("Potassium (K)", "7.8", "≤ 20", "mg/kg"),
    ("Calcium (Ca)", "19.1", "≤ 20", "mg/kg"),
    ("Magnesium (Mg)", "2.3", "≤ 10", "mg/kg"),
    ("Iron (Fe)", "1.4", "≤ 5", "mg/kg"),
    ("Copper (Cu)", "0.28", "≤ 1", "mg/kg"),
    ("Manganese (Mn)", "1.1", "≤ 5", "mg/kg"),
    ("Silicon (Si)", "12", "≤ 40", "mg/kg"),
    ("Nickel (Ni)", "0.7", None, "mg/kg"),
    ("Chromium (Cr)", "0.6", None, "mg/kg"),
    ("Zinc (Zn)", "2.4", None, "mg/kg"),
    ("Magnetic impurities", "9", "≤ 100", "ppb"),
    ("Particle size D10", "2.7", None, "µm"),
    ("Particle size D50", "10.9", "3.0 – 20.0", "µm"),
    ("Particle size D90", "24.0", None, "µm"),
]


@pytest.mark.parametrize("name, expected", [
    ("COA_A_0007.pdf", SYNTHETIC_A),
    ("COA_B_0005.pdf", SYNTHETIC_B),
    ("COA_D_0007.pdf", SYNTHETIC_D),
])
def test_synthetic_golden_rows(fixture_pdf, name, expected):
    rows = parse_tables(read_pages(fixture_pdf(name)))
    assert [(r.name, r.value, r.spec, r.unit) for r in rows] == expected
    assert all(r.confidence == CONF_CLEAN and r.page == 1 for r in rows)
    assert all(r.value_box is not None for r in rows)


@pytest.mark.parametrize("text, role", [
    ("Result name", "item"), ("Result Name", "item"), ("Test Value", "result"), ("Tests", "item"),
    ("Specifications", "spec"), ("Sepecification", "spec"), ("TEST ITEM", "item"), ("TEST RESULT", "result"),
    ("检验项目", "item"), ("检验结果", "result"), ("标准要求", "spec"), ("单位", "unit"), ("Units", "unit"),
    ("Min", "min"), ("Max", "max"), ("Status", "judge"), ("Sr.no.", "no"), ("Item test", "item"),
    ("Lot Number", None), ("ICP-OES", None),
    ("The undersigned hereby certifies the following data", None),
])
def test_role_of(text, role):
    assert role_of(text) == role


def test_sentence_with_column_words_is_not_a_header(fixture_pdf):
    # 가상 A 본문 '… true specification of the obtained results of tests …' 는 머리글이 아니다
    lines = read_pages(fixture_pdf("COA_A_0007.pdf"))[0].lines
    headers = find_headers(lines)
    assert len(headers) == 1
    assert lines[headers[0].first].text == "Tests Method Results Specifications"


def test_hidden_item_name_in_spec_and_result(make_pdf):
    # Fisher 양식 A: 원소 이름이 'Trace analysis' 행의 규격·결과 칸 안에 있다
    path = make_pdf([
        [(40, "Result name"), (150, "Units"), (210, "Specifications"), (410, "Test Value")],
        [(40, "Trace analysis"), (210, "Type: Na measure < 10 ppm"), (410, "Type: Na measure < 10 ppm")],
        [(40, "Trace analysis"), (210, "Type: Ca measure 90 ppm"), (410, "Type: Ca measure 90 ppm")],
    ])
    rows = parse_tables(read_pages(path))
    assert [(r.name, r.value, r.spec) for r in rows] == [
        ("Trace analysis (Type: Na measure)", "< 10 ppm", "< 10 ppm"),
        ("Trace analysis (Type: Ca measure)", "90 ppm", "90 ppm"),
    ]


def test_headerless_list(make_pdf):
    # Alfa 13418 처럼 머리글 없이 '이름  값' 만 나열된 문서
    path = make_pdf([
        [(90, "Lot No.:"), (200, "U24E051")],
        [(225, "Li2CO3"), (330, "99.5 %")],
        [(225, "Na2O"), (330, "0.04 %")],
        [(225, "Fe2O3"), (330, "< 0.0001 %")],
        [(225, "Appearance"), (330, "Passes")],
    ])
    rows = parse_tables(read_pages(path))
    assert [(r.name, r.value, r.spec) for r in rows] == [
        ("Li2CO3", "99.5 %", None), ("Na2O", "0.04 %", None), ("Fe2O3", "< 0.0001 %", None), ("Appearance", "Passes", None),
    ]
    assert all(r.confidence == CONF_LIST for r in rows)


def test_two_lines_are_not_a_list(make_pdf):
    path = make_pdf([[(90, "Product No.:"), (200, "13418")], [(90, "Lot No.:"), (200, "U24E051")]])
    assert parse_tables(read_pages(path)) == []


@pytest.mark.parametrize("lo, hi, expected", [
    ("56.50", "57.50", "56.50 – 57.50"),
    (None, "0.50", "≤ 0.50"),
    ("99.0", None, "≥ 99.0"),
    (None, None, None),
])
def test_spec_from_min_max(lo, hi, expected):
    assert _spec_from_min_max(lo, hi) == expected


def test_table_continues_on_next_page_without_header(tmp_path):
    # 실물 CoA 는 모두 1쪽이지만 합성 시나리오 A04(복수 페이지)를 대비한다
    import pymupdf
    doc = pymupdf.open()
    rows_by_page = [
        [[(40, "Result name"), (210, "Specifications"), (410, "Test Value")],
         [(40, "Sodium (Na)"), (210, "=<1000 ppm"), (410, "2.56 ppm")],
         [(40, "Calcium (Ca)"), (210, "=<100 ppm"), (410, "3.32 ppm")]],
        [[(40, "Iron (Fe)"), (210, "=<20 ppm"), (410, "none detected")],
         [(40, "Potassium (K)"), (210, "=<100 ppm"), (410, "8.68 ppm")]],
    ]
    for lines in rows_by_page:
        page = doc.new_page(width=595, height=842)
        for n, parts in enumerate(lines):
            for x, text in parts:
                page.insert_text((x, 60 + 16 * n), text, fontsize=9)
    path = tmp_path / "two_pages.pdf"
    doc.save(path)
    rows = parse_tables(read_pages(path))
    assert [(r.page, r.name, r.value) for r in rows] == [
        (1, "Sodium (Na)", "2.56 ppm"), (1, "Calcium (Ca)", "3.32 ppm"),
        (2, "Iron (Fe)", "none detected"), (2, "Potassium (K)", "8.68 ppm"),
    ]


def test_raw_text_is_kept_as_is(make_pdf):
    # 값 해석은 서버 몫: 부등호·ND·괄호 설명을 고치지 않는다
    path = make_pdf([
        [(40, "Result name"), (210, "Specifications"), (410, "Test Value")],
        [(40, "Nitrate (NO3)"), (210, "=<5 ppm"), (410, "=<5 ppm")],
        [(40, "Iron (Fe)"), (210, "=<20 ppm"), (410, "N.D.")],
        [(40, "Insoluble matter"), (210, "=<0.01 % (in dilute HCl)"), (410, "0.005 % (in dilute HCl)")],
    ])
    rows = parse_tables(read_pages(path))
    assert [(r.value, r.spec) for r in rows] == [
        ("=<5 ppm", "=<5 ppm"), ("N.D.", "=<20 ppm"), ("0.005 % (in dilute HCl)", "=<0.01 % (in dilute HCl)"),
    ]


def test_non_unit_text_in_unit_column_goes_back_to_name(make_pdf):
    # Piochem: pH 행의 단위 칸에 'At 25°C' 같은 조건이 들어 있다
    path = make_pdf([
        [(65, "Sr.no."), (111, "Item test"), (242, "units"), (345, "Sepecification"), (501, "Results")],
        [(78, "3"), (111, "pH"), (234, "At 25C"), (376, "14"), (508, "pass")],
        [(78, "6"), (111, "Sulphate"), (244, "wt%"), (353, "0.01% max"), (507, "0.1%")],
    ])
    rows = parse_tables(read_pages(path))
    assert [(r.name, r.unit, r.confidence) for r in rows] == [
        ("pH At 25C", None, CONF_FIXED), ("Sulphate", "wt%", CONF_CLEAN),
    ]


def test_symbol_value_grid(make_pdf):
    # Puratronic: 한 줄에 '기호 값' 쌍이 여러 개 (머리글 없음)
    grid = [["Al", "7", "Sb", "ND"], ["Fe", "1", "Pb", "ND"], ["Na", "ND", "Si", "1"]]
    path = make_pdf([[(126 + 92 * k, cell) for k, cell in enumerate(row)] for row in grid])
    rows = parse_tables(read_pages(path))
    assert [(r.name, r.value) for r in rows] == [
        ("Al", "7"), ("Sb", "ND"), ("Fe", "1"), ("Pb", "ND"), ("Na", "ND"), ("Si", "1"),
    ]
    assert all(r.confidence == CONF_LIST and r.spec is None for r in rows)


def test_sparse_min_column_is_kept(tmp_path):
    # Min 값이 한 행(순도)에만 있는 표: 값이 적은 열도 머리글이 있으면 열로 남아야 한다 (최종 검토에서 발견)
    import pymupdf
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    lines = [[(44, "Parameter"), (283, "Unit"), (342, "Min"), (386, "Max"), (439, "Result")],
             [(44, "Assay"), (283, "%"), (335, "99.50"), (447, "99.62")]]
    for name in ["Sodium (Na)", "Potassium (K)", "Calcium (Ca)", "Magnesium (Mg)", "Iron (Fe)", "Copper (Cu)",
                 "Manganese (Mn)", "Silicon (Si)", "Chloride (Cl)", "Sulfate (SO4)", "Nickel (Ni)"]:
        lines.append([(44, name), (280, "mg/kg"), (390, "40"), (455, "12")])
    for n, parts in enumerate(lines):
        for x, text in parts:
            page.insert_text((x, 60 + 15 * n), text, fontsize=9)
    path = tmp_path / "sparse.pdf"
    doc.save(path)
    rows = parse_tables(read_pages(path))
    assert (rows[0].name, rows[0].spec, rows[0].unit, rows[0].value) == ("Assay", "≥ 99.50", "%", "99.62")
    assert (rows[1].name, rows[1].spec, rows[1].unit) == ("Sodium (Na)", "≤ 40", "mg/kg")
