"""テスト用のPDFを生成するヘルパー

リポジトリにバイナリを置かずに済むよう、必要なPDFはテスト実行時に組み立てる。
画像を「入れ子の奥」に置いた検体を作れることが重要で、ここが
過去に画像削除が機能していなかった原因そのものにあたる。
"""
import random
import re
import zlib

import pikepdf
from pikepdf import Array, Dictionary, Name, Stream

# 画像1枚あたりのバイト数を大きめにして、削除漏れがサイズに出るようにする
IMAGE_SIDE = 120

# インライン画像は圧縮が効かない乱数で作り、削除漏れがサイズに出るようにする
INLINE_SIDE = 60
# inline_image と build_image_xobject_pdf が画像を描く範囲（PDF座標、左下原点）
IMAGE_BOX = (100, 100, 200, 200)
INLINE_LOCATIONS = ("page", "form", "nested_form", "form_without_resources",
                    "soft_mask", "pattern", "annotation")


def without_file_id(data):
    """PDFのバイト列から /ID を取り除く

    /ID は保存時刻（秒）で変わるため、同じ内容でも保存が秒をまたぐと
    バイト列が一致しなくなる。内容を比較するときはこれを通す。
    """
    masked, count = re.subn(rb"/ID \[<[0-9a-f]+><[0-9a-f]+>\]", b"/ID []", data)
    assert count == 1, f"/ID が {count} 個見つかりました"
    return masked


def _image(pdf, seed=0):
    """非圧縮のRGB画像ストリームを作る"""
    data = bytes(((x * 7 + y * 13 + seed) % 256)
                 for y in range(IMAGE_SIDE) for x in range(IMAGE_SIDE)
                 for _ in range(3))
    return pdf.make_stream(data, Type=Name.XObject, Subtype=Name.Image,
                           Width=IMAGE_SIDE, Height=IMAGE_SIDE,
                           ColorSpace=Name.DeviceRGB, BitsPerComponent=8)


def _form(pdf, resources, content=b"q /Im0 Do Q"):
    """指定したResourcesを持つForm XObjectを作る

    content streamから実際に画像を描画しておくことが重要。描画していないと
    pikepdfのremove_unreferenced_resources()が未使用リソースとして
    勝手に取り除いてしまい、再帰削除が働いているかの検証にならない。
    """
    return pdf.make_stream(
        content, Type=Name.XObject, Subtype=Name.Form,
        BBox=Array([0, 0, 100, 100]), Resources=resources)


