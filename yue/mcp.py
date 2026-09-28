"""MCP 服务器（不依赖任何三方库，自己说 JSON-RPC）。
两种传输：
  stdio          —— `python run.py mcp`：本进程只是个薄壳，工具调用走 REST 到正在跑的乐服务（要 config 里的 api_token）。
  streamable HTTP —— 乐服务自己在 /mcp 收 POST（Authorization: Bearer <api_token>）。
工具：now / note / push_song / say / notes / recent_talk / search
"""
import json
import sys
import urllib.request

from .lyrics import mmss

PROTOCOL = "2025-03-26"

TOOLS = [
    {"name": "now",
     "description": ("她正在一起听歌时，回话前先调这个。返回：正在放哪首、放到第几秒、此刻唱到哪句歌词、以及音乐到目前为止已经听到的段落"
                     "（前奏/主歌/副歌…每段听到了什么乐器/情绪）。只给已经听到的部分，后面的不剧透——你也别提还没到的段落。没放歌会直接说。"),
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "say",
     "description": "对她说一句话，会浮在她的播放页面上（无框、几秒后淡出）。一两句口语就好，像坐在旁边一起听的人。",
     "inputSchema": {"type": "object", "properties": {"text": {"type": "string", "description": "要说的话"}}, "required": ["text"]}},
    {"name": "note",
     "description": "在她此刻正在听的那句歌词下留一条批注（以后再放到这句时会冒出来，像在歌词旁写字）。要对具体某一句说话时用它，闲聊用 say。",
     "inputSchema": {"type": "object", "properties": {"text": {"type": "string", "description": "批注内容"},
                                                      "t": {"type": "number", "description": "可选，秒；不填就是此刻这句"}},
                     "required": ["text"]}},
    {"name": "push_song",
     "description": "推一首歌给她：她页面顶上会出一张卡，点了就放。曲库里有的歌才推得了，不确定先用 search 找。",
     "inputSchema": {"type": "object", "properties": {"query": {"type": "string", "description": "歌名/歌手关键字，或 search 给的歌曲 id"},
                                                      "message": {"type": "string", "description": "附一句为什么想一起听，可选"}}, "required": ["query"]}},
    {"name": "notes",
     "description": "最近的听歌批注（她写的和你写的都有，带歌名和那句歌词）。想接着之前的话聊时看看。",
     "inputSchema": {"type": "object", "properties": {"n": {"type": "integer", "description": "条数，默认 10"}}}},
    {"name": "recent_talk",
     "description": "你们最近在播放页里说过的话（她在底部输入的、你用 say 说的）。",
     "inputSchema": {"type": "object", "properties": {"n": {"type": "integer", "description": "条数，默认 10"}}}},
    {"name": "search",
     "description": "在她的曲库里找歌，返回 id、歌名、歌手。push_song 之前用。",
     "inputSchema": {"type": "object", "properties": {"query": {"type": "string", "description": "关键字"}}, "required": ["query"]}},
]


def fmt_now(d, names):
    if not d.get("id"):
        return f"{names['me']}还没放歌。"
    st = "在放" if d.get("playing") else "停着"
    out = [f"《{d['name']}》- {d['artist']}  {mmss(d['t'])}  {st}", "这句：" + (d.get("line") or "（间奏）")]
    for x in d.get("heard", []):
        out.append(f"  {mmss(x['start'])} {x['part']}：{x['hear']}")
    return "\n".join(out)


def fmt_notes(a, names):
    return "\n".join(f"{names['ai'] if n['who'] == 'ai' else names['me']}｜《{n['song']}》「{n['line']}」：{n['text']}" for n in a) or "还没有批注。"


def fmt_talk(a, names):
    return "\n".join(f"{names['ai'] if x['who'] == 'ai' else names['me']}：{x['text']}" for x in a) or "还没说过话。"


