#!/usr/bin/env python3
"""前端自测（可选，要装 playwright：pip install playwright && playwright install chromium）：
起服务 → 无头浏览器登录 → 放歌 → 歌词跟着亮 → 点歌词写批注 → 批注进了 API → AI 回话浮出来。
  python tests/test_browser.py
"""
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from test_all import free_port, wait_port, http, until  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    from playwright.sync_api import sync_playwright
    port = free_port()
    tmp = tempfile.mkdtemp(prefix="yue-bt-")
    cfg = {"port": port, "passcode": "1357", "api_token": "bt-token", "data_dir": os.path.join(tmp, "data"),
           "source": {"kind": "local", "dir": os.path.join(ROOT, "tests", "music")},
           "listener": {"kind": "tests.mock_listener:MockListener"}}
    cfgp = os.path.join(tmp, "config.json")
    json.dump(cfg, open(cfgp, "w"))
    log = open(os.path.join(tmp, "log"), "w")
    srv = subprocess.Popen([sys.executable, os.path.join(ROOT, "run.py"), "--config", cfgp], cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
    fails = []

    def check(name, cond, extra=""):
        print(("  通过  " if cond else "  失败  ") + name + (("  " + str(extra)[:160]) if extra and not cond else ""))
        if not cond:
            fails.append(name)

    base = f"http://127.0.0.1:{port}"
    api = lambda m, p, b=None: http(m, base + p, b, {"Authorization": "Bearer bt-token"})
    try:
        assert wait_port(port)
        with sync_playwright() as pw:
            br = pw.chromium.launch(args=["--autoplay-policy=no-user-gesture-required"])
            ctx = br.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, has_touch=True)
            pg = ctx.new_page()
            errors = []
            pg.on("pageerror", lambda e: errors.append(str(e)))
            pg.goto(base + "/")
            check("先看到登录页", pg.locator("input[name=passcode]").count() == 1)
            pg.fill("input[name=passcode]", "1357")
            pg.click("button")
            pg.wait_for_selector("#vinyl")
            check("登录后是播放器", pg.locator("#vinyl").count() == 1)
            check("默认用 CSS 唱臂", pg.locator("#arm.css").count() == 1)
            pg.click("#sbtn")
            pg.wait_for_selector("#res [data-i]")
            rows = pg.locator("#res [data-i]").all_inner_texts()
            check("曲库列出 3 首", len(rows) == 3, rows)
            pg.locator("#res [data-i]", has_text="晨光").click()
            pg.wait_for_function("document.getElementById('name').textContent==='晨光'")
            check("歌名/歌手上屏", pg.locator("#artist").inner_text() == "测试乐队")
            check("歌词渲染含翻译", pg.locator(".ln small").count() == 6)
            pg.wait_for_function("!document.getElementById('au').paused", timeout=8000)
            check("自动开始播放", pg.evaluate("!document.getElementById('au').paused"))
            check("唱片在转、唱臂落下", pg.locator("#vinyl.on").count() == 1 and pg.locator("#arm.on").count() == 1)
            pg.evaluate("document.getElementById('au').currentTime=3.4")
            pg.wait_for_function("document.querySelector('.ln.cur')&&document.querySelector('.ln.cur').textContent.startsWith('窗子外面有鸟叫')", timeout=5000)
            check("歌词跟着时间亮", True)
            check("进度上报到了后端", until(lambda: api("GET", "/api/now")[1].get("name") == "晨光"))
            pg.click(".ln.cur")
            pg.wait_for_selector("#sheet.on")
            pg.fill("#st", "浏览器里写的")
            pg.click("#so")
            check("批注进了 API", until(lambda: any(n["text"] == "浏览器里写的" and n["line"] == "窗子外面有鸟叫" for n in api("GET", "/api/notes")[1])))
            pg.wait_for_selector(".ln.has")
            check("歌词旁出现批注点", pg.locator(".ln.has").count() >= 1)
            api("POST", "/api/reply", {"text": "我在这儿"})
            pg.wait_for_selector(".tk.ai", timeout=6000)
            check("AI 回话浮出来", "我在这儿" in pg.locator(".tk.ai span").inner_text())
            pg.wait_for_function("document.body.classList.contains('m-安静')", timeout=15000)
            check("情绪氛围上身", True)
            api("POST", "/api/rec", {"q": "夜车", "msg": "换这首"})
            pg.evaluate("checkRecs()")
            pg.wait_for_selector("#rec.on", timeout=5000)
            check("推歌卡冒出来", "夜车" in pg.locator("#rect").inner_text())
            pg.click("#recp")
            pg.wait_for_function("document.getElementById('name').textContent==='夜车'")
            check("点卡片换歌", True)
            check("页面不能横向滚动", pg.evaluate("document.documentElement.scrollWidth<=window.innerWidth"))
            check("没有页面脚本错误", not errors, errors)
            os.makedirs(os.path.join(tmp, "shots"), exist_ok=True)
            pg.screenshot(path=os.path.join(tmp, "shots", "playing.png"))
            print("  截图在", os.path.join(tmp, "shots", "playing.png"))
            br.close()
    finally:
        srv.terminate()
        log.close()
        if fails:
            print(open(log.name).read()[-1500:])
    print()
    print("全部通过" if not fails else f"{len(fails)} 项失败：{fails}")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
