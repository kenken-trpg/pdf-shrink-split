"""テスト用のPDFを生成するヘルパー

リポジトリにバイナリを置かずに済むよう、必要なPDFはテスト実行時に組み立てる。
画像を「入れ子の奥」に置いた検体を作れることが重要で、ここが
過去に画像削除が機能していなかった原因そのものにあたる。
"""
import zlib

import pikepdf
from pikepdf import Array, Dictionary, Name, Stream

# 画像1枚あたりのバイト数を大きめにして、削除漏れがサイズに出るようにする
IMAGE_SIDE = 120


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
              nested=True, piece_info=True):
    """検証用PDFを生成して保存する

    nested=True のとき、画像をページ直下だけでなく
    Form XObjectの入れ子・ソフトマスクグループ・パターン・注釈の外観の
    中にも配置する。
    """
    pdf = pikepdf.Pdf.new()
    font = pdf.make_indirect(Dictionary(
        Type=Name.Font, Subtype=Name.Type1, BaseFont=Name.Helvetica,
        Encoding=Name.WinAnsiEncoding))

    for page_num in range(pages):
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
        pdf.Root.Metadata = pdf.make_stream(
            b'<?xpacket begin="" ?><x:xmpmeta xmlns:x="adobe:ns:meta/">'
            + b"<!-- padding -->" * 500
            + b"</x:xmpmeta><?xpacket end=\"w\"?>",
            Type=Name.Metadata, Subtype=Name.XML)
        pdf.Root.StructTreeRoot = Dictionary(
            Type=Name.StructTreeRoot,
            K=Array([Dictionary(Type=Name.StructElem, S=Name.P)] * 50))
        pdf.Root.PieceInfo = Dictionary(ClaudeTest=Dictionary(
            LastModified=pikepdf.String("D:20260101000000Z"),
            Private=pdf.make_stream(zlib.compress(b"R" * 200_000),
                                    Filter=Name.FlateDecode)))

    pdf.save(path)
    return str(path)


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
