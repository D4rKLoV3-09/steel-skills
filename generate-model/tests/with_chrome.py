#!/usr/bin/env python3
"""Run a browser test with the system Chrome when Playwright's own Chromium is not installed
(claude.ai cloud session: /usr/bin/google-chrome exists, `playwright install` is not available).

    python tests/with_chrome.py tests/ui_check.py PAGE.html
    python generate-model/tests/with_chrome.py generate-mto/tests/mto_parity.py PAGE.html
"""
import os
import runpy
import sys

from playwright.async_api import BrowserType

CHROME = os.environ.get("CHROME", "/usr/bin/google-chrome")
_launch = BrowserType.launch


async def launch(self, *a, **k):
    k.setdefault("executable_path", CHROME)
    k["args"] = list(k.get("args", [])) + ["--no-sandbox"]
    return await _launch(self, *a, **k)


BrowserType.launch = launch
sys.argv = sys.argv[1:]
runpy.run_path(sys.argv[0], run_name="__main__")