class Backend:
    """工具的实际执行者：本进程的 App，或 REST 客户端（stdio 模式）。"""

    def __init__(self, app=None, base=None, token=None, names=None):
        self.app, self.base, self.token = app, base, token
        self.names = names or (app.cfg["names"] if app else {"ai": "他", "me": "我"})

    def _rest(self, path, body=None):
        req = urllib.request.Request(self.base + path, data=json.dumps(body, ensure_ascii=False).encode() if body is not None else None,
                                     headers={"Authorization": "Bearer " + (self.token or ""), "Content-Type": "application/json"})
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req, timeout=30) as r:
            return json.loads(r.read().decode())

    def call(self, name, a):
        n = self.names
        if name == "now":
            return fmt_now(self.app.now() if self.app else self._rest("/api/now"), n)
        if name == "say":
            self.app.ai_say(a["text"]) if self.app else self._rest("/api/reply", {"text": a["text"]})
            return "说了。"
        if name == "note":
            r = self.app.ai_note(a["text"], t=a.get("t")) if self.app else self._rest("/api/note", {"text": a["text"], "who": "ai", "t": a.get("t")})
            return "留在了「" + (r.get("line") or "间奏") + "」下面。"
        if name == "push_song":
            r = self.app.push_song(a["query"], a.get("message", "")) if self.app else self._rest("/api/rec", {"q": a["query"], "msg": a.get("message", "")})
            return f"推过去了：《{r['name']}》- {r['artist']}。她开着页面会在顶上看到。"
        if name == "notes":
            k = int(a.get("n") or 10)
            return fmt_notes(self.app.store.notes(n=k) if self.app else self._rest(f"/api/notes?n={k}"), n)
        if name == "recent_talk":
            k = int(a.get("n") or 10)
            return fmt_talk(self.app.store.talk_recent(k) if self.app else self._rest(f"/api/talk/recent?n={k}"), n)
        if name == "search":
            r = self.app.source.search(a["query"], 20) if self.app else self._rest("/api/search?q=" + urllib.request.quote(a["query"]))
            return "\n".join(f"{s['id']}  《{s['name']}》- {s.get('artist', '')}" for s in r) or "没找到。"
        raise KeyError(name)


def handle(msg, backend, server_name="yue"):
    """处理一条 JSON-RPC 消息；通知返回 None。"""
    mid, method, params = msg.get("id"), msg.get("method", ""), msg.get("params") or {}
    if method.startswith("notifications/") or mid is None and method:
        return None

    def ok(result):
        return {"jsonrpc": "2.0", "id": mid, "result": result}

    def err(code, text):
        return {"jsonrpc": "2.0", "id": mid, "error": {"code": code, "message": text}}

    if method == "initialize":
        return ok({"protocolVersion": params.get("protocolVersion") or PROTOCOL, "capabilities": {"tools": {}},
                   "serverInfo": {"name": server_name, "version": "1.0"}})
    if method == "ping":
        return ok({})
    if method == "tools/list":
        return ok({"tools": TOOLS})
    if method == "tools/call":
        name, args = params.get("name"), params.get("arguments") or {}
        try:
            text = backend.call(name, args)
            return ok({"content": [{"type": "text", "text": text}], "isError": False})
        except KeyError:
            return err(-32602, f"没有这个工具：{name}")
        except Exception as e:
            return ok({"content": [{"type": "text", "text": "出错了：" + str(e)[:200]}], "isError": True})
    if method in ("resources/list", "prompts/list"):
        return ok({"resources": [], "prompts": []})
    return err(-32601, f"不支持：{method}")


def stdio_main(cfg):
    base = f"http://127.0.0.1:{cfg['port']}"
    backend = Backend(base=base, token=cfg.get("api_token"), names=cfg["names"])
    out = sys.stdout
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except Exception:
            continue
        msgs = msg if isinstance(msg, list) else [msg]
        for m in msgs:
            r = handle(m, backend)
            if r is not None:
                out.write(json.dumps(r, ensure_ascii=False) + "\n")
                out.flush()
