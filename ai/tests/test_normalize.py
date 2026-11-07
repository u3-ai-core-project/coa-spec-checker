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


@pytest.mark.parametrize("raw", ["Assay", "Assay (special)", "ASSAY"])
def test_assay_is_lioh_content_for_lithium_hydroxide(raw):
    # 서버 item_mappings.csv 의 'LIOH,Assay → LiOH 함량' 과 같게 (PR #43 후속). 탄산리튬에서는 그대로 순도다.
    # LiOH·H2O 기준 값(Piochem 98%)은 자체 검증(selfcheck)이 확인 필요로 돌린다
    m = Normalizer("LIOH").map(raw)
    assert (m.name, m.source) == ("LiOH 함량", "dictionary")
    assert Normalizer("LI2CO3").map(raw).name == "순도"


def test_material_specific_items():
    assert Normalizer("LIOH").map("Li₂CO₃").source == "ai"
    assert Normalizer("LIOH").map("Li₂CO₃ 함량").source == "ai"  # 수산화리튬에서는 불순물이라 LiOH 함량이 아니다
    assert Normalizer("LI2CO3").map("LiOH (as LiOH)").source == "ai"


@pytest.mark.parametrize("raw, expected", [
    # 규격 세트 항목 (PR #20 LI2CO3-D3-2023)
    ("Loss on ignition", "강열감량"),
    ("Loss on Ignition (LOI)", "강열감량"),
    ("LOI", "강열감량"),
    ("L.O.I.", "강열감량"),
    ("Ignition loss", "강열감량"),
    ("灼烧失量", "강열감량"),
    ("灼减量", "강열감량"),
    ("강열감량", "강열감량"),
    ("D99", "입도 D99"),
    ("Particle size D99", "입도 D99"),
    ("粒度 D99", "입도 D99"),
    ("D99 (μm)", "입도 D99"),
    # 산화물 표기: 서버가 raw_name 의 화학식으로 원소 환산 (PR #14)
    ("K₂O", "K"),
    ("K2O content", "K"),
    ("氧化钾 K2O", "K"),
    ("Potassium oxide (K₂O)", "K"),
    ("MgO", "Mg"),
    ("氧化镁MgO", "Mg"),
    # 화학식·이름 + 함량 표기
    ("Li₂CO₃ 함량", "순도"),
    ("Li2CO3含量", "순도"),
    ("Li2CO3 Assay", "순도"),
    ("Li2CO3 purity", "순도"),
    ("Li2CO3 (%)", "순도"),
    ("Content of Li2CO3", "순도"),
    ("탄산리튬 함량", "순도"),
])
def test_spec_set_items(raw, expected):
    m = Normalizer("LI2CO3").map(raw)
    assert (m.name, m.source) == (expected, "dictionary")


def test_oxides_the_server_cannot_convert_stay_unmapped():
    for raw in ("Al₂O₃", "SiO₂"):
        assert Normalizer("LI2CO3").map(raw).source == "ai"


@pytest.mark.parametrize("raw", ["Potassium oxide", "Magnesium oxide", "Sodium oxide", "氧化钾", "산화칼륨"])
def test_oxide_names_without_formula_are_not_guessed(raw):
    # 서버는 raw_name 의 화학식(K2O 등)을 보고 환산한다. 화학식 없는 이름을 원소로 붙이면 환산 없이 판정된다
    assert Normalizer("LI2CO3").map(raw).name == raw


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


@pytest.mark.parametrize("raw", ["Loss at 500ºC", "Loss on drying", "건조감량", "Density", "염산에 녹는 상태", "Sb", ""])
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
    # 생성기 v2 양식 D 저해상도·흐림: Li 의 i 를 I·( 로 읽거나 놓침, D10 의 0 을 D 로 읽음
    ("LI2CO3", "LI2CO3 (as LI2CO3)", "순도"),
    ("LI2CO3", "L2CO3 (as L2CO3)", "순도"),
    ("LI2CO3", "LI2CO3 (as LI2COd)", "순도"),
    ("LI2CO3", "Particle size D1D", "입도 D10"),
])
def test_ocr_noise_in_names(material, raw, expected):
    m = Normalizer(material).map(raw)
    assert (m.name, m.source) == (expected, "dictionary")


@pytest.mark.parametrize("raw", ["2 Theta", "10 Lot Size", "1", "Ti"])
def test_ocr_cleanup_does_not_invent_items(raw):
    assert Normalizer("LI2CO3").map(raw).source == "ai"


@pytest.mark.parametrize("raw, expected", [
    # 생성기 v2 양식 B(중·영) 흐림·저해상도: 한자 이름 뒤의 기호·옆 칸을 잡음으로 읽음. 한자 이름만으로 확실하다
    ("钾κ", "K"),
    ("钾×", "K"),
    ("水分1.0", "수분"),
    ("外观 一", "외관"),
    ("粮度 D50 Panicde Su", "입도 D50"),  # 粒度 를 粮度 로 읽음. D50 과 '度' 로 입도
])
def test_cjk_name_with_ocr_noise(raw, expected):
    m = Normalizer("LI2CO3").map(raw)
    assert (m.name, m.source) == (expected, "dictionary")


@pytest.mark.parametrize("raw, expected", [
    ("硼日", "B"),                                            # 硼 B 의 B 를 비슷한 한자 日 로 읽음
    ("Moisture (105 °C) % ww", "수분"),                        # 단위 칸 글자가 붙음 (양식 D 흐림)
    ("Appearance Vsu 一", "외관"),                             # 시험 방법 칸이 붙음
    ("Magnetic impurties Magnetic sep /IP-OES ppb", "자성이물"),
    ("Suffate (SO,2)", "황산염"),                              # OCR 오타
    ("Nckel (N)", "Ni"),
    ("Lithum Carbonate (as", "순도"),
])
def test_ocr_guesses_need_review(raw, expected):
    # 앞 단어만 맞추거나 오타를 짐작한 것이라 확정하지 않고 담당자 확인으로 넘긴다
    m = Normalizer("LI2CO3").map(raw)
    assert (m.name, m.source, m.cap) == (expected, "ai", AI_CAP)


@pytest.mark.parametrize("raw", ["Sodium + Potassium total", "销", "Tesi tom Unn", "Na and K"])
def test_ocr_guess_does_not_split_combined_or_unknown(raw):
    # 합산 줄을 앞 단어(Sodium)만 보고 Na 로 붙이면 안 된다. 모르는 글자는 원문 그대로
    assert Normalizer("LI2CO3").map(raw).name == raw


@pytest.mark.parametrize("raw", [
    # 서버 Na+K 합산 규칙(#27)은 normalized_name 이 'Na+K' 인 줄에만 적용된다
    "Na+K", "Na + K", "K+Na", "Sodium + Potassium", "Sodium + Potassium (Na+K)", "Sodium and Potassium (Na+K)",
    "Potassium + Sodium", "钠+钾", "钾+钠", "钠+钾 Na+K", "Na+K (ppm)", "Na+K content",
    "钾钠合量Na+K", "钾钠合量",  # 생성기 v2 양식 B
])
def test_na_k_sum_line(raw):
    m = Normalizer("LI2CO3").map(raw)
    assert (m.name, m.source) == ("Na+K", "dictionary")


@pytest.mark.parametrize("raw, expected", [("Sodium (Na)", "Na"), ("钠 Na", "Na"), ("钠", "Na"), ("Potassium", "K"), ("钾K", "K")])
def test_single_elements_stay_elements(raw, expected):
    assert Normalizer("LI2CO3").map(raw).name == expected
