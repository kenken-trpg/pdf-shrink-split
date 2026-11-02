"""Streamlitアプリが起動することのスモークテスト"""
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

import pytest
from streamlit.testing.v1 import AppTest

from pdf_fixtures import build_pdf

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BOOT_TIMEOUT = 90


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.mark.timeout(BOOT_TIMEOUT)
def test_app_script_runs_without_error():
    """スクリプト本体を実行する（ヘルスチェックはスクリプトを実行しない）"""
    app_test = AppTest.from_file(os.path.join(ROOT, "streamlit_app.py"),
                                 default_timeout=30).run()

    assert not app_test.exception
    assert app_test.title[0].value == "📄 PDF Shrink & Split"


@pytest.mark.timeout(BOOT_TIMEOUT + 30)
def test_app_serves_health_endpoint():
    port = _free_port()
    proc = subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", "streamlit_app.py",
         "--server.headless", "true", "--server.port", str(port),
         "--browser.gatherUsageStats", "false"],
        cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True)
    try:
        url = f"http://127.0.0.1:{port}/_stcore/health"
        deadline = time.time() + BOOT_TIMEOUT
        last_error = None
        while time.time() < deadline:
            if proc.poll() is not None:
                pytest.fail("streamlitが終了しました:\n" + proc.stdout.read())
            try:
                with urllib.request.urlopen(url, timeout=3) as response:
                    assert response.status == 200
                    return
            except (urllib.error.URLError, OSError) as exc:
                last_error = exc
                time.sleep(1)
        pytest.fail(f"{BOOT_TIMEOUT}秒以内に起動しませんでした: {last_error}")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()


def _app_with_file(path):
    app_test = AppTest.from_file(os.path.join(ROOT, "streamlit_app.py"),
                                 default_timeout=30).run()
    data = open(path, "rb").read()
    app_test.file_uploader[0].set_value(
        (os.path.basename(path), data, "application/pdf")).run()
    return app_test


def _click(app_test, label):
    next(b for b in app_test.button if label in b.label).click().run()


def _metrics(app_test):
    return {metric.label: metric.value for metric in app_test.metric}


@pytest.mark.timeout(BOOT_TIMEOUT)
def test_app_processes_uploaded_pdf(tmp_path):
    app_test = _app_with_file(build_pdf(tmp_path / "web.pdf", pages=2))

    _click(app_test, "処理開始")

    assert not app_test.exception
    assert "処理が完了しました" in app_test.success[0].value
    assert _metrics(app_test)["総ページ数"] == "2"
    assert _metrics(app_test)["出力ファイル数"] == "1"


@pytest.mark.timeout(BOOT_TIMEOUT)
def test_app_shows_page_limit_warning(tmp_path):
    long_page = build_pdf(tmp_path / "long.pdf", pages=1,
                          text_per_page="Hello PDF shrink split. " * 3)
    app_test = _app_with_file(long_page)
    app_test.number_input[0].set_value(1000)

    _click(app_test, "処理開始")

    assert not app_test.exception
    assert any("1ページで字数制限" in w.value for w in app_test.warning)


@pytest.mark.timeout(BOOT_TIMEOUT)
def test_app_asks_before_processing_textless_pdf(tmp_path):
    path = build_pdf(tmp_path / "scan.pdf", pages=2, empty_pages=2)
    app_test = _app_with_file(path)

    _click(app_test, "処理開始")

    assert not app_test.exception
    assert "テキストを抽出できません" in app_test.error[0].value
    assert not app_test.success

    _click(app_test, "それでも画像を削除")

    assert not app_test.exception
    assert "処理が完了しました" in app_test.success[0].value
