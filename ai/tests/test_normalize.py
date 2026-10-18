"""[담당: 고도영] 항목명 정규화. 조사 문서·기획안·실물·가상 CoA 의 표기 사례."""
import pytest

from coa_ai.normalize import AI_CAP, Normalizer, canon, strip_charges


@pytest.mark.parametrize("raw, expected", [
    # Fisher 양식 A~D (탄산리튬)
    ("Trace analysis (Type: Ca measure)", "Ca"),
    ("Trace analysis (Type: NO3 measure)", "질산염"),
    ("Assay Titrimetry", "순도"),
    ("Titration excess HCl", "순도"),
    ("Sulfur compounds (as SO4)", "황산염"),
    ("Heavy metals (as Pb)", "중금속 총량"),
    ("Heavy metals (ICP-OES)", "중금속 총량"),
    ("Insoluble matter", "불용분"),
    ("Appearance (Color)", "외관"),
    ("Appearance (Form)", "외관"),
    ("Sodium (Na)", "Na"),
    ("Iron (Fe)", "Fe"),
    # Alfa 13418 (산화물, 첨자)
    ("Li₂CO₃", "순도"),
    ("Na₂O", "Na"),
    ("CaO", "Ca"),
    ("Fe₂O₃", "Fe"),
    ("SO₄", "황산염"),
    ("Cl", "염화물"),
    ("Insolubles", "불용분"),
    # 대정화금 (한글, 글자 사이 공백)
    ("함 량(after dried )", "순도"),
    ("납(Pb)", "Pb"),
    ("염 화 물(Cl)", "염화물"),
    ("황 산 염(SO₄)", "황산염"),
    ("마그네슘(Mg)", "Mg"),
    # 기타
    ("Sulphate", "황산염"),
    ("Assay", "순도"),
])
def test_li2co3_dictionary(raw, expected):
    m = Normalizer("LI2CO3").map(raw)
    assert (m.name, m.source, m.cap) == (expected, "dictionary", 1.0)


@pytest.mark.parametrize("raw, expected", [
    # 가상 A·D (영문)
    ("Lithium Hydroxide (as LiOH)", "LiOH 함량"),
    ("LiOH (as LiOH)", "LiOH 함량"),
    ("Carbonate (as CO₃)", "탄산"),
    ("Chloride (Cl⁻)", "염화물"),
    ("Sulfate (SO₄²⁻)", "황산염"),
    ("Magnetic Impurities", "자성이물"),
    ("Particle Size D50", "입도 D50"),
    ("Particle size D10", "입도 D10"),
    ("Particle size D90", "입도 D90"),
    # 가상 B (중·영 병기, 공백 없음)
    ("钠Na", "Na"),
    ("钾K", "K"),
    ("外观Appearance", "외관"),
    ("氢氧化锂LiOH", "LiOH 함량"),
    ("碳酸根CO₃²⁻", "탄산"),
    ("氯离子Cl⁻", "염화물"),
    ("硫酸根SO₄²⁻", "황산염"),
    ("硼B", "B"),
    ("酸不溶物Acid Insoluble", "불용분"),
    ("磁性物质Magnetic Substance", "자성이물"),
    ("粒度 D50 Particle Size", "입도 D50"),
])
def test_lioh_dictionary(raw, expected):
    m = Normalizer("LIOH").map(raw)
    assert (m.name, m.source) == (expected, "dictionary")


def test_heavy_metals_never_become_lead():
    for material in ("LI2CO3", "LIOH"):
        assert Normalizer(material).map("Heavy metals (as Pb)").name == "중금속 총량"


def test_assay_is_not_mapped_for_lithium_hydroxide():
    # LiOH·H2O 함량(약 98%)을 LiOH 함량 규격(56.5~57.5%)과 비교하는 오판 방지
    m = Normalizer("LIOH").map("Assay")
    assert (m.name, m.source, m.cap) == ("Assay", "ai", AI_CAP)


def test_material_specific_items():
    assert Normalizer("LIOH").map("Li₂CO₃").source == "ai"
    assert Normalizer("LI2CO3").map("LiOH (as LiOH)").source == "ai"


def test_oxides_the_server_cannot_convert_stay_unmapped():
    for raw in ("K₂O", "MgO", "Al₂O₃", "SiO₂"):
        assert Normalizer("LI2CO3").map(raw).source == "ai"


@pytest.mark.parametrize("material", ["li2co3", " LI2CO3 ", "LI2CO3"])
def test_material_code_is_case_insensitive(material):
    assert Normalizer(material).map("Titration excess HCl").name == "순도"


def test_unknown_material_uses_common_items_only():
    n = Normalizer("NICKEL")
    assert n.map("Sodium (Na)").name == "Na"
    assert n.map("Titration excess HCl").source == "ai"


def test_db_mappings_come_first():
    n = Normalizer("LI2CO3", {"Sodium (Na)": "나트륨", "Trace analysis": "기타"})
    assert n.map("Sodium (Na)").name == "나트륨"
    assert n.map("sodium (na)").name == "나트륨"  # 대소문자·공백 무시


def test_fuzzy_match_is_capped():
    m = Normalizer("LI2CO3").map("Insoluble in dilute HC1")  # 원문 오타 'HC1'
    assert (m.name, m.source, m.cap) == ("불용분", "ai", AI_CAP)


@pytest.mark.parametrize("raw", ["Loss at 500ºC", "Density", "염산에 녹는 상태", "Sb", ""])
def test_unmapped_keeps_raw_name(raw):
    m = Normalizer("LI2CO3").map(raw)
    assert (m.name, m.source, m.cap) == (raw, "ai", AI_CAP)


def test_text_helpers():
    assert strip_charges("SO₄²⁻") == "SO4"
    assert canon("  Sulfate  (SO₄²⁻) ") == "sulfate (so4)"


@pytest.mark.parametrize("material, raw, expected", [
    # 스캔본(OCR)에서 행 번호 칸이 항목명에 붙음 (가상 B 저해상도, Piochem)
    ("LIOH", "4 钠Na", "Na"),
    ("LIOH", "1 外观 Appearance", "외관"),
    ("LIOH", "2 氢氧化锂 LiOH", "LiOH 함량"),
    ("LIOH", "13 硫酸根 SO2-", "황산염"),
    ("LIOH", "7 Iron", "Fe"),
    # 소문자 l 을 대문자 I 로 읽음 (Fisher 양식 A, 대정화금)
    ("LI2CO3", "Trace analysis (Type: CI measure)", "염화물"),
    ("LI2CO3", "Trace analysis (Type: AI measure)", "Al"),
    ("LI2CO3", "Sulfate (S04)", "황산염"),
    # OCR 이 첨자를 괄호·밑줄로 읽음 (가상 A, Alfa 13418)
    ("LIOH", "Sulfate (SO{4{2})}", "황산염"),
    ("LI2CO3", "Fe{2O3", "Fe"),
    ("LI2CO3", "Li2CO_3", "순도"),
])
def test_ocr_noise_in_names(material, raw, expected):
    m = Normalizer(material).map(raw)
    assert (m.name, m.source) == (expected, "dictionary")


@pytest.mark.parametrize("raw", ["2 Theta", "10 Lot Size", "1", "Ti"])
def test_ocr_cleanup_does_not_invent_items(raw):
    assert Normalizer("LI2CO3").map(raw).source == "ai"
