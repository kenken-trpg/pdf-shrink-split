import streamlit as st
import io
import os
import zipfile
from PyPDF2 import PdfReader
import pikepdf
from pikepdf import Pdf, ObjectStreamMode

st.set_page_config(
    page_title="PDF Shrink & Split",
    page_icon="📄",
    layout="centered"
)


def count_characters_per_page(reader):
    """各ページのテキスト字数リストを返す"""
    char_counts = []
    for page in reader.pages:
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        char_counts.append(len(text))
    return char_counts


def strip_images_from_resources(resources, seen=None):
    """Resources辞書を再帰的に辿って画像XObjectを削除し、削除数を返す

    画像はページ直下の /Resources/XObject だけでなく、Form XObject の
    入れ子、ソフトマスクグループ(/ExtGState -> /SMask -> /G)、
    パターンの中にも置かれているため再帰的に処理する必要がある。
    """
    if resources is None:
        return 0

    if seen is None:
        seen = set()
    objgen = getattr(resources, "objgen", (0, 0))
    if objgen != (0, 0):
        # 循環参照・共有リソースの二重処理を防ぐ
        if objgen in seen:
            return 0
        seen.add(objgen)

    removed = 0

    xobjects = resources.get("/XObject")
    if xobjects is not None:
        for name in list(xobjects.keys()):
            try:
                xobj = xobjects[name]
                subtype = str(xobj.get("/Subtype"))
                if subtype == "/Image":
                    del xobjects[name]
                    removed += 1
                elif subtype == "/Form":
                    removed += strip_images_from_resources(
                        xobj.get("/Resources"), seen)
            except Exception:
                pass

    ext_gstates = resources.get("/ExtGState")
    if ext_gstates is not None:
        for name in list(ext_gstates.keys()):
            try:
                smask = ext_gstates[name].get("/SMask")
                # /SMask は /None という名前オブジェクトの場合もある
                if smask is None or isinstance(smask, pikepdf.Name):
                    continue
                group = smask.get("/G")
                if group is not None:
                    removed += strip_images_from_resources(
                        group.get("/Resources"), seen)
            except Exception:
                pass

    patterns = resources.get("/Pattern")
    if patterns is not None:
        for name in list(patterns.keys()):
            try:
                removed += strip_images_from_resources(
                    patterns[name].get("/Resources"), seen)
            except Exception:
                pass

    return removed


# ページから削除しても本文テキストに影響しないエントリ
# /PieceInfo には Photoshop/Illustrator が元画像の複製を丸ごと残すことがある
PAGE_CRUFT_KEYS = ("/PieceInfo", "/Thumb", "/Metadata", "/B", "/StructParents")
ROOT_CRUFT_KEYS = ("/Metadata", "/PieceInfo", "/StructTreeRoot")


def clean_page(page):
    """1ページから画像と不要なメタデータを削除し、削除した画像数を返す"""
    removed = strip_images_from_resources(page.get("/Resources"))

    annots = page.get("/Annots")
    if annots is not None:
        for annot in annots:
            try:
                appearance = annot.get("/AP")
                if appearance is None:
                    continue
                for state in list(appearance.keys()):
                    stream = appearance[state]
                    if isinstance(stream, pikepdf.Stream):
                        removed += strip_images_from_resources(
                            stream.get("/Resources"))
            except Exception:
                pass

    for key in PAGE_CRUFT_KEYS:
        if key in page:
            del page[key]

    return removed


def build_pdf_bytes(source_pdf, page_indices):
    """指定ページを抜き出し、画像を削除・圧縮したバイト列を返す"""
    out_pdf = Pdf.new()
    for page_num in page_indices:
        out_pdf.pages.append(source_pdf.pages[page_num])

    removed_images = 0
    for page in out_pdf.pages:
        removed_images += clean_page(page)

    for key in ROOT_CRUFT_KEYS:
        if key in out_pdf.Root:
            del out_pdf.Root[key]

    out_pdf.remove_unreferenced_resources()

    buf = io.BytesIO()
    out_pdf.save(
        buf,
        compress_streams=True,
        recompress_flate=True,
        object_stream_mode=ObjectStreamMode.generate,
    )
    return buf.getvalue(), removed_images


