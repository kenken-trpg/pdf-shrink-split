"""インライン画像(BI...EI)の削除のテスト

XObjectと違ってコンテンツストリームに直接書かれているため、ストリームを
書き換えて削除する。本文を巻き添えにしないことも合わせて確認する。
"""
import io
import os

import pikepdf
import pytest
from pypdf import PdfReader

from pdf_fixtures import (INLINE_LOCATIONS, RULE_INLINE_IMAGES,
                          build_inline_pdf, count_inline_images,
                          without_file_id)


def inline_images_in(result):
    total = 0
    for out in result["files"]:
        with pikepdf.open(io.BytesIO(out["bytes"])) as pdf:
            total += count_inline_images(pdf)
    return total


def extracted_chars(result):
    total = 0
    for out in result["files"]:
        reader = PdfReader(io.BytesIO(out["bytes"]))
        total += sum(len(p.extract_text() or "") for p in reader.pages)
    return total


def page_content(out):
    with pikepdf.open(io.BytesIO(out["bytes"])) as pdf:
        page = pdf.pages[0]
        page.contents_coalesce()
        return page.Contents.read_bytes()


def test_fixture_has_inline_images_everywhere(tmp_path):
    """検体に想定どおりの場所と数のインライン画像が入っている"""
    path = build_inline_pdf(tmp_path / "all.pdf")
    assert count_inline_images(path) == len(INLINE_LOCATIONS)


@pytest.mark.parametrize("location", INLINE_LOCATIONS)
def test_inline_image_is_removed(app, uploaded, tmp_path, location):
    path = build_inline_pdf(tmp_path / "one.pdf", locations=(location,))
    assert count_inline_images(path) == 1

    result = app["split_and_process_pdf"](uploaded(path))

    assert result["removed_images"] == 1
    assert inline_images_in(result) == 0


def test_all_locations_reduce_size_and_keep_text(app, uploaded, tmp_path):
    path = build_inline_pdf(tmp_path / "all.pdf")

    result = app["split_and_process_pdf"](uploaded(path))

    assert result["removed_images"] == len(INLINE_LOCATIONS)
    assert result["output_size"] < result["original_size"] / 10
    assert extracted_chars(result) == result["total_chars"] > 0


def test_contents_array_is_handled(app, uploaded, tmp_path):
    """/Contents が配列でも削除でき、q と Q の対応も壊れない"""
    path = build_inline_pdf(tmp_path / "array.pdf", locations=("page",),
                            split_contents=True)

    result = app["split_and_process_pdf"](uploaded(path))
    content = page_content(result["files"][0])

    assert result["removed_images"] == 1
    assert inline_images_in(result) == 0
    assert b"(ID and BI and EI)" in content
    assert content.count(b"q") >= 1


def test_text_resembling_operators_is_not_touched(app, uploaded, tmp_path):
    """本文中の ID や BI は演算子として扱わない"""
    path = build_inline_pdf(tmp_path / "text.pdf", locations=())

    result = app["split_and_process_pdf"](uploaded(path))

    assert result["removed_images"] == 0
    assert extracted_chars(result) == result["total_chars"] > 0
    assert b"(ID and BI and EI)" in page_content(result["files"][0])


def test_type3_glyphs_are_preserved(app, uploaded, tmp_path):
    """Type 3フォントのグリフは本文の一部なので削除しない"""
    path = build_inline_pdf(tmp_path / "type3.pdf", locations=("page",),
                            type3=True)
    assert count_inline_images(path) == 2

    result = app["split_and_process_pdf"](uploaded(path))

    # ページ本体の1個だけが消え、グリフの1個は残る
    assert result["removed_images"] == 1
    assert inline_images_in(result) == 1


@pytest.mark.parametrize("name", RULE_INLINE_IMAGES)
def test_rules_and_stencils_are_preserved(app, uploaded, tmp_path, name):
    """罫線や字形を描くインライン画像は、写真ではないので削除しない

    抽出テキストには現れないため、消えても字数の比較では検知できない。
    """
    path = build_inline_pdf(tmp_path / "rule.pdf", locations=(),
                            trailer=RULE_INLINE_IMAGES[name])

    result = app["split_and_process_pdf"](uploaded(path))

    assert result["removed_images"] == 0
    assert inline_images_in(result) == 1


