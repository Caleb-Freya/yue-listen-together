#!/usr/bin/env python3
"""一键自测（只用标准库，不碰任何真实 AI 服务）：
起一个假 OpenAI 服务、一个假 webhook 接收端、一个假 Listener，再起乐服务，把 REST / 三种接法 / MCP(http+stdio) / 命令行都走一遍。
  python tests/test_all.py
"""
import hashlib
import hmac
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
TOKEN = "test-token-" + hashlib.sha1(os.urandom(8)).hexdigest()[:8]
PASS = "2468"
SECRET = "test-secret"
class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect)
seen = {"openai": [], "webhook": []}
PORT = {}


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def http(method, url, body=None, headers=None, raw=False):
    h = {"Content-Type": "application/json"}
    h.update(headers or {})
    data = json.dumps(body, ensure_ascii=False).encode() if body is not None and not raw else body
    req = urllib.request.Request(url, data=data, headers=h, method=method)
    try:
        r = OPENER.open(req, timeout=15)
    except urllib.error.HTTPError as e:
        r = e
    b = r.read()
    try:
        return r.status, json.loads(b) if b else None, r.headers
    except Exception:
        return r.status, b, r.headers


def api(method, path, body=None, headers=None, **kw):
    return http(method, f"http://127.0.0.1:{PORT['yue']}{path}", body, dict({"Authorization": "Bearer " + TOKEN}, **(headers or {})), **kw)


