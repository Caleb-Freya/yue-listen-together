"""HTTP 服务：页面 + REST + MCP(streamable HTTP)。只用标准库。

页面：GET /            （有口令时先到登录页）
鉴权：页面靠 cookie；/api/* 和 /mcp 认 cookie 或 Authorization: Bearer <api_token>。
REST（给外部系统/AI 用的都标了 ★）：
  GET  /api/config                页面要的公开配置（称呼、有哪些图）
  GET  /api/library               本地库全部
  GET  /api/search?q=             找歌 ★
  GET  /api/song/<id>             歌曲信息+歌词
  GET  /api/audio/<id>            音频（支持 Range）
  GET  /api/cover/<id>            封面
  GET  /api/desc/<id>             听歌描述（pending / disabled）
  GET  /api/mood/<id>             情绪
  GET  /api/now  POST /api/now    现在放到哪 ★ / 页面上报 {id,t,playing,ended,duration}
  GET  /api/notes?n=  /api/notes/<id>   批注 ★
  POST /api/note {sid,t,line,text,who}  写批注 ★（who=ai 时 sid/t 可省，取此刻）
  POST /api/note/del {id}
  GET  /api/history  GET /api/recs      一起听过 / 推的歌
  POST /api/rec {q|sid, msg}            推歌 ★
  POST /api/say {text}                  她对 AI 说话（触发事件）
  POST /api/reply {text}                AI 回话，浮在页面上 ★
  GET  /api/talk?since=  /api/talk/recent?n=   浮字对话 ★
  POST /mcp                             MCP streamable HTTP ★
"""
import hashlib
import hmac
import json
import mimetypes
import os
import re
import secrets
import ssl
import sys
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import mcp
from .app import App, log

HERE = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.join(os.path.dirname(HERE), "web")

LOGIN_HTML = """<!doctype html><html lang="zh"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1">
<title>{title}</title><style>html,body{{margin:0;height:100%;background:#141a2e;color:#f4ead8;font-family:"Songti SC","Noto Serif SC",serif;display:flex;align-items:center;justify-content:center}}
form{{text-align:center}}h1{{font-weight:normal;letter-spacing:6px;color:#f1dcae;font-size:26px}}
input{{width:200px;height:40px;border-radius:20px;border:1px solid rgba(216,183,122,.5);background:rgba(255,255,255,.05);color:#f4ead8;text-align:center;font-size:18px;outline:none;letter-spacing:4px}}
button{{display:block;margin:16px auto 0;height:36px;padding:0 24px;border-radius:18px;border:1px solid rgba(216,183,122,.6);background:rgba(216,183,122,.15);color:#f1dcae;font-size:14px}}
p{{color:rgba(244,234,216,.5);font-size:13px}}</style></head><body><form method="post" action="login"><h1>{title}</h1>
<input name="passcode" type="password" inputmode="numeric" autofocus placeholder="口令"><button>进</button><p>{msg}</p></form></body></html>"""


class Auth:
    def __init__(self, cfg):
        self.passcode = str(cfg.get("passcode") or "")
        self.token = str(cfg.get("api_token") or "")
        sf = os.path.join(cfg["data_dir"], ".secret")
        if not os.path.exists(sf):
            with open(sf, "w") as f:
                f.write(secrets.token_hex(32))
            os.chmod(sf, 0o600)
        self.secret = open(sf).read().strip()

    def cookie_value(self):
        return hmac.new(self.secret.encode(), self.passcode.encode(), hashlib.sha256).hexdigest()

    def page_ok(self, h):
        if not self.passcode:
            return True
        c = h.get("Cookie") or ""
        m = re.search(r"(?:^|;\s*)yue=([0-9a-f]+)", c)
        return bool(m and hmac.compare_digest(m.group(1), self.cookie_value()))

    def api_ok(self, h, query=None):
        """cookie、Authorization: Bearer、X-Api-Key、或 ?token=（给没法自定义请求头的 MCP 客户端用）任一对上即可。"""
        if self.page_ok(h):
            return True
        if not self.token:
            return False
        a = h.get("Authorization") or ""
        cands = [a[7:].strip() if a.startswith("Bearer ") else "", h.get("X-Api-Key") or "", (query or {}).get("token") or ""]
        return any(c and hmac.compare_digest(c, self.token) for c in cands)


