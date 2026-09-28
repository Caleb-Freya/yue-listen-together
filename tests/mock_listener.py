"""自测用的假"听歌"插件：不联网，直接编三段。也是"怎么写一个 Listener 插件"的最小例子。"""
from yue.listeners import Listener


class MockListener(Listener):
    def listen(self, song, audio):
        assert audio.get("path") or audio.get("url"), "得给我音频"
        return {"segs": [{"start": 0, "part": "前奏", "hear": "一个很干净的单音铺开"},
                         {"start": 6, "part": "主歌", "hear": "同一个音持续，像在等什么"},
                         {"start": 12, "part": "尾奏", "hear": "音渐弱，收在一个安静的点上"}],
                "whole": "一首极简的长音练习", "mood": "安静"}
