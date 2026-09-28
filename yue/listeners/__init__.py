"""替 AI "听歌" 的接口：把整首音频交给一个能听声音的多模态模型，按段落写下听到了什么。

自己写一个：继承 Listener，实现 listen()，config 里 listener.kind 写 "你的包.模块:类名"。
返回格式：
  {"segs": [{"start": 秒, "part": "前奏/主歌/副歌…", "hear": "这段听到了什么"}], "whole": "整首一句话", "mood": "温暖|忧伤|轻快|安静|激昂"}
kind 为 "none" 时不听：AI 只能拿到歌词。
"""
import re

from ..plugins import load_class

BUILTIN = {
    "none": "yue.listeners:NoListener",
    "qwen_omni": "yue.listeners.qwen_omni:QwenOmniListener",
}
MOODS = ("温暖", "忧伤", "轻快", "安静", "激昂")
_MOOD_WORDS = {"忧伤": "忧伤|悲|遗憾|失落|孤独|心碎|惆怅|伤感|思念|哀", "激昂": "激昂|燃|爆发|澎湃|热血|摇滚|史诗|磅礴",
               "轻快": "轻快|欢快|甜|活泼|俏皮|明亮|跳跃|舞", "安静": "安静|平静|空灵|舒缓|克制|淡|静谧|慢",
               "温暖": "温暖|温柔|治愈|暖|深情|浪漫"}


class Listener:
    enabled = True

    def __init__(self, cfg):
        self.cfg = cfg

    def listen(self, song, audio):
        """song: 歌曲 dict；audio: {"url": 公网地址 或 None, "path": 本地文件 或 None, "format": "mp3"}。"""
        raise NotImplementedError


class NoListener(Listener):
    enabled = False

    def listen(self, song, audio):
        return {}


def normalize(d):
    segs = sorted([{"start": float(x.get("start", 0)), "part": str(x.get("part", "")), "hear": str(x.get("hear", ""))}
                   for x in (d or {}).get("segs", []) if x.get("hear")], key=lambda x: x["start"])
    return {"segs": segs, "whole": str((d or {}).get("whole", "")), "mood": mood_of(d)}


def mood_of(d):
    m = (d or {}).get("mood", "")
    if m in MOODS:
        return m
    text = (d or {}).get("whole", "") + " ".join(x.get("hear", "") for x in (d or {}).get("segs", []))
    if not text:
        return ""
    best = max(MOODS, key=lambda k: len(re.findall(_MOOD_WORDS[k], text)))
    return best if re.search(_MOOD_WORDS[best], text) else "温暖"


def load_listener(cfg):
    return load_class(cfg["listener"].get("kind", "none"), BUILTIN)(cfg)
