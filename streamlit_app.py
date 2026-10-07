import streamlit as st
import io
import os
import zipfile
from PyPDF2 import PdfReader, PdfWriter
from PyPDF2.generic import NullObject
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


def remove_images_from_pages(reader, page_indices):
    """指定されたページから画像を削除し、PdfWriterを返す"""
    writer = PdfWriter()
    for page_num in page_indices:
        page = reader.pages[page_num]
        if "/Resources" in page and "/XObject" in page["/Resources"]:
            xObject = page["/Resources"]["/XObject"].get_object()
            for obj in list(xObject.keys()):
                try:
                    if xObject[obj]["/Subtype"] == "/Image":
                        xObject[obj] = NullObject()
                except Exception:
                    pass
        writer.add_page(page)
    return writer


def save_compressed_to_bytes(writer):
    """PdfWriterの内容をpikepdfで圧縮してバイト列を返す"""
    with io.BytesIO() as buf:
        writer.write(buf)
        buf.seek(0)
        pdf_out = Pdf.open(buf)
        output_buf = io.BytesIO()
        pdf_out.save(output_buf, compress_streams=True,
                     object_stream_mode=ObjectStreamMode.generate)
        output_buf.seek(0)
        return output_buf.getvalue()


def split_and_process_pdf(uploaded_file, char_limit=100000):
    """PDFから画像を削除し、字数制限で分割してバイト列のリストを返す"""
    reader = PdfReader(uploaded_file)
    total_pages = len(reader.pages)

    char_counts = count_characters_per_page(reader)
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
    base_name = os.path.splitext(uploaded_file.name)[0]

    for idx, group in enumerate(groups):
        writer = remove_images_from_pages(reader, group)
        pdf_bytes = save_compressed_to_bytes(writer)

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