def build_pdf(path, pages=1, text_per_page="Hello PDF shrink split. ",
              nested=True, piece_info=True, empty_pages=0):
    """検証用PDFを生成して保存する

    empty_pages に枚数を指定すると、その枚数だけテキストのないページを作る。

    nested=True のとき、画像をページ直下だけでなく
    Form XObjectの入れ子・ソフトマスクグループ・パターン・注釈の外観の
    中にも配置する。
    """
    pdf = pikepdf.Pdf.new()
    font = pdf.make_indirect(Dictionary(
        Type=Name.Font, Subtype=Name.Type1, BaseFont=Name.Helvetica,
        Encoding=Name.WinAnsiEncoding))

    for page_num in range(pages):
        # empty_pages で指定した枚数は、テキストを持たない
        # （スキャン画像だけの）ページとして作る
        if page_num < empty_pages:
            text = ""
        else:
            text = (text_per_page * 40).strip()
        content = (f"BT /F1 12 Tf 40 700 Td ({text}) Tj ET\n"
                   "q /Im0 Do Q\n"
                   "q /GS0 gs /Fm0 Do Q\n"
                   "q /Pattern cs /P0 scn 0 0 10 10 re f Q\n"
                   ).encode("latin-1", "replace")

        resources = Dictionary(
            Font=Dictionary(F1=font),
            XObject=Dictionary(Im0=_image(pdf, page_num)),
        )

        if nested:
            # (a) Form XObject の中の画像（さらに二段の入れ子も作る）
            inner = _form(pdf, Dictionary(
                XObject=Dictionary(Im0=_image(pdf, page_num + 100))))
            resources.XObject.Fm0 = _form(pdf, Dictionary(
                XObject=Dictionary(Im0=_image(pdf, page_num + 200),
                                   Fm0=inner)),
                content=b"q /Im0 Do /Fm0 Do Q")

            # (b) ソフトマスクグループ (/ExtGState -> /SMask -> /G) の中の画像
            group = _form(pdf, Dictionary(
                XObject=Dictionary(Im0=_image(pdf, page_num + 300))))
            group.Group = Dictionary(S=Name.Transparency, Type=Name.Group)
            resources.ExtGState = Dictionary(
                GS0=Dictionary(Type=Name.ExtGState,
                               SMask=Dictionary(S=Name.Luminosity, G=group)),
                # /SMask が /None という名前オブジェクトのケースも混ぜる
                GS1=Dictionary(Type=Name.ExtGState, SMask=Name.None_),
            )

            # (c) パターンの中の画像
            pattern = _form(pdf, Dictionary(
                XObject=Dictionary(Im0=_image(pdf, page_num + 400))))
            pattern.PatternType = 1
            pattern.PaintType = 1
            pattern.TilingType = 1
            pattern.XStep = 10
            pattern.YStep = 10
            resources.Pattern = Dictionary(P0=pattern)

        page = Dictionary(
            Type=Name.Page, MediaBox=Array([0, 0, 612, 792]),
            Resources=resources, Contents=pdf.make_stream(content))

        if nested:
            # (d) 注釈の外観ストリームの中の画像
            appearance = _form(pdf, Dictionary(
                XObject=Dictionary(Im0=_image(pdf, page_num + 500))))
            page.Annots = Array([pdf.make_indirect(Dictionary(
                Type=Name.Annot, Subtype=Name.Square,
                Rect=Array([0, 0, 10, 10]),
                AP=Dictionary(N=appearance)))])

        if piece_info:
            # Photoshop/Illustrator が残す私的データ（実ファイルでは
            # これだけで数MBを占めることがある）
            blob = zlib.compress(b"P" * 400_000)
            page.PieceInfo = Dictionary(ClaudeTest=Dictionary(
                LastModified=pikepdf.String("D:20260101000000Z"),
                Private=pdf.make_stream(blob, Filter=Name.FlateDecode)))
            page.Thumb = _image(pdf, 999)

        pdf.pages.append(pikepdf.Page(pdf.make_indirect(page)))

    if piece_info:
        # 文書レベルの余剰データ（XMPメタデータ・構造ツリー・私的データ）
        # pikepdfが保存時に解析するため、妥当なXMPにしておく
        # （不正なXMPだと "Error occurred parsing XMP" が大量に出る）
        xmp = (b'<?xpacket begin="\xef\xbb\xbf" id="W5M0MpCehiHzreSzNTczkc9d"?>'
               b'<x:xmpmeta xmlns:x="adobe:ns:meta/">'
               b'<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
               b'<rdf:Description rdf:about="" '
               b'xmlns:dc="http://purl.org/dc/elements/1.1/">'
               b"<dc:title><rdf:Alt><rdf:li xml:lang=\"x-default\">"
               b"fixture</rdf:li></rdf:Alt></dc:title>"
               b"</rdf:Description></rdf:RDF></x:xmpmeta>"
               + b" " * 4000
               + b'<?xpacket end="w"?>')
        pdf.Root.Metadata = pdf.make_stream(
            xmp, Type=Name.Metadata, Subtype=Name.XML)
        pdf.Root.StructTreeRoot = Dictionary(
            Type=Name.StructTreeRoot,
            K=Array([Dictionary(Type=Name.StructElem, S=Name.P)] * 50))
        pdf.Root.PieceInfo = Dictionary(ClaudeTest=Dictionary(
            LastModified=pikepdf.String("D:20260101000000Z"),
            Private=pdf.make_stream(zlib.compress(b"R" * 200_000),
                                    Filter=Name.FlateDecode)))

    pdf.save(path)
    return str(path)


def inline_image(seed=0):
    """インライン画像(BI...EI)を描画するコンテンツを作る"""
    rng = random.Random(seed)
    data = bytes(rng.randrange(256) for _ in range(INLINE_SIDE ** 2 * 3))
    return (b"q 100 0 0 100 100 100 cm\n"
            + (f"BI /W {INLINE_SIDE} /H {INLINE_SIDE} /BPC 8 /CS /RGB "
               "/F /AHx ID\n").encode()
            + data.hex().encode() + b">\nEI\nQ\n")