# ---- 假 OpenAI ----
class MockOpenAI(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        d = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        seen["openai"].append(d)
        last = d["messages"][-1]["content"]
        reply = "无" if "song_end" in last else f"（假模型）收到：{last[:20]}"
        b = json.dumps({"choices": [{"message": {"role": "assistant", "content": reply}}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)


# ---- 假 webhook 接收端：验签 → 记事件 → 用 REST 回一句 ----
class MockHook(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"]))
        ts = self.headers.get("X-Yue-Timestamp", "")
        want = "sha256=" + hmac.new(SECRET.encode(), f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
        ok = hmac.compare_digest(want, self.headers.get("X-Yue-Signature", ""))
        ev = json.loads(body)
        seen["webhook"].append((ev, ok))
        self.send_response(200)
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"ok")
        if ok and ev["type"] == "say":
            threading.Thread(target=lambda: api("POST", "/api/reply", {"text": "（webhook 那边）我也在听"}), daemon=True).start()


def wait_port(p, t=10):
    for _ in range(int(t * 10)):
        try:
            socket.create_connection(("127.0.0.1", p), 0.3).close()
            return True
        except OSError:
            time.sleep(0.1)
    return False


def until(fn, t=8):
    for _ in range(int(t * 10)):
        if fn():
            return True
        time.sleep(0.1)
    return False


def main():
    PORT.update(yue=free_port(), openai=free_port(), hook=free_port())
    for k, H in (("openai", MockOpenAI), ("hook", MockHook)):
        s = ThreadingHTTPServer(("127.0.0.1", PORT[k]), H)
        threading.Thread(target=s.serve_forever, daemon=True).start()
    tmp = tempfile.mkdtemp(prefix="yue-test-")
    cfg = {"host": "127.0.0.1", "port": PORT["yue"], "passcode": PASS, "api_token": TOKEN, "names": {"ai": "他", "me": "我"},
           "data_dir": os.path.join(tmp, "data"), "source": {"kind": "local", "dir": os.path.join(ROOT, "tests", "music")},
           "listener": {"kind": "tests.mock_listener:MockListener"},
           "companions": [{"kind": "openai", "base_url": f"http://127.0.0.1:{PORT['openai']}/v1", "api_key": "x", "model": "mock", "min_interval": 0},
                          {"kind": "webhook", "url": f"http://127.0.0.1:{PORT['hook']}/ev", "secret": SECRET}]}
    cfgp = os.path.join(tmp, "config.json")
    json.dump(cfg, open(cfgp, "w"), ensure_ascii=False)
    logf = open(os.path.join(tmp, "server.log"), "w")
    srv = subprocess.Popen([sys.executable, os.path.join(ROOT, "run.py"), "--config", cfgp], cwd=ROOT, stdout=logf, stderr=subprocess.STDOUT)
    fails = []

    def check(name, cond, extra=""):
        print(("  通过  " if cond else "  失败  ") + name + (("  " + str(extra)[:120]) if extra and not cond else ""))
        if not cond:
            fails.append(name)

    try:
        assert wait_port(PORT["yue"]), "服务没起来"
        base = f"http://127.0.0.1:{PORT['yue']}"
        # 鉴权
        st, b, _ = http("GET", base + "/")
        check("无口令进页面 → 登录页", st == 200 and b"passcode" in b)
        st, _, _ = http("GET", base + "/api/now")
        check("无 token 调 API → 401", st == 401)
        st, _, h = http("POST", base + "/login", b"passcode=0000", {"Content-Type": "application/x-www-form-urlencoded"}, raw=True)
        check("错口令 → 401", st == 401)
        st, _, h = http("POST", base + "/login", f"passcode={PASS}".encode(), {"Content-Type": "application/x-www-form-urlencoded"}, raw=True)
        cookie = (h.get("Set-Cookie") or "").split(";")[0]
        check("对口令 → 303 + cookie", st == 303 and cookie.startswith("yue="))
        st, b, _ = http("GET", base + "/", headers={"Cookie": cookie})
        check("带 cookie 进页面 → 播放器", st == 200 and b"vinyl" in b)
        # 曲库
        st, lib, _ = api("GET", "/api/library")
        check("曲库 3 首", st == 200 and len(lib) == 3, lib)
        s1 = next(x for x in lib if x["name"] == "晨光")
        s2 = next(x for x in lib if x["name"] == "夜车")
        check("文件名 '歌手 - 歌名' 认出来", s2["artist"] == "月台")
        check("ID3 标签认出来", s1["artist"] == "测试乐队" and s1["album"] == "自测集")
        st, song, _ = api("GET", f"/api/song/{s1['id']}")
        check("歌词 + 翻译", "天还没亮透" in song["lrc"] and "Birds" in song["tlrc"])
        st, _, h = api("GET", f"/api/cover/{s1['id']}")
        check("同名封面", st == 200 and "image" in h.get("Content-Type", ""))
        st, _, h = api("GET", f"/api/audio/{s1['id']}", headers={"Range": "bytes=0-99"})
        check("音频 Range → 206", st == 206 and h.get("Content-Length") == "100", (st, h.get("Content-Length")))
        st, r, _ = api("GET", "/api/search?q=" + urllib.request.quote("夜车"))
        check("搜歌", st == 200 and len(r) == 1 and r[0]["id"] == s2["id"])
        # Listener（假的）
        st, d, _ = api("GET", f"/api/desc/{s1['id']}")
        check("desc 先 pending", d.get("pending") or d.get("segs"))
        check("假 Listener 写入 3 段", until(lambda: api("GET", f"/api/desc/{s1['id']}")[1].get("segs")), api("GET", f"/api/desc/{s1['id']}")[1])
        st, m, _ = api("GET", f"/api/mood/{s1['id']}")
        check("情绪=安静", m.get("mood") == "安静")
        # 进度上报 → 事件
        st, now, _ = api("POST", "/api/now", {"id": s1["id"], "t": 1.0, "playing": True, "duration": 20})
        check("上报后 now 有这句歌词", now["line"] == "天还没亮透" and len(now["heard"]) == 1, now)
        check("song_start 到了假 OpenAI", until(lambda: any("放了" in x["messages"][-1]["content"] for x in seen["openai"])))
        check("song_start 到了 webhook 且验签通过", until(lambda: any(e["type"] == "song_start" and ok for e, ok in seen["webhook"])))
        check("OpenAI 的回话进了浮字", until(lambda: any(x["who"] == "ai" and "假模型" in x["text"] for x in api("GET", "/api/talk?since=0")[1]["items"])))
        st, now, _ = api("POST", "/api/now", {"id": s1["id"], "t": 8.0, "playing": True})
        check("听到 8 秒只给 2 段（不剧透）", len(now["heard"]) == 2 and now["heard"][-1]["part"] == "主歌", now["heard"])
        check("segment 事件带 15s 节流：第二段暂时不发", not any(e["type"] == "segment" for e, _ in seen["webhook"]))
        # 她说话
        st, it, _ = api("POST", "/api/say", {"text": "这段像早上"})
        check("说话进浮字", st == 200 and it["who"] == "me")
        check("say 事件到了 webhook", until(lambda: any(e["type"] == "say" and e["text"] == "这段像早上" for e, _ in seen["webhook"])))
        check("webhook 用 REST 回话进了浮字", until(lambda: any("webhook 那边" in x["text"] for x in api("GET", "/api/talk?since=0")[1]["items"])))
        check("say 事件到了假 OpenAI（带正在听的歌）", until(lambda: any("这段像早上" in x["messages"][-1]["content"] and "晨光" in x["messages"][-1]["content"] for x in seen["openai"])))
        # 批注
        st, n, _ = api("POST", "/api/note", {"sid": s1["id"], "t": 3.2, "text": "这句好", "who": "me"})
        check("她写批注落在对的句子", st == 200 and n["line"] == "窗子外面有鸟叫" and n["who"] == "me", n)
        check("note 事件到了 webhook", until(lambda: any(e["type"] == "note" and e["text"] == "这句好" for e, _ in seen["webhook"])))
        st, n2, _ = api("POST", "/api/note", {"text": "我也觉得", "who": "ai"})
        check("AI 批注不给 sid 就落在此刻这句", st == 200 and n2["line"] == "你把被子拉到下巴", n2)
        st, ns, _ = api("GET", f"/api/notes/{s1['id']}")
        check("这首歌两条批注", len(ns) == 2)
        # 推歌 / 历史
        st, rec, _ = api("POST", "/api/rec", {"q": "夜车", "msg": "听这首"})
        check("按关键字推歌", st == 200 and rec["name"] == "夜车", rec)
        st, recs, _ = api("GET", "/api/recs")
        check("推荐列表", recs and recs[0]["id"] == s2["id"] and not recs[0]["seen"])
        st, hs, _ = api("GET", "/api/history")
        check("一起听过里有晨光", any(x["id"] == s1["id"] and x["notes"] == 2 for x in hs), hs)
        # 放完
        st, now, _ = api("POST", "/api/now", {"id": s1["id"], "t": 20, "playing": False, "ended": True})
        check("song_end 到了 webhook", until(lambda: any(e["type"] == "song_end" and "极简" in e.get("whole", "") for e, _ in seen["webhook"])))
        # MCP over HTTP
        mcp = lambda m: api("POST", "/mcp", m)[1]
        r = mcp({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "t", "version": "0"}}})
        check("MCP http initialize", r["result"]["serverInfo"]["name"] == "乐", r)
        st, _, _ = api("POST", "/mcp", {"jsonrpc": "2.0", "method": "notifications/initialized"})
        check("MCP 通知 → 202", st == 202)
        r = mcp({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        names = [t["name"] for t in r["result"]["tools"]]
        check("MCP 工具列表", names == ["now", "say", "note", "push_song", "notes", "recent_talk", "search"], names)
        call = lambda n, a: mcp({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": n, "arguments": a}})["result"]
        r = call("now", {})
        check("MCP now", "晨光" in r["content"][0]["text"] and "前奏" in r["content"][0]["text"], r)
        r = call("say", {"text": "MCP 来的一句"})
        check("MCP say", until(lambda: any(x["text"] == "MCP 来的一句" for x in api("GET", "/api/talk/recent?n=20")[1])))
        r = call("note", {"text": "MCP 批注", "t": 12.5})
        check("MCP note", "我数到三百" in r["content"][0]["text"], r)
        r = call("push_song", {"query": "晨光", "message": "再听一遍"})
        check("MCP push_song", "晨光" in r["content"][0]["text"], r)
        r = call("notes", {"n": 5})
        check("MCP notes", "MCP 批注" in r["content"][0]["text"])
        r = call("recent_talk", {})
        check("MCP recent_talk", "MCP 来的一句" in r["content"][0]["text"])
        r = call("search", {"query": "无词"})
        check("MCP search", "无词曲" in r["content"][0]["text"])
        r = mcp({"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "nope", "arguments": {}}})
        check("MCP 未知工具报错", "error" in r, r)
        # MCP over stdio
        p = subprocess.Popen([sys.executable, os.path.join(ROOT, "run.py"), "--config", cfgp, "mcp"], cwd=ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        msgs = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "t", "version": "0"}}},
                {"jsonrpc": "2.0", "method": "notifications/initialized"},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
                {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "now", "arguments": {}}},
                {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "say", "arguments": {"text": "stdio 来的"}}}]
        out, _ = p.communicate("\n".join(json.dumps(m) for m in msgs) + "\n", timeout=20)
        lines = [json.loads(l) for l in out.splitlines() if l.strip()]
        check("MCP stdio 回了 4 条（通知不回）", len(lines) == 4, out[:200])
        check("MCP stdio tools/list", len(lines[1]["result"]["tools"]) == 7)
        check("MCP stdio now（走 REST 到服务）", "晨光" in lines[2]["result"]["content"][0]["text"], lines[2])
        check("MCP stdio say 落到浮字", until(lambda: any(x["text"] == "stdio 来的" for x in api("GET", "/api/talk/recent?n=30")[1])))
        # 命令行
        env = dict(os.environ, YUE_URL=base, YUE_TOKEN=TOKEN, YUE_CONFIG=cfgp)
        r = subprocess.run([sys.executable, os.path.join(ROOT, "bin", "yue"), "now"], cwd=ROOT, env=env, capture_output=True, text=True, timeout=20)
        check("bin/yue now", "晨光" in r.stdout, r.stdout + r.stderr)
        r = subprocess.run([sys.executable, os.path.join(ROOT, "bin", "yue"), "notes", "3"], cwd=ROOT, env=env, capture_output=True, text=True, timeout=20)
        check("bin/yue notes", "批注" in r.stdout or "好" in r.stdout, r.stdout + r.stderr)
        # push-off
        open(os.path.join(cfg["data_dir"], "push-off"), "w").close()
        n0 = len(seen["webhook"])
        api("POST", "/api/say", {"text": "这句不该发出去"})
        time.sleep(0.8)
        check("push-off 存在时不发事件", len(seen["webhook"]) == n0)
        os.remove(os.path.join(cfg["data_dir"], "push-off"))
        # 检查所有 webhook 签名
        check("webhook 全部验签通过", all(ok for _, ok in seen["webhook"]) and seen["webhook"])
        check("token 没出现在日志里", TOKEN not in open(logf.name).read())
    finally:
        srv.terminate()
        try:
            srv.wait(5)
        except Exception:
            srv.kill()
        logf.close()
        if fails:
            print("---- 服务日志 ----")
            print(open(logf.name).read()[-2000:])
        shutil.rmtree(tmp, ignore_errors=True)
    print()
    print("全部通过" if not fails else f"{len(fails)} 项失败：{fails}")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
