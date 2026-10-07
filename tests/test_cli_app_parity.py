"""CLI版とStreamlit版が同じ結果を出すことのテスト

同じ処理ロジックが2ファイルに重複して存在するため、
片方だけ直して食い違う事故を検知する。
"""
import os

from pdf_fixtures import build_pdf


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
        assert open(cli_path, "rb").read() == app_file["bytes"], (
            f"{app_file['name']} の内容がCLI版とStreamlit版で一致しません")


def test_both_expose_the_same_helpers(cli, app):
    """両方に同じ処理関数が存在する"""
    for name in ("strip_images_from_resources", "clean_page",
                 "count_characters_per_page", "split_and_process_pdf"):
        assert hasattr(cli, name), f"CLI版に {name} がありません"
        assert name in app, f"Streamlit版に {name} がありません"
