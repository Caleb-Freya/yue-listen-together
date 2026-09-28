"""陪听的 AI 怎么接进来。三种内置接法：
  openai   —— 后端自己调一个 OpenAI 兼容的聊天模型，事件发生时让它说一句。
  webhook  —— 把事件 POST 到你的地址（带签名），你的系统用 REST（带 token）回话/批注/推歌。
  （MCP 不在这里：MCP 是 AI 主动来问，见 yue/mcp.py。）

事件（ev）长这样：
  {"type": "song_start|segment|say|note|song_end", "at": 时间戳,
   "song": {"id","name","artist"}, "t": 秒, "line": "此刻歌词",
   "seg": {"start","part","hear"}(仅 segment), "heard": [已经听到的段落],
   "text": 她说的话/批注(仅 say/note), "whole": 整首感觉(仅 song_end)}
自己写一个：继承 Companion 实现 on_event(ev, app)，config 的 companions 里 kind 写 "你的包.模块:类名"。
"""
import threading
import traceback

from ..plugins import load_class

BUILTIN = {
    "openai": "yue.companions.openai_compat:OpenAICompanion",
    "webhook": "yue.companions.webhook:WebhookCompanion",
}


class Companion:
    def __init__(self, cfg, item):
        self.cfg = cfg
        self.item = item
        self.events = set(item.get("events") or ["song_start", "segment", "say", "note", "song_end"])

    def on_event(self, ev, app):
        raise NotImplementedError


class Bus:
    def __init__(self, cfg, log):
        self.log = log
        self.items = []
        for item in cfg.get("companions", []):
            if not item.get("enabled", True):
                continue
            try:
                self.items.append(load_class(item.get("kind", ""), BUILTIN)(cfg, item))
            except Exception as e:
                log("companion 装不上：", item.get("kind"), repr(e)[:160])

    def emit(self, ev, app):
        for c in self.items:
            if ev["type"] not in c.events:
                continue

            def run(c=c):
                try:
                    c.on_event(ev, app)
                except Exception:
                    self.log("companion", c.item.get("kind"), "出错：", traceback.format_exc()[-300:])
            threading.Thread(target=run, daemon=True).start()
