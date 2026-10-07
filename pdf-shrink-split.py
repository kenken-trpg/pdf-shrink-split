import subprocess
import sys
import os
import io

# --- 依存パッケージの自動インストール ---
def install_packages():
    """必要なパッケージがなければ自動でインストールする"""
    required = {"PyPDF2": "PyPDF2", "pikepdf": "pikepdf"}
    for import_name, pip_name in required.items():
        try:
            __import__(import_name)
        except ImportError:
            print(f"📦 {pip_name} をインストールしています...")
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", pip_name],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            print(f"✓ {pip_name} のインストールが完了しました。")

install_packages()

import logging
import warnings
logging.getLogger("PyPDF2").setLevel(logging.ERROR)
warnings.filterwarnings("ignore", module="PyPDF2")

from PyPDF2 import PdfReader
import pikepdf
from pikepdf import Pdf, ObjectStreamMode


# --- ユーティリティ関数 ---

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


def make_output_paths(input_path, num_parts):
    """入力ファイル名から分割ファイル名のリストを生成する

    例: input.pdf → input_part1.pdf, input_part2.pdf, ...
    1つだけの場合: input_no_images.pdf
    """
    base, ext = os.path.splitext(input_path)
    if num_parts == 1:
        return [f"{base}_no_images{ext}"]
    return [f"{base}_part{i+1}{ext}" for i in range(num_parts)]


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


def write_cleaned_pdf(source_pdf, page_indices, output_path):
    """指定ページを抜き出し、画像を削除・圧縮して保存する"""
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

    out_pdf.save(
        output_path,
        compress_streams=True,
        recompress_flate=True,
        object_stream_mode=ObjectStreamMode.generate,
    )
    return removed_images


def split_and_process_pdf(input_path, char_limit=100000):
    """PDFから画像を削除し、字数制限で分割して保存する"""
    reader = PdfReader(input_path)
    total_pages = len(reader.pages)

    # 各ページの字数をカウント
    char_counts = count_characters_per_page(reader)
    total_chars = sum(char_counts)

    print(f"--- 字数カウント情報 ---")
    print(f"ページ数: {total_pages}")
    print(f"総字数:   {total_chars:,}")
    print(f"字数制限: {char_limit:,}")
    print(f"------------------------")

    # ページを分割グループに振り分け
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

    # 出力ファイル名を生成
    output_paths = make_output_paths(input_path, len(groups))

    if len(groups) == 1:
        print(f"✓ 字数制限内です。1ファイルで出力します。")
    else:
        print(f"📄 {len(groups)}個のファイルに分割します。")

    # 各グループを処理・保存
    removed_images = 0
    with Pdf.open(input_path) as source_pdf:
        for idx, (group, out_path) in enumerate(zip(groups, output_paths)):
            group_chars = sum(char_counts[p] for p in group)
            removed_images += write_cleaned_pdf(source_pdf, group, out_path)
            print(f"  [{idx+1}/{len(groups)}] {os.path.basename(out_path)}"
                  f"  ({len(group)}ページ, {group_chars:,}字,"
                  f" {os.path.getsize(out_path)/1024/1024:.2f}MB)")

    original_size = os.path.getsize(input_path)
    output_size = sum(os.path.getsize(p) for p in output_paths)
    reduction = 100 - output_size * 100 / original_size if original_size else 0
    print()
    print(f"削除した画像: {removed_images:,}個")
    print(f"サイズ: {original_size/1024/1024:.2f}MB"
          f" → {output_size/1024/1024:.2f}MB ({reduction:.1f}% 削減)")
    print(f"\n✅ 完了しました！")
    return output_paths


# --- メイン処理 ---

if __name__ == "__main__":
    args = sys.argv[1:]
    char_limit = 100000

    # --char-limit オプションの処理
    if "--char-limit" in args:
        idx = args.index("--char-limit")
        try:
            char_limit = int(args[idx + 1])
            args = args[:idx] + args[idx + 2:]
        except (IndexError, ValueError):
            print("エラー: --char-limit には数値を指定してください。")
            print("使用法: python pdf_image_remover.py 入力.pdf [--char-limit 100000]")
            sys.exit(1)

    if len(args) == 1:
        input_file = args[0]
    elif len(args) == 0:
        print("使用法: python pdf_image_remover.py 入力.pdf [--char-limit 100000]")
        print()
        print("PDFから画像を削除し、字数制限（デフォルト10万字）を超える場合は")
        print("複数のファイルに自動分割します。")
        sys.exit(0)
    else:
        print("使用法: python pdf_image_remover.py 入力.pdf [--char-limit 100000]")
        sys.exit(1)

    if not os.path.exists(input_file):
        print(f"エラー: ファイルが見つかりません: {input_file}")
        sys.exit(1)

    split_and_process_pdf(input_file, char_limit)
