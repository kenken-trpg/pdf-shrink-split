import importlib.util
import io
import os
import sys
import zipfile

import streamlit as st

st.set_page_config(
    page_title="PDF Shrink & Split",
    page_icon="📄",
    layout="centered"
)


def load_core():
    """CLI版のスクリプトを処理の本体として読み込む

    CLI版はファイル1つで配布するためパッケージに分けられず、ファイル名に
    ハイフンを含むので通常の import もできない。Streamlit は操作のたびに
    このスクリプトを再実行するため、読み込むのは最初の1回だけにする。
    """
    name = "pdf_shrink_split_core"
    if name not in sys.modules:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "pdf-shrink-split.py")
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        sys.modules[name] = module
    return sys.modules[name]


core = load_core()
TextlessPdfError = core.TextlessPdfError


def format_size_change(reduction):
    """削減率(%)を、サイズの増減を表す文字列にする"""
    return f"{-reduction:+.1f}%"


def split_and_process_pdf(uploaded_file, char_limit=100000, force=False):
    """PDFから画像を削除し、字数制限で分割してバイト列のリストを返す"""
    pdf_data = uploaded_file.getvalue()

    reader = core.PdfReader(io.BytesIO(pdf_data))
    char_counts = core.count_characters_per_page(reader)

    warnings = core.check_text_coverage(char_counts, force)
    warnings += core.check_page_limit(char_counts, char_limit)

    groups = core.group_pages_by_chars(char_counts, char_limit)

    output_files = []
    removed_images = 0
    base_name = os.path.splitext(uploaded_file.name)[0]

    with core.Pdf.open(io.BytesIO(pdf_data)) as source_pdf:
        for idx, group in enumerate(groups):
            buffer = io.BytesIO()
            removed_images += core.write_cleaned_pdf(source_pdf, group, buffer)

            if len(groups) == 1:
                file_name = f"{base_name}_no_images.pdf"
            else:
                file_name = f"{base_name}_part{idx+1}.pdf"

            output_files.append({
                "name": file_name,
                "bytes": buffer.getvalue(),
                "pages": len(group),
                "chars": sum(char_counts[p] for p in group)
            })

    return {
        "total_pages": len(char_counts),
        "total_chars": sum(char_counts),
        "char_limit": char_limit,
        "original_size": len(pdf_data),
        "output_size": sum(len(f["bytes"]) for f in output_files),
        "removed_images": removed_images,
        "warnings": warnings,
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

def run_processing(file, limit, force=False):
    """処理を実行し、結果をsession_stateに保存する"""
    for key in ("result", "error", "textless"):
        st.session_state.pop(key, None)
    with st.spinner("処理中..."):
        try:
            st.session_state["result"] = split_and_process_pdf(
                file, limit, force)
        except TextlessPdfError as e:
            # テキストのないPDFは画像を削除すると中身が消えるため、
            # 黙って空のPDFを返さずに確認を求める
            st.session_state["textless"] = str(e)
        except Exception as e:
            st.session_state["error"] = e


# 処理実行
if process_btn:
    if not uploaded_file:
        st.warning("⚠️ 先にPDFファイルをアップロードしてください")
        st.session_state.pop("result", None)
    else:
        run_processing(uploaded_file, char_limit)

# テキストを抽出できないPDFの確認
if "textless" in st.session_state:
    st.error(f"❌ {st.session_state['textless']}")
    st.markdown(
        "スキャンしたPDFはこのツールの対象外です。"
        "元のファイルをそのままお使いください。")
    if st.button("⚠️ それでも画像を削除して処理する"):
        if uploaded_file:
            run_processing(uploaded_file, char_limit, force=True)
            st.rerun()
        else:
            st.warning("⚠️ PDFファイルを再度アップロードしてください")

if "error" in st.session_state:
    e = st.session_state["error"]
    st.error(f"❌ エラーが発生しました: {str(e)}")
    st.exception(e)

# 結果表示（ダウンロードで再実行されてもsession_stateから復元される）
if "result" in st.session_state:
    result = st.session_state["result"]

    st.success("✅ 処理が完了しました！")

    for warning in result.get("warnings", []):
        st.warning(f"⚠️ {warning}")

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
                  delta=format_size_change(reduction), delta_color="inverse")
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