# 写真ではなく本文の一部として描かれるインライン画像
# TeX系のPDFは表の罫線や分数の横棒を、1x1のImageMaskを引き伸ばして描く
RULE_INLINE_IMAGES = {
    "one_pixel_stencil": (b"q 200 0 0 1 100 400 cm\n"
                          b"BI /W 1 /H 1 /BPC 1 /IM true ID \x00 EI\nQ\n"),
    "one_pixel_gray": (b"q 200 0 0 1 100 420 cm\n"
                       b"BI /W 1 /H 1 /BPC 8 /CS /G ID \x00 EI\nQ\n"),
    "bitmap_glyph": (b"q 8 0 0 8 100 440 cm\n"
                     b"BI /W 8 /H 8 /BPC 1 /IM true ID "
                     + bytes(range(8)) + b" EI\nQ\n"),
}


def _type3_font(pdf):
    """字形をインライン画像で描くType 3フォントを作る"""
    glyph = pdf.make_stream(
        b"8 0 0 0 8 8 d1 8 0 0 8 0 0 cm "
        b"BI /W 1 /H 1 /BPC 1 /IM true ID \x00 EI\n")
    return pdf.make_indirect(Dictionary(
        Type=Name.Font, Subtype=Name.Type3, FontBBox=Array([0, 0, 8, 8]),
        FontMatrix=Array([1, 0, 0, 1, 0, 0]),
        CharProcs=Dictionary(a=glyph),
        Encoding=Dictionary(Type=Name.Encoding, Differences=Array([97, Name.a])),
        FirstChar=97, LastChar=97, Widths=Array([8])))


def build_inline_pdf(path, locations=INLINE_LOCATIONS, pages=1, type3=False,
                     shared_form=False, split_contents=False, trailer=b""):
    """インライン画像を指定した場所に置いた検証用PDFを生成して保存する

    locations には INLINE_LOCATIONS の要素を指定する。本文にはあえて
    インライン画像の演算子と同じ文字列を含め、誤検知しないことも確かめる。
    trailer を指定すると、ページのコンテンツの末尾に追加する。
    """
    pdf = pikepdf.Pdf.new()
    font = pdf.make_indirect(Dictionary(
        Type=Name.Font, Subtype=Name.Type1, BaseFont=Name.Helvetica,
        Encoding=Name.WinAnsiEncoding))
    shared = (_form(pdf, Dictionary(), content=inline_image(1))
              if shared_form else None)

    for page_num in range(pages):
        seed = (page_num + 1) * 10
        text = b"BT /F1 12 Tf 40 700 Td (ID and BI and EI) Tj ET\n"
        body = b""
        resources = Dictionary(Font=Dictionary(F1=font))
        xobjects = Dictionary()
        annots = Array()

        if "page" in locations:
            body += inline_image(seed)
        if "form" in locations:
            xobjects.Fm0 = shared if shared is not None else _form(
                pdf, Dictionary(), content=inline_image(seed + 1))
            body += b"/Fm0 Do\n"
        if "nested_form" in locations:
            inner = _form(pdf, Dictionary(), content=inline_image(seed + 2))
            xobjects.Fm1 = _form(pdf, Dictionary(XObject=Dictionary(Fm0=inner)),
                                 content=b"/Fm0 Do\n")
            body += b"/Fm1 Do\n"
        if "form_without_resources" in locations:
            xobjects.Fm2 = pdf.make_stream(
                inline_image(seed + 3), Type=Name.XObject, Subtype=Name.Form,
                BBox=Array([0, 0, 100, 100]))
            body += b"/Fm2 Do\n"
        if "soft_mask" in locations:
            group = _form(pdf, Dictionary(), content=inline_image(seed + 4))
            group.Group = Dictionary(S=Name.Transparency, Type=Name.Group)
            resources.ExtGState = Dictionary(GS0=Dictionary(
                Type=Name.ExtGState,
                SMask=Dictionary(S=Name.Luminosity, G=group)))
            body += b"q /GS0 gs Q\n"
        if "pattern" in locations:
            pattern = _form(pdf, Dictionary(), content=inline_image(seed + 5))
            pattern.PatternType = 1
            pattern.PaintType = 1
            pattern.TilingType = 1
            pattern.XStep = 10
            pattern.YStep = 10
            resources.Pattern = Dictionary(P0=pattern)
            body += b"q /Pattern cs /P0 scn 0 0 10 10 re f Q\n"
        if "annotation" in locations:
            appearance = _form(pdf, Dictionary(), content=inline_image(seed + 6))
            annots.append(pdf.make_indirect(Dictionary(
                Type=Name.Annot, Subtype=Name.Square,
                Rect=Array([0, 0, 10, 10]), AP=Dictionary(N=appearance))))
        if type3:
            resources.Font.T3 = _type3_font(pdf)
            body += b"BT /T3 8 Tf 40 600 Td (a) Tj ET\n"

        if len(xobjects.keys()):
            resources.XObject = xobjects

        if split_contents:
            # 命令の途中ではなく q と Q の間で /Contents を分ける
            contents = Array([pdf.make_stream(text + b"q "),
                              pdf.make_stream(b"Q\n" + body + trailer)])
        else:
            contents = pdf.make_stream(text + body + trailer)

        page = Dictionary(
            Type=Name.Page, MediaBox=Array([0, 0, 612, 792]),
            Resources=resources, Contents=contents)
        if len(annots):
            page.Annots = annots
        pdf.pages.append(pikepdf.Page(pdf.make_indirect(page)))

    pdf.save(path)
    return str(path)


