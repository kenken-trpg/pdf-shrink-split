"""CLI版とStreamlit版が同じ結果を出すことのテスト

処理の本体はCLI版にあり、Web版はそれを読み込んで使う。入出力の扱いは
それぞれ別に書いているため、結果が食い違わないことを確かめる。
"""
import os

from conftest import APP_PATH
from pdf_fixtures import build_pdf, without_file_id


def test_same_bytes_as_cli(cli, app, uploaded, tmp_path):
    src = build_pdf(tmp_path / "parity.pdf", pages=4)

    app_result = app["split_and_process_pdf"](uploaded(src), 1500)

    cli_dir = tmp_path / "cli"
    cli_dir.mkdir()
    cli_src = cli_dir / "parity.pdf"
    cli_src.write_bytes(open(src, "rb").read())
    cli_outputs = cli.split_and_process_pdf(str(cli_src), 1500)

    assert len(cli_outputs) == len(app_result["files"])

    for cli_path, app_file in zip(cli_outputs, app_result["files"]):
        assert os.path.basename(cli_path) == app_file["name"]
        cli_bytes = without_file_id(open(cli_path, "rb").read())
        assert cli_bytes == without_file_id(app_file["bytes"]), (
            f"{app_file['name']} の内容がCLI版とStreamlit版で一致しません")


def test_app_does_not_duplicate_processing(cli):
    """Web版に処理の定義を置かず、CLI版の1か所だけで管理する"""
    source = open(APP_PATH, encoding="utf-8").read()
    for name in ("strip_images_from_resources", "strip_inline_images",
                 "clean_page", "count_characters_per_page",
                 "check_text_coverage", "group_pages_by_chars",
                 "write_cleaned_pdf"):
        assert hasattr(cli, name), f"CLI版に {name} がありません"
        assert f"def {name}(" not in source, (
            f"Web版に {name} の定義が重複しています")
