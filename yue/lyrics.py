"""歌词工具：解析 LRC、找某一秒对应的那句、找当前段落。"""
import re

_TS = re.compile(r"\[(\d+):(\d+(?:\.\d+)?)\]")
_META = re.compile(r"^(作词|作曲|编曲|制作人|混音|母带|和声|吉他|贝斯|鼓|录音|监制|出品|OP|SP)\s*[:：]")


def parse_lrc(text):
    """返回 [(秒, 文字)]，按时间排序；去掉制作人员那类信息行。"""
    out = []
    for line in (text or "").splitlines():
        stamps = _TS.findall(line)
        words = _TS.sub("", line).strip()
        if not stamps or not words or _META.match(words):
            continue
        for m, s in stamps:
            out.append((int(m) * 60 + float(s), words))
    out.sort(key=lambda x: x[0])
    return out


def lyric_at(lrc, t):
    line = ""
    for ts, words in parse_lrc(lrc):
        if ts <= t:
            line = words
        else:
            break
    return line


def seg_at(segs, t):
    i = -1
    for k, x in enumerate(segs or []):
        if float(x.get("start", 0)) <= t + 0.5:
            i = k
    return i


def mmss(t):
    t = max(0, int(t or 0))
    return f"{t // 60}:{t % 60:02d}"


def brief(text, n=16):
    """取第一小句，最多 n 个字。"""
    t = re.split(r"[，。；,;！!？?\n]", (text or "").strip())[0]
    return t[:n] + ("…" if len(t) > n else "")