def build_image_xobject_pdf(path, width, height, stencil=False, pages=1):
    """画像XObjectを本文から離れた位置に描くPDFを生成して保存する

    画像は IMAGE_BOX の位置に描き、それ以外の場所に本文を置く。
    """
    pdf = pikepdf.Pdf.new()
    font = pdf.make_indirect(Dictionary(
        Type=Name.Font, Subtype=Name.Type1, BaseFont=Name.Helvetica,
        Encoding=Name.WinAnsiEncoding))
    if stencil:
        data = bytes(((width + 7) // 8) * height)
        extra = {"ImageMask": True, "BitsPerComponent": 1}
    else:
        data = bytes(random.Random(1).randrange(256)
                     for _ in range(width * height * 3))
        extra = {"ColorSpace": Name.DeviceRGB, "BitsPerComponent": 8}

    left, bottom, right, top = IMAGE_BOX
    content = (b"BT /F1 12 Tf 40 700 Td (Text beside the image) Tj ET\n"
               + f"q {right - left} 0 0 {top - bottom} {left} {bottom} cm "
                 "/Im0 Do Q\n".encode())
    for _ in range(pages):
        image = pdf.make_stream(data, Type=Name.XObject, Subtype=Name.Image,
                                Width=width, Height=height, **extra)
        page = Dictionary(
            Type=Name.Page, MediaBox=Array([0, 0, 612, 792]),
            Resources=Dictionary(Font=Dictionary(F1=font),
                                 XObject=Dictionary(Im0=image)),
            Contents=pdf.make_stream(content))
        pdf.pages.append(pikepdf.Page(pdf.make_indirect(page)))
    pdf.save(path)
    return str(path)


def count_inline_images(path_or_pdf):
    """PDF内の全ストリームに残っているインライン画像の数を数える"""
    def _count(pdf):
        total = 0
        for obj in pdf.objects:
            # オブジェクトストリームなどコンテンツでないものは解析しない
            if (isinstance(obj, Stream)
                    and str(obj.get("/Subtype")) != "/Image"
                    and str(obj.get("/Type")) not in ("/ObjStm", "/XRef")):
                total += sum(
                    isinstance(instruction, pikepdf.ContentStreamInlineImage)
                    for instruction in pikepdf.parse_content_stream(obj))
        return total

    if isinstance(path_or_pdf, pikepdf.Pdf):
        return _count(path_or_pdf)
    with pikepdf.open(path_or_pdf) as pdf:
        return _count(pdf)


def count_image_streams(path_or_pdf):
    """PDF内に残っている画像ストリームの数を数える"""
    def _count(pdf):
        return sum(1 for obj in pdf.objects
                   if isinstance(obj, Stream)
                   and str(obj.get("/Subtype")) == "/Image")

    if isinstance(path_or_pdf, pikepdf.Pdf):
        return _count(path_or_pdf)
    with pikepdf.open(path_or_pdf) as pdf:
        return _count(pdf)
