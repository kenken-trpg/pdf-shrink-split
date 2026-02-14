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

from PyPDF2 import PdfReader, PdfWriter
from PyPDF2.generic import NullObject
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


def save_compressed(writer, output_path):
    """PdfWriterの内容をpikepdfで圧縮して保存する"""
    with io.BytesIO() as buf:
        writer.write(buf)
        buf.seek(0)
        pdf_out = Pdf.open(buf)
        pdf_out.save(output_path, compress_streams=True,
                     object_stream_mode=ObjectStreamMode.generate)


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
    for idx, (group, out_path) in enumerate(zip(groups, output_paths)):
        group_chars = sum(char_counts[p] for p in group)
        writer = remove_images_from_pages(reader, group)
        save_compressed(writer, out_path)
        print(f"  [{idx+1}/{len(groups)}] {os.path.basename(out_path)}"
              f"  ({len(group)}ページ, {group_chars:,}字)")

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