def split_and_process_pdf(uploaded_file, char_limit=100000):
    """PDFから画像を削除し、字数制限で分割してバイト列のリストを返す"""
    pdf_data = uploaded_file.getvalue()

    reader = PdfReader(io.BytesIO(pdf_data))
    char_counts = count_characters_per_page(reader)
    total_pages = len(char_counts)
    total_chars = sum(char_counts)

    groups = []
    current_group = []
    current_chars = 0

    for i, count in enumerate(char_counts):
        if current_group and current_chars + count > char_limit:
            groups.append(current_group)
            current_group = []
            current_chars = 0
        current_group.append(i)
        current_chars += count

    if current_group:
        groups.append(current_group)

    output_files = []
    removed_images = 0
    base_name = os.path.splitext(uploaded_file.name)[0]

    with Pdf.open(io.BytesIO(pdf_data)) as source_pdf:
        for idx, group in enumerate(groups):
            pdf_bytes, removed = build_pdf_bytes(source_pdf, group)
            removed_images += removed

            if len(groups) == 1:
                file_name = f"{base_name}_no_images.pdf"
            else:
                file_name = f"{base_name}_part{idx+1}.pdf"

            output_files.append({
                "name": file_name,
                "bytes": pdf_bytes,
                "pages": len(group),
                "chars": sum(char_counts[p] for p in group)
            })

    return {
        "total_pages": total_pages,
        "total_chars": total_chars,
        "char_limit": char_limit,
        "original_size": len(pdf_data),
        "output_size": sum(len(f["bytes"]) for f in output_files),
        "removed_images": removed_images,
        "files": output_files
    }


# --- UI ---

st.title("📄 PDF Shrink & Split")
st.markdown("PDFから画像を削除し、ファイルサイズを軽量化＆字数制限で自動分割")

st.divider()

# ファイルアップロード
uploaded_file = st.file_uploader(
    "PDFファイルをアップロード",
    type=["pdf"],
    help="処理したいPDFファイルを選択してください"
)

# 字数制限設定
col1, col2 = st.columns(2)
with col1:
    char_limit = st.number_input(
        "字数制限",
        min_value=1000,
        max_value=1000000,
        value=100000,
        step=1000,
        help="この字数を超えると自動的に分割されます"
    )

with col2:
    st.markdown("<br>", unsafe_allow_html=True)
    process_btn = st.button("🚀 処理開始", type="primary", use_container_width=True)

# 処理実行
if process_btn:
    if not uploaded_file:
        st.warning("⚠️ 先にPDFファイルをアップロードしてください")
        st.session_state.pop("result", None)
    else:
        with st.spinner("処理中..."):
            try:
                st.session_state["result"] = split_and_process_pdf(
                    uploaded_file, char_limit)
                st.session_state.pop("error", None)
            except Exception as e:
                st.session_state.pop("result", None)
                st.session_state["error"] = e

if "error" in st.session_state:
    e = st.session_state["error"]
    st.error(f"❌ エラーが発生しました: {str(e)}")
    st.exception(e)

# 結果表示（ダウンロードで再実行されてもsession_stateから復元される）
if "result" in st.session_state:
    result = st.session_state["result"]

    st.success("✅ 処理が完了しました！")

    st.subheader("📊 処理結果")
    info_col1, info_col2, info_col3 = st.columns(3)
    with info_col1:
        st.metric("総ページ数", result["total_pages"])
    with info_col2:
        st.metric("総字数", f"{result['total_chars']:,}")
    with info_col3:
        st.metric("出力ファイル数", len(result["files"]))

    size_col1, size_col2, size_col3 = st.columns(3)
    original_mb = result["original_size"] / 1024 / 1024
    output_mb = result["output_size"] / 1024 / 1024
    if result["original_size"]:
        reduction = 100 - output_mb / original_mb * 100
    else:
        reduction = 0
    with size_col1:
        st.metric("元のサイズ", f"{original_mb:.2f} MB")
    with size_col2:
        st.metric("出力合計サイズ", f"{output_mb:.2f} MB",
                  delta=f"-{reduction:.1f}%", delta_color="inverse")
    with size_col3:
        st.metric("削除した画像", f"{result['removed_images']:,} 個")

    st.divider()

    # ダウンロードボタン
    st.subheader("⬇️ ダウンロード")

    for idx, file in enumerate(result["files"]):
        st.download_button(
            label=f"📄 {file['name']} ({file['pages']}ページ, {file['chars']:,}字)",
            data=file["bytes"],
            file_name=file["name"],
            mime="application/pdf",
            use_container_width=True,
            key=f"dl_{idx}_{file['name']}"
        )

    if len(result["files"]) > 1:
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for file in result["files"]:
                zf.writestr(file["name"], file["bytes"])
        st.download_button(
            label=f"🗂️ すべてまとめてダウンロード (ZIP, {len(result['files'])}ファイル)",
            data=zip_buf.getvalue(),
            file_name="pdf_split_files.zip",
            mime="application/zip",
            use_container_width=True,
            key="dl_zip"
        )

    st.caption("※ ダウンロード後もこの一覧は残ります。再処理する場合のみ「処理開始」を押してください。")

# フッター
st.divider()
st.caption("""
**使い方:**
1. PDFファイルをアップロード
2. 字数制限を設定（デフォルト: 10万字）
3. 「処理開始」ボタンをクリック
4. 生成されたファイルをダウンロード

**注意:** 暗号化されたPDFには対応していません。重要なファイルは必ずバックアップを取ってから使用してください。
""")
