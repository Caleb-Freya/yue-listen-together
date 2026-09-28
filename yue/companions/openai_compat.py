"""OpenAI 兼容接法：事件发生时调一次聊天模型，它说的话浮在页面上。
节流：她说话/写批注一定回；放歌/进段落/放完这类事件之间至少隔 min_interval 秒。历史只带最近 history 条。"""
import json
import ssl
import threading
import time
import urllib.request

from . import Companion
from ..lyrics import mmss

DEFAULT_SYSTEM = ("你在陪{me}一起听歌。她的播放器会把此刻发生的事告诉你（放了哪首、唱到哪句、音乐进到哪一段、她说了什么、她写了什么批注）。"
                  "你像坐在旁边一起听的人那样说话：一两句，口语，不要列点，不要客套，不要复述歌词，可以接着她的话聊，"
                  "也可以说你对这段音乐的感觉。没什么想说的时候只回一个字：无。")


class OpenAICompanion(Companion):
    def __init__(self, cfg, item):
        super().__init__(cfg, item)
        self.lock = threading.Lock()
        self.last = 0

    def _chat(self, messages):
        it = self.item
        body = {"model": it.get("model", "gpt-4o-mini"), "messages": messages, "temperature": it.get("temperature", 0.9),
                "max_tokens": it.get("max_tokens", 200)}
        req = urllib.request.Request(it.get("base_url", "https://api.openai.com/v1").rstrip("/") + "/chat/completions",
                                     data=json.dumps(body, ensure_ascii=False).encode(),
                                     headers={"Authorization": "Bearer " + it.get("api_key", ""), "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=int(it.get("timeout", 60)), context=ssl.create_default_context()) as r:
            d = json.loads(r.read().decode("utf-8"))
        return ((d.get("choices") or [{}])[0].get("message") or {}).get("content") or ""

    def describe(self, ev, app):
        names = self.cfg["names"]
        s = ev.get("song") or {}
        head = f"《{s.get('name', '')}》- {s.get('artist', '')}"
        t = ev.get("type")
        if t == "song_start":
            return f"[事件] {names['me']}放了 {head}。"
        if t == "segment":
            g = ev.get("seg") or {}
            return f"[事件] {head} 到了 {mmss(ev.get('t'))}，{g.get('part', '')}：{g.get('hear', '')}" + (f"\n此刻这句歌词：{ev['line']}" if ev.get("line") else "")
        if t == "song_end":
            return f"[事件] {head} 放完了。" + (f"整首听下来：{ev['whole']}" if ev.get("whole") else "")
        if t == "note":
            return f"[事件] {names['me']}在「{ev.get('line', '')}」这句下写了批注：{ev.get('text', '')}"
        if t == "say":
            ctx = f"（正在听 {head}" + (f"，唱到「{ev['line']}」" if ev.get("line") else "") + "）" if s.get("name") else ""
            return f"{ctx}{ev.get('text', '')}"
        return ""

    def on_event(self, ev, app):
        it = self.item
        urgent = ev["type"] in ("say", "note")
        with self.lock:
            if not urgent and time.time() - self.last < float(it.get("min_interval", 20)):
                return
            self.last = time.time()
            names = self.cfg["names"]
            system = (it.get("system") or DEFAULT_SYSTEM).replace("{me}", names["me"]).replace("{ai}", names["ai"])
            msgs = [{"role": "system", "content": system}]
            for x in app.store.talk_recent(int(it.get("history", 8))):
                msgs.append({"role": "assistant" if x["who"] == "ai" else "user", "content": x["text"]})
            msgs.append({"role": "user", "content": self.describe(ev, app)})
            text = self._chat(msgs).strip()
            if not text or text in ("无", "无。", "（无）"):
                return
            app.ai_say(text)
