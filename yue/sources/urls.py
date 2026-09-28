"""直接 URL 列表来源：一个 json 文件，每首写 url + 歌词。适合放在自己的网盘/对象存储/静态站上的音乐。

songs.json 长这样：
[
  {"id": "可选，不写就按 url 生成", "name": "歌名", "artist": "歌手", "album": "可选",
   "url": "https://example.com/a.mp3",
   "lrc": "可以是 LRC 文本，也可以是 .lrc 文件路径或 URL",
   "tlrc": "翻译，同上，可选",
   "cover": "图片路径或 URL，可选",
   "headers": {"可选": "请求音频时带的头"}}
]
"""
import hashlib
import json
import os
import urllib.request

from . import MusicSource


class UrlListSource(MusicSource):
    def __init__(self, cfg):
        super().__init__(cfg)
        self.file = cfg["source"].get("file") or os.path.join(cfg["_dir"], "songs.json")
        self._mtime = None
        self._songs = {}
        self._text_cache = {}

    def _load(self):
        try:
            mt = os.path.getmtime(self.file)
        except OSError:
            self._songs = {}
            return
        if mt == self._mtime:
            return
        self._mtime = mt
        songs = {}
        for x in json.load(open(self.file, encoding="utf-8")):
            sid = str(x.get("id") or hashlib.sha1(x["url"].encode()).hexdigest()[:12])
            songs[sid] = dict(x, id=sid, name=x.get("name") or x["url"].rsplit("/", 1)[-1],
                              artist=x.get("artist", ""), album=x.get("album", ""), duration=x.get("duration", 0))
        self._songs = songs

    def _text(self, v):
        """lrc 字段：本身是 LRC 文本 / 本地路径 / URL。"""
        if not v:
            return ""
        if "[" in v and "\n" in v or v.lstrip().startswith("["):
            return v
        if v in self._text_cache:
            return self._text_cache[v]
        t = ""
        try:
            if v.startswith(("http://", "https://")):
                t = urllib.request.urlopen(v, timeout=15).read().decode("utf-8", "replace")
            else:
                p = v if os.path.isabs(v) else os.path.join(os.path.dirname(self.file), v)
                t = open(p, encoding="utf-8", errors="replace").read()
        except Exception:
            t = ""
        self._text_cache[v] = t
        return t

    def all(self):
        self._load()
        return [{k: v for k, v in s.items() if k in ("id", "name", "artist", "album", "duration")} | {"has_cover": bool(s.get("cover"))}
                for s in self._songs.values()]

    def song(self, sid):
        self._load()
        s = self._songs.get(sid)
        if not s:
            return None
        return {"id": sid, "name": s["name"], "artist": s["artist"], "album": s["album"], "duration": s.get("duration", 0),
                "lrc": self._text(s.get("lrc")), "tlrc": self._text(s.get("tlrc")), "has_cover": bool(s.get("cover")), "playable": True}

    def audio(self, sid):
        self._load()
        s = self._songs.get(sid)
        if not s:
            return None
        u = s["url"]
        if u.startswith(("http://", "https://")):
            return ("url", u, s.get("headers") or {})
        return ("file", u if os.path.isabs(u) else os.path.join(os.path.dirname(self.file), u))

    def cover(self, sid):
        self._load()
        s = self._songs.get(sid)
        c = s and s.get("cover")
        if not c:
            return None
        if c.startswith(("http://", "https://")):
            return ("url", c, {})
        return ("file", c if os.path.isabs(c) else os.path.join(os.path.dirname(self.file), c))

    def public_audio_url(self, sid):
        self._load()
        s = self._songs.get(sid)
        u = s and s["url"]
        return u if u and u.startswith("https://") and not s.get("headers") else None
