"""ページ分割と、1ページで字数制限を超える場合の警告のテスト

分割はページ単位なので、1ページで字数制限を超えるページを含むファイルは
制限を超える。翻訳サービスなどに渡す前に気づけるよう、警告で知らせる。
"""
import pytest

from pdf_fixtures import build_pdf


@pytest.mark.parametrize("counts, limit, expected", [
    ([], 100, []),
    ([10, 20], 100, [[0, 1]]),
    ([60, 60, 60], 100, [[0], [1], [2]]),
    ([50, 50, 1], 100, [[0, 1], [2]]),
    ([500, 10], 100, [[0], [1]]),
    ([10, 500, 10], 100, [[0], [1], [2]]),
])
def test_group_pages_by_chars(cli, counts, limit, expected):
    assert cli.group_pages_by_chars(counts, limit) == expected


def test_no_warning_when_every_page_fits(cli):
    assert cli.check_page_limit([100, 99], 100) == []


def test_warning_names_the_oversized_page(cli):
    warnings = cli.check_page_limit([10, 120000, 10], 100000)

    assert len(warnings) == 1
    assert "2ページ目（120,000字）" in warnings[0]
    assert "100,000字" in warnings[0]


def test_warning_shortens_a_long_list_of_pages(cli):
    limit = 100
    counts = [200] * (cli.MAX_LISTED_PAGES + 2)

    warning = cli.check_page_limit(counts, limit)[0]

    assert f"{cli.MAX_LISTED_PAGES}ページ目" in warning
    assert f"{cli.MAX_LISTED_PAGES + 1}ページ目" not in warning
    assert "ほか2ページ" in warning


def test_app_reports_oversized_page(app, uploaded, tmp_path):
    path = build_pdf(tmp_path / "big.pdf", pages=2)

    result = app["split_and_process_pdf"](uploaded(path), 100)

    assert any("字数制限" in warning for warning in result["warnings"])


def test_app_has_no_warning_within_limit(app, uploaded, tmp_path):
    path = build_pdf(tmp_path / "small.pdf", pages=2)

    result = app["split_and_process_pdf"](uploaded(path))

    assert result["warnings"] == []


def test_cli_prints_oversized_page(cli, tmp_path, capsys):
    path = build_pdf(tmp_path / "big.pdf", pages=2)

    cli.split_and_process_pdf(path, 100)

    assert "1ページで字数制限" in capsys.readouterr().out


def test_every_part_over_the_limit_is_reported(app, uploaded, tmp_path):
    """制限を超えるファイルが、警告なしに出力されることはない"""
    path = build_pdf(tmp_path / "parts.pdf", pages=4)

    for limit in (100, 959, 960, 961, 1500, 2000):
        result = app["split_and_process_pdf"](uploaded(path), limit)
        over_limit = [f for f in result["files"] if f["chars"] > limit]

        assert bool(over_limit) == any(
            "字数制限" in warning for warning in result["warnings"]), limit
        assert all(f["pages"] == 1 for f in over_limit)
