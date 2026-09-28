"""音乐来源接口。自己写来源插件：继承 MusicSource，实现下面几个方法，config 里 source.kind 写 "你的包.模块:类名"。

歌曲 dict 统一长这样（search / all / song 都返回它，song 多带歌词）：
  {"id": "字符串id", "name": "歌名", "artist": "歌手", "album": "专辑", "duration": 秒(可 0),
   "lrc": "LRC 文本", "tlrc": "翻译 LRC 文本", "has_cover": bool, "playable": bool}
"""
from ..plugins import load_class

BUILTIN = {
    "local": "yue.sources.local:LocalFolderSource",
    "urls": "yue.sources.urls:UrlListSource",
}


class MusicSource:
    def __init__(self, cfg):
        self.cfg = cfg

    def search(self, q, limit=20):
        """按关键字找歌，返回歌曲 dict 列表（可不带歌词）。"""
        k = (q or "").strip().lower()
        if not k:
            return self.all()[:limit]
        return [s for s in self.all() if k in (s["name"] + " " + s.get("artist", "") + " " + s.get("album", "")).lower()][:limit]

    def all(self):
        """整个曲库（歌单里"本地库"那一栏）。来源太大的可以返回 []。"""
        return []

    def song(self, sid):
        """一首歌的完整信息（含 lrc/tlrc），没有返回 None。"""
        raise NotImplementedError

    def audio(self, sid):
        """音频怎么拿：("file", 本地路径) 或 ("url", 地址, 额外请求头 dict)；没有返回 None。"""
        raise NotImplementedError

    def cover(self, sid):
        """封面：("file", 路径) / ("url", 地址, 头) / ("bytes", 二进制, mime)；没有返回 None。"""
        return None

    def public_audio_url(self, sid):
        """给"替 AI 听歌"用的可公网访问的音频地址；本地文件返回 None（会改用 base64 上传）。"""
        return None

    def audio_format(self, sid):
        """音频格式名（mp3/flac/wav/m4a…），给 Listener 用。"""
        a = self.audio(sid)
        if not a:
            return "mp3"
        p = a[1].split("?")[0]
        return p.rsplit(".", 1)[-1].lower() if "." in p[-6:] else "mp3"


def load_source(cfg):
    return load_class(cfg["source"].get("kind", "local"), BUILTIN)(cfg)