def make_handler(app, auth):
    cfg = app.cfg
    mcp_backend = mcp.Backend(app=app)

    class H(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *a):
            pass

        # ---- 小工具 ----
        def j(self, obj, code=200, headers=None):
            b = json.dumps(obj, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(b)))
            self.send_header("Cache-Control", "no-store")
            for k, v in (headers or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(b)

        def raw(self, b, ctype, code=200, cache="no-cache", headers=None):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(b)))
            self.send_header("Cache-Control", cache)
            for k, v in (headers or {}).items():
                self.send_header(k, v)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(b)

        def send_file(self, path, cache="no-cache", ranged=False):
            ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
            if path.endswith(".flac"):
                ctype = "audio/flac"
            if path.endswith(".m4a"):
                ctype = "audio/mp4"
            size = os.path.getsize(path)
            start, end = 0, size - 1
            code = 200
            rg = self.headers.get("Range") if ranged else None
            m = rg and re.match(r"bytes=(\d*)-(\d*)", rg)
            if m and (m.group(1) or m.group(2)):
                if m.group(1):
                    start = int(m.group(1))
                    end = int(m.group(2)) if m.group(2) else size - 1
                else:
                    start = max(0, size - int(m.group(2)))
                end = min(end, size - 1)
                if start > end:
                    self.send_response(416)
                    self.send_header("Content-Range", f"bytes */{size}")
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                code = 206
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(end - start + 1))
            self.send_header("Cache-Control", cache)
            if ranged:
                self.send_header("Accept-Ranges", "bytes")
            if code == 206:
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.end_headers()
            if self.command == "HEAD":
                return
            with open(path, "rb") as f:
                f.seek(start)
                left = end - start + 1
                try:
                    while left > 0:
                        chunk = f.read(min(65536, left))
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                        left -= len(chunk)
                except (BrokenPipeError, ConnectionResetError):
                    pass

        def relay(self, url, headers=None, cache=None):
            h = dict(headers or {})
            if self.headers.get("Range"):
                h["Range"] = self.headers["Range"]
            req = urllib.request.Request(url, headers=h)
            try:
                r = urllib.request.urlopen(req, timeout=20, context=ssl.create_default_context())
            except urllib.error.HTTPError as e:
                r = e
            self.send_response(r.status)
            for k in ("Content-Type", "Content-Length", "Content-Range", "Accept-Ranges"):
                if r.headers.get(k):
                    self.send_header(k, r.headers[k])
            if cache:
                self.send_header("Cache-Control", cache)
            if not r.headers.get("Content-Length"):
                self.send_header("Connection", "close")
            self.end_headers()
            try:
                while True:
                    chunk = r.read(65536)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
            except (BrokenPipeError, ConnectionResetError):
                pass
            finally:
                r.close()
                if not r.headers.get("Content-Length"):
                    self.close_connection = True

        def send_media(self, m, cache="public, max-age=86400", ranged=False):
            if not m:
                return self.j({"error": "not found"}, 404)
            if m[0] == "file":
                return self.send_file(m[1], cache, ranged) if os.path.exists(m[1]) else self.j({"error": "file missing"}, 404)
            if m[0] == "url":
                return self.relay(m[1], m[2] if len(m) > 2 else None, cache)
            if m[0] == "bytes":
                return self.raw(m[1], m[2], cache=cache)
            return self.j({"error": "bad media"}, 500)

        def body(self):
            n = int(self.headers.get("Content-Length") or 0)
            return self.rfile.read(n) if n else b""

        # ---- 路由 ----
        def do_HEAD(self):
            self.do_GET()

        def do_GET(self):
            u = urlparse(self.path)
            p, q = u.path, {k: v[0] for k, v in parse_qs(u.query).items()}
            try:
                if p in ("/", "/index.html"):
                    if not auth.page_ok(self.headers):
                        return self.raw(LOGIN_HTML.format(title=cfg["title"], msg="").encode(), "text/html; charset=utf-8")
                    return self.send_file(os.path.join(WEB, "index.html"))
                if p == "/login":
                    return self.raw(LOGIN_HTML.format(title=cfg["title"], msg="").encode(), "text/html; charset=utf-8")
                m = re.match(r"^/img/(background|tonearm|idle_cover|avatar_ai|avatar_me)$", p)
                if m:
                    f = cfg["images"].get(m.group(1))
                    return self.send_file(f, "public, max-age=604800") if f and os.path.exists(f) else self.j({"error": "no image"}, 404)
                if p.startswith("/api/") or p == cfg["mcp"].get("path", "/mcp"):
                    if not auth.api_ok(self.headers, q):
                        return self.j({"error": "unauthorized"}, 401)
                if p == cfg["mcp"].get("path", "/mcp"):
                    return self.j({"error": "use POST"}, 405)
                if p == "/api/config":
                    im = {k: bool(v and os.path.exists(v)) for k, v in cfg["images"].items()}
                    return self.j({"title": cfg["title"], "names": cfg["names"], "images": im, "listener": app.listener.enabled,
                                   "build": int(os.path.getmtime(os.path.join(WEB, "index.html")))})
                if p == "/api/library":
                    return self.j(app.source.all())
                if p == "/api/search":
                    return self.j(app.source.search(q.get("q", ""), int(q.get("n", 20))))
                if p == "/api/now":
                    return self.j(app.now())
                if p == "/api/history":
                    return self.j(app.store.history())
                if p == "/api/recs":
                    return self.j(app.store.recs())
                if p == "/api/notes":
                    return self.j(app.store.notes(n=int(q.get("n", 50))))
                m = re.match(r"^/api/notes/([\w.-]+)$", p)
                if m:
                    return self.j(app.store.notes(sid=m.group(1)))
                if p == "/api/talk":
                    import time
                    return self.j({"now": time.time(), "items": app.store.talk_since(float(q.get("since", 0) or 0))})
                if p == "/api/talk/recent":
                    return self.j(app.store.talk_recent(int(q.get("n", 10))))
                m = re.match(r"^/api/(song|audio|cover|desc|mood)/([\w.-]+)$", p)
                if m:
                    kind, sid = m.groups()
                    if kind == "song":
                        s = app.song(sid)
                        return self.j(s) if s else self.j({"error": "not found"}, 404)
                    if kind == "audio":
                        return self.send_media(app.source.audio(sid), "no-cache", ranged=True)
                    if kind == "cover":
                        return self.send_media(app.source.cover(sid), "public, max-age=2592000")
                    if kind == "desc":
                        return self.j(app.desc(sid))
                    if kind == "mood":
                        return self.j({"mood": app.mood(sid)})
                return self.j({"error": "not found"}, 404)
            except Exception as e:
                log("GET", p, repr(e)[:200])
                try:
                    return self.j({"error": "server"}, 500)
                except Exception:
                    pass

        def do_POST(self):
            u = urlparse(self.path)
            p, q = u.path, {k: v[0] for k, v in parse_qs(u.query).items()}
            raw = self.body()
            try:
                if p == "/login":
                    d = {k: v[0] for k, v in parse_qs(raw.decode("utf-8", "replace")).items()}
                    if auth.passcode and hmac.compare_digest(d.get("passcode", ""), auth.passcode):
                        return self.raw(b"", "text/plain", 303, headers={"Location": "./", "Set-Cookie": f"yue={auth.cookie_value()}; Path=/; Max-Age=31536000; SameSite=Lax; HttpOnly"})
                    return self.raw(LOGIN_HTML.format(title=cfg["title"], msg="口令不对").encode(), "text/html; charset=utf-8", 401)
                if not auth.api_ok(self.headers, q):
                    return self.j({"error": "unauthorized"}, 401)
                if p == cfg["mcp"].get("path", "/mcp"):
                    if not cfg["mcp"].get("http", True):
                        return self.j({"error": "mcp http disabled"}, 404)
                    try:
                        msg = json.loads(raw or b"{}")
                    except Exception:
                        return self.j({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}}, 400)
                    msgs = msg if isinstance(msg, list) else [msg]
                    out = [r for r in (mcp.handle(m, mcp_backend, cfg["title"]) for m in msgs) if r is not None]
                    if not out:
                        return self.raw(b"", "text/plain", 202)
                    return self.j(out if isinstance(msg, list) else out[0], headers={"Mcp-Session-Id": "yue"})
                try:
                    d = json.loads(raw or b"{}")
                except Exception:
                    return self.j({"error": "bad json"}, 400)
                if p == "/api/now":
                    sid = str(d.get("id") or "")
                    if not sid:
                        return self.j({"error": "no id"}, 400)
                    return self.j(app.report(sid, d.get("t") or 0, d.get("playing"), d.get("ended"), float(d.get("duration") or 0)))
                if p == "/api/note":
                    text = str(d.get("text") or "").strip()
                    if not text:
                        return self.j({"error": "empty"}, 400)
                    who = "ai" if d.get("who") == "ai" else "me"
                    sid = str(d.get("sid") or "")
                    if who == "ai" and not sid:
                        return self.j(app.ai_note(text, t=d.get("t")))
                    return self.j(app.add_note(sid, d.get("t") or 0, text, who, str(d.get("line") or "")))
                if p == "/api/note/del":
                    app.store.del_note(int(d.get("id") or 0))
                    return self.j({"ok": True})
                if p == "/api/say":
                    return self.j(app.she_says(d.get("text")))
                if p == "/api/reply":
                    return self.j(app.ai_say(d.get("text")))
                if p == "/api/rec":
                    return self.j(app.push_song(str(d.get("sid") or d.get("q") or ""), str(d.get("msg") or "")))
                if p == "/api/rec/seen":
                    app.store.mark_rec_seen(rid=int(d.get("id") or 0))
                    return self.j({"ok": True})
                return self.j({"error": "not found"}, 404)
            except (ValueError, LookupError) as e:
                return self.j({"error": str(e) or "bad request"}, 400)
            except Exception as e:
                log("POST", p, repr(e)[:200])
                try:
                    return self.j({"error": "server"}, 500)
                except Exception:
                    pass

    return H


def serve(cfg):
    app = App(cfg)
    auth = Auth(cfg)
    host, port = cfg["host"], int(cfg["port"])
    if host not in ("127.0.0.1", "localhost", "::1") and not cfg.get("passcode"):
        log("警告：绑在了非本机地址却没设 passcode，谁都能打开页面")
    if not cfg.get("api_token"):
        log("提示：api_token 为空，外部系统/MCP stdio 没法调用 API（页面本身不受影响）")
    log(f"乐 已启动 http://{host}:{port}/  来源={cfg['source'].get('kind')}  听歌={cfg['listener'].get('kind')}  陪听={[c.item.get('kind') for c in app.bus.items]}")
    srv = ThreadingHTTPServer((host, port), make_handler(app, auth))
    srv.daemon_threads = True
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
