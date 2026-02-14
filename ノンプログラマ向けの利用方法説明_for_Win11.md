# PDFから画像を削除して圧縮するツールのご案内（Windows 11向け）
このガイドは、プログラムの知識がなくても、指定されたPythonスクリプトを使ってPDFファイルから画像を削除し、ファイルサイズを小さくする方法をWindows 11で実践するための手順を説明します。一つ一つのステップを丁寧に案内しますので、初めての方でも安心して進めてください。

## 1. このスクリプトの目的
このスクリプトは、PDFファイルに含まれる画像を取り除き、その結果としてファイルサイズを小さく（圧縮）するものです。また、**テキストの字数が10万字を超える場合は、自動的に複数のPDFファイルに分割**します。機械翻訳サービスなどの字数制限に対応したいときに便利です。

## 2. Pythonのインストール
このスクリプトを使うには、まずPythonというツールをパソコンにインストールする必要があります。

**手順：**
1. Microsoft Storeを開く：
   - 画面左下の「スタート」ボタン（Windowsアイコン）をクリック。
   - 検索バーに「Microsoft Store」と入力し、表示されたアプリを開きます。

2. Pythonを検索：
   - Microsoft Storeの上部にある検索バーに「Python」と入力。
   - 最新バージョン（例：Python 3.12）を選択します。

3. インストール：
   - 「入手」または「インストール」ボタンをクリックしてPythonをインストール。

4. 確認：
   - インストールが終わったら、スタートメニューに「Python」が追加されているか確認してください。

## 3. コマンドプロンプトの開き方
スクリプトを実行するには、コマンドプロンプトというツールを使います。これは、Windowsで命令を入力するための黒い画面です。

**手順：**
1. スタートボタンをクリックし、検索バーに「cmd」と入力。
2. 「コマンドプロンプト」が表示されたら、それをクリックして開きます。
3. 黒い画面が表示されたら、準備完了です。

## 4. スクリプトの保存
提供されたスクリプトをパソコンに保存します。

> **💡 ポイント**: このスクリプトは初回実行時に必要なライブラリ（PyPDF2、pikepdf）を自動でインストールします。手動でのインストール作業は不要です！

**手順：**
1. テキストエディタを開く：
   - スタートメニューで「メモ帳」と検索して開きます。

2. スクリプトをコピーして貼り付け：
   - 以下のコードをすべてコピーし、メモ帳に貼り付けます：
```python
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
    """入力ファイル名から分割ファイル名のリストを生成する"""
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

    char_counts = count_characters_per_page(reader)
    total_chars = sum(char_counts)

    print(f"--- 字数カウント情報 ---")
    print(f"ページ数: {total_pages}")
    print(f"総字数:   {total_chars:,}")
    print(f"字数制限: {char_limit:,}")
    print(f"------------------------")

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

    output_paths = make_output_paths(input_path, len(groups))

    if len(groups) == 1:
        print(f"✓ 字数制限内です。1ファイルで出力します。")
    else:
        print(f"📄 {len(groups)}個のファイルに分割します。")

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
```

3. ファイルとして保存：
   - メモ帳のメニューで「ファイル」→「名前を付けて保存」を選択。
   - ファイル名を「pdf_image_remover.py」と入力（.pyを必ず付ける）。
   - 保存先はデスクトップやドキュメントフォルダなど、わかりやすい場所を選び、「保存」をクリック。

## 5. スクリプトの実行
準備ができたら、スクリプトを実行してPDFから画像を削除します。

**手順：**
1. コマンドプロンプトでフォルダに移動：
   - スクリプトを保存した場所に移動します。たとえば、デスクトップに保存した場合：
```
cd C:\Users\ユーザー名\Desktop
```
   - ※「ユーザー名」は自分のWindowsのユーザー名に置き換えてください。

2. スクリプトを実行：
   - 次のコマンドを入力してEnterキーを押します：
```
python pdf_image_remover.py input.pdf
```
   - `input.pdf` の部分を、処理したいPDFファイルの名前に変えてください。
   - 字数制限を変更したい場合は、`--char-limit` を追加します：
```
python pdf_image_remover.py input.pdf --char-limit 50000
```

3. 結果の確認：
   - 実行が成功すると、画面に字数情報と出力ファイル名が表示されます。
   - 字数が10万字以内の場合: `入力ファイル名_no_images.pdf` が作成されます。
   - 字数が10万字を超えた場合: `入力ファイル名_part1.pdf`, `_part2.pdf`, ... に自動分割されます。

### 具体例：
PDFが「C:\Users\太郎\Documents\sample.pdf」にある場合：
```
python pdf_image_remover.py C:\Users\太郎\Documents\sample.pdf
```
これで、同じフォルダにsample_no_images.pdf（または分割ファイル）が保存されます。

## 6. もしうまくいかない場合（トラブルシューティング）
エラーが出た場合、以下の点をチェックしてください：
  - Pythonが動いているか：
     - コマンドプロンプトで `python --version` と入力し、バージョンが表示されるか確認。
  - フォルダが正しいか：
     - `cd` コマンドで正しいフォルダに移動しているか確認。
  - ファイル名やパスが間違っていないか：
     - PDFファイルが存在するか、ファイル名に誤りがないか確認。
  - ファイル名にカッコが含まれる場合：
     - シングルクォートでファイル名を囲んでください：`python pdf_image_remover.py 'ファイル名(注意).pdf'`

## 7. まとめ
お疲れ様でした！これで以下の手順を完了しました：
1. Pythonをインストール
2. コマンドプロンプトを開く
3. スクリプトを保存
4. スクリプトを実行して画像を削除＆圧縮＆自動分割

必要なライブラリは初回実行時に自動インストールされるので、手動での準備は不要です。不明点があれば、「Python 使い方」などで検索してみるとさらに詳しい情報が見つかります。ぜひ試してみてください！
