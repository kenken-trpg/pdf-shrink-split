"""細工されたコンテンツストリームで処理が止まらないことのテスト

PyPDF2 3.0.1 は、改行なしのコメントで終わるコンテンツストリームを読むと
無限ループに陥っていた（CVE-2023-36464）。公開しているWeb版は誰でもPDFを
アップロードできるため、pypdf から戻してしまった場合に検知できるようにする。
"""
import pikepdf
import pytest
from pikepdf import Array, Dictionary, Name


def build_comment_terminated_pdf(path):
    """コンテンツストリームが改行なしのコメントで終わるPDFを作る"""
    pdf = pikepdf.Pdf.new()
    font = pdf.make_indirect(Dictionary(
        Type=Name.Font, Subtype=Name.Type1, BaseFont=Name.Helvetica))
    content = b"BT /F1 12 Tf 40 700 Td (Hello) Tj ET\n%comment"
    pdf.pages.append(pikepdf.Page(pdf.make_indirect(Dictionary(
        Type=Name.Page, MediaBox=Array([0, 0, 612, 792]),
        Resources=Dictionary(Font=Dictionary(F1=font)),
        Contents=pdf.make_stream(content)))))
    pdf.save(path)
    return str(path)


@pytest.mark.timeout(15)
def test_cli_finishes_on_unterminated_comment(cli, tmp_path):
    src = build_comment_terminated_pdf(tmp_path / "comment.pdf")

    assert len(cli.split_and_process_pdf(src)) == 1


@pytest.mark.timeout(15)
def test_app_finishes_on_unterminated_comment(app, uploaded, tmp_path):
    src = build_comment_terminated_pdf(tmp_path / "comment.pdf")

    result = app["split_and_process_pdf"](uploaded(src))

    assert result["total_chars"] == len("Hello")
