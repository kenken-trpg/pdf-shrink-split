"""テキストを持たないPDFに対する安全弁のテスト

スキャンした画像だけのPDFは、画像を削除すると中身が失われる。
黙って空のPDFを返さないことを確認する。
"""
import pytest

from pdf_fixtures import build_pdf


def test_textless_pdf_is_rejected(app, uploaded, tmp_path):
    """1字も抽出できないPDFは例外になり、空のPDFを返さない"""
    path = build_pdf(tmp_path / "scanned.pdf", pages=3, empty_pages=3)

    with pytest.raises(app["TextlessPdfError"]):
        app["split_and_process_pdf"](uploaded(path), 100000)


def test_textless_pdf_can_be_forced(app, uploaded, tmp_path):
    """force=True なら処理を続行できる"""
    path = build_pdf(tmp_path / "scanned.pdf", pages=3, empty_pages=3)

    result = app["split_and_process_pdf"](uploaded(path), 100000, force=True)

    assert result["total_chars"] == 0
    assert result["files"]
    # 続行した場合も警告は残す
    assert result["warnings"]


def test_error_message_mentions_page_count(app, uploaded, tmp_path):
    path = build_pdf(tmp_path / "scanned.pdf", pages=4, empty_pages=4)

    with pytest.raises(app["TextlessPdfError"]) as excinfo:
        app["split_and_process_pdf"](uploaded(path), 100000)

    assert excinfo.value.total_pages == 4
    assert "4" in str(excinfo.value)


def test_partially_textless_pdf_warns_but_proceeds(app, uploaded, tmp_path):
    """半分以上のページにテキストがない場合は警告しつつ処理する"""
    path = build_pdf(tmp_path / "mixed.pdf", pages=4, empty_pages=3)

    result = app["split_and_process_pdf"](uploaded(path), 100000)

    assert result["files"], "処理は続行されるべき"
    assert result["total_chars"] > 0
    assert len(result["warnings"]) == 1
    assert "3" in result["warnings"][0]


def test_mostly_text_pdf_has_no_warning(app, uploaded, tmp_path):
    """テキストのないページが少数なら警告しない"""
    path = build_pdf(tmp_path / "ok.pdf", pages=4, empty_pages=1)

    result = app["split_and_process_pdf"](uploaded(path), 100000)

    assert result["warnings"] == []


def test_check_text_coverage_thresholds(app):
    """しきい値の境界を直接確認する"""
    check = app["check_text_coverage"]

    # ちょうど半分 -> 警告する
    assert check([0, 0, 10, 10])
    # 半分未満 -> 警告しない
    assert check([0, 10, 10, 10]) == []
    # テキストが全くない -> 例外
    with pytest.raises(app["TextlessPdfError"]):
        check([0, 0, 0])
    # force指定時は例外にならず警告だけ返る
    assert check([0, 0, 0], force=True)
    # 空のPDF（ページ0枚）では例外にしない
    assert check([]) == []


def test_cli_rejects_textless_pdf(cli, tmp_path):
    """CLI版も同じ安全弁を持つ"""
    path = build_pdf(tmp_path / "scanned.pdf", pages=2, empty_pages=2)

    with pytest.raises(cli.TextlessPdfError):
        cli.split_and_process_pdf(str(path), 100000)

    outputs = cli.split_and_process_pdf(str(path), 100000, force=True)
    assert outputs


def test_cli_writes_no_files_when_rejected(cli, tmp_path):
    """拒否されたときに出力ファイルを作らない（空PDFを置き残さない）"""
    src = tmp_path / "scanned.pdf"
    build_pdf(src, pages=2, empty_pages=2)
    before = sorted(p.name for p in tmp_path.iterdir())

    with pytest.raises(cli.TextlessPdfError):
        cli.split_and_process_pdf(str(src), 100000)

    assert sorted(p.name for p in tmp_path.iterdir()) == before
