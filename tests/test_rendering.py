"""処理前後の描画を画素単位で比較するテスト

表の罫線や分数の横棒、グラフの軸の目盛りは抽出テキストに現れないため、
字数の比較では消えても気づけない。実際に描画して見た目を確かめる。
"""
import io

import pikepdf
import pypdfium2
import pytest
from PIL import ImageChops

from pdf_fixtures import (IMAGE_BOX, RULE_INLINE_IMAGES, build_image_xobject_pdf,
                          build_inline_pdf, count_image_streams)

PAGE_HEIGHT = 792


def render(data):
    """PDFのバイト列を、ページごとの画像のリストにする"""
    document = pypdfium2.PdfDocument(data)
    return [page.render(scale=1).to_pil().convert("RGB") for page in document]


def render_output(result):
    """分割された出力も含めて、全ページを順に描画する"""
    pages = []
    for out in result["files"]:
        pages.extend(render(out["bytes"]))
    return pages


def changed_area(before, after):
    """2枚の画像で変化した範囲を返す。同じなら None"""
    return ImageChops.difference(before, after).getbbox()


def image_area():
    """IMAGE_BOX を、描画した画像の座標（左上原点）にする"""
    left, bottom, right, top = IMAGE_BOX
    return left, PAGE_HEIGHT - top, right, PAGE_HEIGHT - bottom


def assert_renders_identically(source_path, result):
    source = render(open(source_path, "rb").read())
    output = render_output(result)

    assert len(source) == len(output)
    for number, (before, after) in enumerate(zip(source, output), start=1):
        assert changed_area(before, after) is None, (
            f"{number}ページ目の描画が変わっています")


def assert_only_image_area_changed(source_path, result):
    source = render(open(source_path, "rb").read())
    output = render_output(result)
    left, top, right, bottom = image_area()

    assert len(source) == len(output)
    for before, after in zip(source, output):
        area = changed_area(before, after)
        assert area is not None, "画像が消えていません"
        # 画像の縁のアンチエイリアスで1画素はみ出すことがある
        assert (area[0] >= left - 1 and area[1] >= top - 1
                and area[2] <= right + 1 and area[3] <= bottom + 1), (
            f"画像の範囲外が変わっています: {area}")


def test_comparison_detects_a_missing_rule(tmp_path):
    """比較の仕組み自体が、罫線の欠けを検知できる"""
    with_rule = build_inline_pdf(
        tmp_path / "with.pdf", locations=(),
        trailer=RULE_INLINE_IMAGES["one_pixel_stencil"])
    without_rule = build_inline_pdf(tmp_path / "without.pdf", locations=())

    before = render(open(with_rule, "rb").read())[0]
    after = render(open(without_rule, "rb").read())[0]

    assert changed_area(before, after) is not None


@pytest.mark.parametrize("name", RULE_INLINE_IMAGES)
def test_inline_rules_render_identically(app, uploaded, tmp_path, name):
    path = build_inline_pdf(tmp_path / "rule.pdf", locations=(),
                            trailer=RULE_INLINE_IMAGES[name])

    assert_renders_identically(path, app["split_and_process_pdf"](uploaded(path)))


@pytest.mark.parametrize("width, height, stencil", [
    (1, 1, False),      # 塗りつぶしの矩形として描かれる1画素の画像
    (1, 1, True),
    (23, 615, True),    # 実際のPDFでグラフの軸の目盛りを描いていた寸法
    (16, 16, True),
])
def test_xobject_rules_render_identically(app, uploaded, tmp_path,
                                          width, height, stencil):
    path = build_image_xobject_pdf(tmp_path / "rule.pdf", width, height, stencil)

    result = app["split_and_process_pdf"](uploaded(path))

    assert result["removed_images"] == 0
    assert_renders_identically(path, result)


def test_rules_render_identically_after_split(app, uploaded, tmp_path):
    rules = b"".join(RULE_INLINE_IMAGES.values())
    path = build_inline_pdf(tmp_path / "split.pdf", locations=(), pages=3,
                            trailer=rules)

    result = app["split_and_process_pdf"](uploaded(path), 1)

    assert len(result["files"]) == 3
    assert_renders_identically(path, result)


def test_removing_inline_photo_changes_only_its_area(app, uploaded, tmp_path):
    rules = b"".join(RULE_INLINE_IMAGES.values())
    path = build_inline_pdf(tmp_path / "photo.pdf", locations=("page",),
                            trailer=rules)

    result = app["split_and_process_pdf"](uploaded(path))

    assert result["removed_images"] == 1
    assert_only_image_area_changed(path, result)


def test_removing_xobject_photo_changes_only_its_area(app, uploaded, tmp_path):
    path = build_image_xobject_pdf(tmp_path / "photo.pdf", 120, 120)

    result = app["split_and_process_pdf"](uploaded(path))

    assert result["removed_images"] == 1
    assert_only_image_area_changed(path, result)


def test_stencil_at_the_size_limit_is_kept(cli, app, uploaded, tmp_path):
    side = int(cli.STENCIL_MAX_PIXELS ** 0.5)
    path = build_image_xobject_pdf(tmp_path / "edge.pdf", side, side, True)

    result = app["split_and_process_pdf"](uploaded(path))

    assert result["removed_images"] == 0


def test_large_stencil_is_removed(app, uploaded, tmp_path):
    """スキャン由来の文字画像のような大きなImageMaskは軽量化の対象"""
    path = build_image_xobject_pdf(tmp_path / "scan.pdf", 1000, 1000, True)

    result = app["split_and_process_pdf"](uploaded(path))

    assert result["removed_images"] == 1
    with pikepdf.open(io.BytesIO(result["files"][0]["bytes"])) as pdf:
        assert count_image_streams(pdf) == 0
