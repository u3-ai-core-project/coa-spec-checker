"""[담당: 고도영] OCR 글줄(픽셀 좌표) → Page 변환"""
import math

import pytest

from coa_ai.ocr import estimate_dpi, ocr_to_page


def rect(x0, y0, x1, y1):
    """OCR 이 내는 네 꼭짓점 (왼쪽 위부터 시계 방향)."""
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def rotate(box, deg, cx=0.0, cy=0.0):
    a = math.radians(deg)
    return [(cx + (x - cx) * math.cos(a) - (y - cy) * math.sin(a),
             cy + (x - cx) * math.sin(a) + (y - cy) * math.cos(a)) for x, y in box]


def test_boxes_on_same_row_become_one_line_in_points():
    boxes = [rect(100, 100, 300, 130), rect(600, 102, 700, 131), rect(100, 200, 260, 230)]
    page = ocr_to_page(boxes, ["Sodium (Na)", "< 10 ppm", "Potassium"], dpi=144, size_px=(1190, 1684), page_no=2)
    assert [[w.text for w in ln.words] for ln in page.lines] == [["Sodium", "(Na)", "<", "10", "ppm"], ["Potassium"]]
    assert (page.number, page.width, page.height) == (2, 595, 842)  # 144 dpi → 픽셀 × 0.5 = pt
    assert all(ln.page == 2 for ln in page.lines)
    first = page.lines[0].words[0].box
    assert (first.x0, first.y0) == pytest.approx((50, 50))


def test_skewed_scan_is_straightened():
    boxes = [rotate(rect(100, 500, 400, 530), 2, 800, 800), rotate(rect(900, 500, 1100, 530), 2, 800, 800)]
    page = ocr_to_page(boxes, ["Sodium (Na)", "< 10 ppm"], dpi=200, size_px=(1654, 2339))
    assert len(page.lines) == 1
    assert page.skew == pytest.approx(math.radians(2), abs=1e-6)


def test_straightened_box_maps_back_to_image_position():
    """바로 세운 좌표의 상자를 원본 이미지 좌표로 되돌린다 (화면의 근거 위치 표시용)."""
    original = rotate(rect(900, 1500, 1100, 1530), 2, 800, 800)
    page = ocr_to_page([rotate(rect(100, 1500, 600, 1530), 2, 800, 800), original], ["Sodium (Na)", "< 10 ppm"],
                       dpi=72, size_px=(1654, 2339))
    box = page.to_image_box(page.lines[0].words[-1].box)  # "ppm"
    xs, ys = [p[0] for p in original], [p[1] for p in original]
    assert box.x1 == pytest.approx(max(xs), abs=3) and box.y1 == pytest.approx(max(ys), abs=3)


def test_empty_text_is_skipped():
    page = ocr_to_page([rect(0, 0, 10, 10)], ["  "], dpi=200, size_px=(1654, 2339))
    assert page.lines == [] and page.width == pytest.approx(1654 * 72 / 200)


@pytest.mark.parametrize("width_px, dpi", [(1654, 200), (827, 100), (2480, 300)])
def test_dpi_is_estimated_from_a4_width(width_px, dpi):
    assert estimate_dpi(width_px) == pytest.approx(dpi, rel=0.01)
