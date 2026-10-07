"""字数制限による分割ロジックのテスト"""
import pytest

from pdf_fixtures import build_pdf


def test_single_file_when_within_limit(app, uploaded, tmp_path):
    path = build_pdf(tmp_path / "small.pdf", pages=2)
    result = app["split_and_process_pdf"](uploaded(path), 100000)

    assert len(result["files"]) == 1
    assert result["files"][0]["name"].endswith("_no_images.pdf")
    assert result["files"][0]["pages"] == 2


def test_splits_when_over_limit(app, uploaded, tmp_path):
    path = build_pdf(tmp_path / "big.pdf", pages=6)
    # 1ページ約960字なので、1500字で区切れば複数に分かれる
    result = app["split_and_process_pdf"](uploaded(path), 1500)

    assert len(result["files"]) > 1
    names = [f["name"] for f in result["files"]]
    assert names == [f"big_part{i+1}.pdf" for i in range(len(names))]


def test_all_pages_are_kept(app, uploaded, tmp_path):
    """分割してもページが落ちたり重複したりしない"""
    path = build_pdf(tmp_path / "pages.pdf", pages=7)
    result = app["split_and_process_pdf"](uploaded(path), 1500)

    assert sum(f["pages"] for f in result["files"]) == result["total_pages"]
    assert result["total_pages"] == 7


def test_chars_add_up(app, uploaded, tmp_path):
    path = build_pdf(tmp_path / "chars.pdf", pages=5)
    result = app["split_and_process_pdf"](uploaded(path), 1500)

    assert sum(f["chars"] for f in result["files"]) == result["total_chars"]


def test_each_part_respects_limit(app, uploaded, tmp_path):
    """1ページが単独で制限を超える場合を除き、各パートは制限内に収まる"""
    path = build_pdf(tmp_path / "limit.pdf", pages=5)
    limit = 2000
    result = app["split_and_process_pdf"](uploaded(path), limit)

    for f in result["files"]:
        # 単一ページで制限超過する場合はそのページだけで1パートになる
        assert f["chars"] <= limit or f["pages"] == 1


def test_single_page_over_limit_is_not_dropped(app, uploaded, tmp_path):
    """1ページだけで制限を超えても、そのページは出力される"""
    path = build_pdf(tmp_path / "one.pdf", pages=1)
    result = app["split_and_process_pdf"](uploaded(path), 10)

    assert result["total_pages"] == 1
    assert sum(f["pages"] for f in result["files"]) == 1
