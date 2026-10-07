"""画像削除の回帰テスト

ページ直下の /Resources/XObject しか見ていなかった実装では、
入れ子に置かれた画像が1枚も削除されずファイルに残っていた。
ここではその状態に戻っていないことを確認する。
"""
import pikepdf
import pytest
from PyPDF2 import PdfReader

from pdf_fixtures import build_pdf, count_image_streams


@pytest.fixture
def nested_pdf(tmp_path):
    return build_pdf(tmp_path / "nested.pdf", pages=3)


def _outputs(app, uploaded, path, char_limit=100000):
    result = app["split_and_process_pdf"](uploaded(path), char_limit)
    return result


def test_fixture_actually_hides_images_in_nested_places(nested_pdf):
    """検体が「入れ子にしか画像がない」状態になっていることの確認

    このテスト自体が壊れていると回帰テストが無意味になるため、
    検体側も検証しておく。
    """
    with pikepdf.open(nested_pdf) as pdf:
        total = count_image_streams(pdf)
        page_level = 0
        for page in pdf.pages:
            xobjects = page.Resources.get("/XObject")
            for name in xobjects.keys():
                if str(xobjects[name].get("/Subtype")) == "/Image":
                    page_level += 1

    assert total == 21, "検体の画像枚数が変わりました"
    # ページ直下は3枚だけで、残り18枚は入れ子の中にある
    assert page_level == 3
    assert total - page_level == 18


def test_no_images_remain_in_output(app, uploaded, nested_pdf):
    """出力PDFに画像ストリームが1つも残らない"""
    result = _outputs(app, uploaded, nested_pdf)

    assert result["files"], "出力ファイルが生成されていません"
    for out in result["files"]:
        remaining = count_image_streams_bytes(out["bytes"])
        assert remaining == 0, (
            f"{out['name']} に画像が {remaining} 個残っています")


def count_image_streams_bytes(data):
    import io
    with pikepdf.open(io.BytesIO(data)) as pdf:
        return count_image_streams(pdf)


def test_removed_images_is_reported(app, uploaded, nested_pdf):
    """削除枚数が実際の枚数として報告される"""
    result = _outputs(app, uploaded, nested_pdf)
    # Thumb は参照ごと削除されるため削除カウントには含まれない
    assert result["removed_images"] >= 18


def test_piece_info_is_removed(app, uploaded, nested_pdf):
    """/PieceInfo と /Thumb が残らない"""
    import io
    result = _outputs(app, uploaded, nested_pdf)
    for out in result["files"]:
        with pikepdf.open(io.BytesIO(out["bytes"])) as pdf:
            for page in pdf.pages:
                assert "/PieceInfo" not in page
                assert "/Thumb" not in page


def test_text_is_preserved(app, uploaded, nested_pdf):
    """テキストの抽出字数が入力と一致する"""
    import io
    result = _outputs(app, uploaded, nested_pdf)

    out_chars = 0
    for out in result["files"]:
        reader = PdfReader(io.BytesIO(out["bytes"]))
        out_chars += sum(len(p.extract_text() or "") for p in reader.pages)

    assert out_chars == result["total_chars"]


def test_output_is_smaller(app, uploaded, nested_pdf):
    """出力が入力より小さくなる"""
    result = _outputs(app, uploaded, nested_pdf)
    assert result["output_size"] < result["original_size"]


def test_output_is_valid_pdf(app, uploaded, nested_pdf):
    """出力PDFのcontent streamが解析できる（壊れたPDFを吐いていない）"""
    import io
    result = _outputs(app, uploaded, nested_pdf)
    for out in result["files"]:
        with pikepdf.open(io.BytesIO(out["bytes"])) as pdf:
            for page in pdf.pages:
                pikepdf.parse_content_stream(page)


def test_pdf_without_images_still_works(app, uploaded, tmp_path):
    """画像がないPDFでも例外にならない"""
    path = build_pdf(tmp_path / "plain.pdf", pages=1,
                     nested=False, piece_info=False)
    result = _outputs(app, uploaded, path)
    assert len(result["files"]) == 1
    assert result["total_chars"] > 0


def test_document_level_cruft_is_removed(app, uploaded, nested_pdf):
    """文書レベルの /Metadata /PieceInfo /StructTreeRoot が残らない"""
    import io
    result = _outputs(app, uploaded, nested_pdf)
    for out in result["files"]:
        with pikepdf.open(io.BytesIO(out["bytes"])) as pdf:
            for key in ("/Metadata", "/PieceInfo", "/StructTreeRoot"):
                assert key not in pdf.Root, f"{out['name']} に {key} が残存"
