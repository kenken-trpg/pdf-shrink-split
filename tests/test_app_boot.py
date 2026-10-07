"""Streamlitアプリが起動することのスモークテスト"""
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BOOT_TIMEOUT = 90


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


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
