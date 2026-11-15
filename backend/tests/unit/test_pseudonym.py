"""[담당: 홍채령] 가명 처리 테스트 (운영 정책 3장, app/services/pseudonym.py). DB 없이."""
from types import SimpleNamespace

from app.services.pseudonym import Pseudonymizer, letters


def person(uid, name):
    return SimpleNamespace(id=uid, name=name)


def test_letters():
    assert [letters(n) for n in (0, 1, 25, 26, 27, 51, 52)] == ["A", "B", "Z", "AA", "AB", "AZ", "BA"]


def test_disabled_keeps_names():
    p = Pseudonymizer(enabled=False)
    assert p.user(person(1, "김검수")) == "김검수"
    assert p.text("김검수 확인") == "김검수 확인"
    assert p.user(None) is None


def test_stable_alias_in_order_of_appearance():
    p = Pseudonymizer()
    kim, lee = person(7, "김검수"), person(3, "이처분")
    assert p.user(kim) == "담당자 A"
    assert p.user(lee) == "담당자 B"
    assert p.user(kim) == "담당자 A"  # 같은 사람은 같은 가명


def test_names_in_free_text_replaced_longest_first():
    p = Pseudonymizer()
    p._names = {1: "김검", 2: "김검수"}  # DB 에서 읽은 등록 사용자 (긴 이름이 짧은 이름을 품는 경우)
    assert p.text("김검수님 확인 후 김검 재확인") == "담당자 A님 확인 후 담당자 B 재확인"
    assert p.text(None) is None


def test_single_letter_names_not_replaced_in_text():
    p = Pseudonymizer()
    p._names = {1: "김"}
    assert p.text("김치 공장") == "김치 공장"