def test_rules_survive_rewriting_the_stream(app, uploaded, tmp_path):
    """写真を削除してストリームを書き換えても、同じページの罫線は残る"""
    rules = b"".join(RULE_INLINE_IMAGES.values())
    path = build_inline_pdf(tmp_path / "mixed.pdf", locations=("page",),
                            trailer=rules)

    result = app["split_and_process_pdf"](uploaded(path))

    assert result["removed_images"] == 1
    assert inline_images_in(result) == len(RULE_INLINE_IMAGES)
    assert extracted_chars(result) == result["total_chars"] > 0


@pytest.mark.parametrize("broken", [b"BT (unterminated ", b"<< /a ", b"[ (a) "])
def test_broken_stream_is_left_untouched(app, uploaded, tmp_path, broken):
    """解析が途中で止まるストリームを書き戻して本文を失わない

    pikepdf は例外を出さず途中までの命令を返すため、そのまま書き戻すと
    壊れた箇所より後ろの本文が消えてしまう。
    pypdf はこのページを0字と数えるため、force で安全弁を通過させる。
    """
    after = b"BT /F1 12 Tf 40 500 Td (After) Tj ET\n"
    path = build_inline_pdf(tmp_path / "broken.pdf", locations=("page",),
                            trailer=broken + after)

    result = app["split_and_process_pdf"](uploaded(path), 100000, True)

    assert result["removed_images"] == 0
    assert b"(After)" in page_content(result["files"][0])


def test_shared_form_is_counted_once(app, uploaded, tmp_path):
    """複数ページで共有するFormの画像は1個として数える"""
    path = build_inline_pdf(tmp_path / "shared.pdf", locations=("form",),
                            pages=3, shared_form=True)
    assert count_inline_images(path) == 1

    result = app["split_and_process_pdf"](uploaded(path))

    assert result["removed_images"] == 1
    assert inline_images_in(result) == 0


def test_split_output_has_no_inline_images(app, uploaded, tmp_path):
    path = build_inline_pdf(tmp_path / "split.pdf", pages=3)

    result = app["split_and_process_pdf"](uploaded(path), 1)

    assert len(result["files"]) == 3
    assert result["removed_images"] == 3 * len(INLINE_LOCATIONS)
    assert inline_images_in(result) == 0


def test_processing_output_again_finds_nothing(app, uploaded, tmp_path):
    path = build_inline_pdf(tmp_path / "again.pdf")
    first = app["split_and_process_pdf"](uploaded(path))

    again = tmp_path / "output.pdf"
    again.write_bytes(first["files"][0]["bytes"])
    second = app["split_and_process_pdf"](uploaded(again))

    assert second["removed_images"] == 0


def test_non_stream_pattern_is_ignored(app):
    """シェーディングパターンのようにストリームでないものは対象外"""
    assert app["strip_inline_images"](pikepdf.Dictionary()) == 0


def test_same_bytes_as_cli(cli, app, uploaded, tmp_path):
    """インライン画像の削除でもCLI版とStreamlit版の出力が一致する"""
    src = build_inline_pdf(tmp_path / "parity.pdf", pages=2, type3=True)
    app_result = app["split_and_process_pdf"](uploaded(src), 1)

    cli_dir = tmp_path / "cli"
    cli_dir.mkdir()
    cli_src = cli_dir / "parity.pdf"
    cli_src.write_bytes(open(src, "rb").read())
    cli_outputs = cli.split_and_process_pdf(str(cli_src), 1)

    assert len(cli_outputs) == len(app_result["files"]) == 2
    for cli_path, app_file in zip(cli_outputs, app_result["files"]):
        assert os.path.basename(cli_path) == app_file["name"]
        cli_bytes = without_file_id(open(cli_path, "rb").read())
        assert cli_bytes == without_file_id(app_file["bytes"])
