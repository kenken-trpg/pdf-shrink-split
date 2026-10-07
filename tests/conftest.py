"""テスト共通の読み込み処理

リポジトリのスクリプトはパッケージ化されていないため、ファイルパスから
直接モジュールとして読み込む。
"""
import importlib.util
import io
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

CLI_PATH = os.path.join(ROOT, "pdf-shrink-split.py")
APP_PATH = os.path.join(ROOT, "streamlit_app.py")

# streamlit_app.py はこのマーカーより後ろがUI構築コードで、読み込むと
# streamlitランタイム外で実行されてしまうため、前半だけを取り出す
UI_MARKER = "# --- UI ---"


@pytest.fixture(scope="session")
def cli():
    """pdf-shrink-split.py を読み込む（ファイル名にハイフンを含むため直接読む）"""
    spec = importlib.util.spec_from_file_location("pdf_shrink_split_cli",
                                                  CLI_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def app():
    """streamlit_app.py の処理関数部分だけを読み込む"""
    source = open(APP_PATH, encoding="utf-8").read()
    assert UI_MARKER in source, (
        f"{APP_PATH} に {UI_MARKER!r} が見つかりません。"
        "処理部分とUI部分の境界が変わった場合はこのテストを更新してください。")
    head = source.split(UI_MARKER)[0]

    namespace = {"__name__": "streamlit_app_core"}
    exec(compile(head, APP_PATH, "exec"), namespace)
    return namespace


class UploadedFile(io.BytesIO):
    """streamlitのUploadedFileの代わり（getvalue()とnameを持てばよい）"""

    def __init__(self, path):
        super().__init__(open(path, "rb").read())
        self.name = os.path.basename(path)


@pytest.fixture
def uploaded():
    return UploadedFile
