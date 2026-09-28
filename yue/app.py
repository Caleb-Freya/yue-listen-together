"""核心：把来源、听歌、陪听、账本串起来。REST 和 MCP 都调这里的方法。"""
import os
import threading
import time

from .companions import Bus
from .listeners import load_listener, normalize
from .lyrics import lyric_at, seg_at
from .sources import load_source
from .store import Store


def log(*a):
    print(time.strftime("%F %T"), *a, flush=True)


class App:
    def __init__(self, cfg):
        self.cfg = cfg
        self.store = Store(cfg["data_dir"])
        self.source = load_source(cfg)
        self.listener = load_listener(cfg)
        self.bus = Bus(cfg, log)
        self._songs = {}
        self._desc_busy = set()
        self._push = {"sid": None, "seg": -2, "at": 0, "ended": False}
        self._lock = threading.Lock()
        self.push_off = os.path.join(cfg["data_dir"], "push-off")  # 有这个文件就不往陪听 AI 发事件

    # ---- 歌 ----
    def song(self, sid):
        if sid in self._songs:
            return self._songs[sid]
        s = self.source.song(sid)
        if s:
            s = dict(s)
            s.setdefault("playable", True)
            self._songs[sid] = s
        return s

    def resolve(self, q):
        """id 或关键字 → 歌曲 dict。"""
        s = self.song(q) if q else None
        if s:
            return s
        r = self.source.search(q, 1)
        return self.song(r[0]["id"]) if r else None

    # ---- 替 AI 听 ----
    def desc(self, sid):
        d = self.store.desc(sid)
        if d:
            return d
        if not self.listener.enabled:
            return {"disabled": True}
        if sid not in self._desc_busy:
            self._desc_busy.add(sid)
            threading.Thread(target=self._describe, args=(sid,), daemon=True).start()
        return {"pending": True}

    def _describe(self, sid):
        try:
            s = self.song(sid)
            a = self.source.audio(sid)
            if not (s and a):
                raise RuntimeError("no audio")
            audio = {"url": self.source.public_audio_url(sid), "path": a[1] if a[0] == "file" else None,
                     "format": self.source.audio_format(sid)}
            d = normalize(self.listener.listen(s, audio))
            d.update(id=sid, at=int(time.time()))
            self.store.save_desc(sid, d)
            log("listened", s["name"], len(d["segs"]), "segs", d["mood"])
        except Exception as e:
            log("listen fail", sid, repr(e)[:200])
        finally:
            self._desc_busy.discard(sid)

    def mood(self, sid):
        return self.store.desc(sid).get("mood", "")

    # ---- 进度上报 → 事件 ----
    def report(self, sid, t, playing, ended=False, duration=0):
        s = self.song(sid) or {}
        if duration and s and not s.get("duration"):
            s["duration"] = duration
        t = float(t or 0)
        segs = self.store.desc(sid).get("segs") or []
        now = {"id": sid, "name": s.get("name", ""), "artist": s.get("artist", ""), "t": round(t, 1),
               "duration": s.get("duration", 0), "playing": bool(playing), "line": lyric_at(s.get("lrc"), t),
               "ended": bool(ended), "at": int(time.time()), "heard": segs[:seg_at(segs, t) + 1]}
        self.store.set_now(now)
        try:
            self._maybe_push(now)
        except Exception as e:
            log("push", repr(e)[:200])
        return now

    def _ev(self, type_, now, **kw):
        ev = {"type": type_, "at": int(time.time()), "song": {"id": now.get("id"), "name": now.get("name"), "artist": now.get("artist")},
              "t": now.get("t", 0), "line": now.get("line", ""), "heard": now.get("heard", [])}
        ev.update(kw)
        return ev

    def emit(self, ev):
        if os.path.exists(self.push_off):
            return
        self.bus.emit(ev, self)

    def _maybe_push(self, now):
        if not now["playing"] and not now.get("ended"):
            return
        sid, t = now["id"], now["t"]
        d = self.store.desc(sid)
        segs = d.get("segs") or []
        p = self._push
        with self._lock:
            if sid != p["sid"]:
                p.update(sid=sid, seg=-2, at=time.time(), ended=False)
                self.store.add_history(sid, now["name"], now["artist"])
                self.store.mark_rec_seen(sid=sid)
                self.emit(self._ev("song_start", now))
                return
            if now.get("ended"):
                if not p["ended"]:
                    p["ended"] = True
                    self.emit(self._ev("song_end", now, whole=d.get("whole", ""), mood=d.get("mood", "")))
                return
            i = seg_at(segs, t)
            if i > p["seg"] and i >= 0 and time.time() - p["at"] > float(self.cfg.get("segment_interval", 15)):
                p.update(seg=i, at=time.time())
                self.emit(self._ev("segment", now, seg=segs[i]))

    # ---- 她这边 ----
    def now(self):
        return dict(self.store.now)

    def she_says(self, text):
        text = (text or "").strip()[:1000]
        if not text:
            raise ValueError("empty")
        item = self.store.talk_add("me", text)
        self.emit(self._ev("say", self.store.now, text=text))
        return item

    def add_note(self, sid, t, text, who, line=None):
        s = self.song(sid)
        if not s:
            raise LookupError("song")
        t = float(t or 0)
        line = line or lyric_at(s.get("lrc"), t)
        n = self.store.add_note(sid, s, t, line, who, text)
        if n["who"] == "me":
            self.emit(self._ev("note", dict(self.store.now, id=sid, name=s["name"], artist=s.get("artist", ""), t=t, line=line), text=n["text"]))
        return n

    # ---- AI 那边 ----
    def ai_say(self, text):
        text = (text or "").strip()[:1000]
        if not text:
            raise ValueError("empty")
        return self.store.talk_add("ai", text)

    def ai_note(self, text, sid=None, t=None):
        now = self.store.now
        sid = sid or now.get("id")
        if not sid:
            raise LookupError("nothing playing")
        return self.add_note(sid, now.get("t", 0) if t is None else t, text, "ai")

    def push_song(self, q, msg=""):
        s = self.resolve(q)
        if not s:
            raise LookupError("song")
        return self.store.add_rec(s, msg)
