"""落盘的小账本：批注 / 一起听过 / 推的歌 / 现在放到哪 / 听歌描述缓存 / 浮字对话（内存）。全是 json 文件，够用就好。"""
import json
import os
import threading
import time


class Store:
    def __init__(self, data_dir):
        self.dir = data_dir
        self.desc_dir = os.path.join(data_dir, "desc")
        os.makedirs(self.desc_dir, exist_ok=True)
        self.lock = threading.RLock()
        self.talk = []  # [{id, who: ai|me, text, at}] 只在内存里，重启就清
        self.now = {}
        try:
            self.now = json.load(open(os.path.join(data_dir, "now.json"), encoding="utf-8"))
        except Exception:
            pass

    # ---- 通用 ----
    def _path(self, name):
        return os.path.join(self.dir, name + ".json")

    def load(self, name, default):
        try:
            return json.load(open(self._path(name), encoding="utf-8"))
        except Exception:
            return default

    def save(self, name, value):
        p = self._path(name)
        with open(p + ".tmp", "w", encoding="utf-8") as f:
            json.dump(value, f, ensure_ascii=False)
        os.replace(p + ".tmp", p)

    # ---- 现在放到哪 ----
    def set_now(self, now):
        with self.lock:
            self.now = now
            self.save("now", now)

    # ---- 批注 ----
    def notes(self, sid=None, n=None):
        a = self.load("notes", [])
        if sid is not None:
            a = [x for x in a if x["sid"] == sid]
        return a[-n:] if n else a

    def add_note(self, sid, song, t, line, who, text):
        with self.lock:
            a = self.load("notes", [])
            n = {"id": int(time.time() * 1000), "sid": sid, "song": song.get("name", ""),
                 "artist": song.get("artist", ""), "t": round(float(t), 2), "line": line,
                 "who": "ai" if who == "ai" else "me", "text": text.strip()[:500], "ts": int(time.time())}
            a.append(n)
            self.save("notes", a[-5000:])
            return n

    def del_note(self, nid):
        with self.lock:
            self.save("notes", [x for x in self.load("notes", []) if x["id"] != nid])

    # ---- 一起听过 ----
    def add_history(self, sid, name, artist):
        with self.lock:
            h = self.load("history", [])
            if h and h[-1]["sid"] == sid and time.time() - h[-1]["at"] < 1800:
                return
            h.append({"sid": sid, "name": name, "artist": artist, "at": int(time.time())})
            self.save("history", h[-2000:])

    def history(self):
        cnt = {}
        for n in self.notes():
            cnt[n["sid"]] = cnt.get(n["sid"], 0) + 1
        seen, out = set(), []
        for x in self.load("history", [])[::-1]:
            if x["sid"] in seen:
                continue
            seen.add(x["sid"])
            out.append(dict(x, id=x["sid"], notes=cnt.get(x["sid"], 0)))
        return out[:200]

    # ---- 推的歌 ----
    def add_rec(self, song, msg):
        with self.lock:
            r = self.load("recs", [])
            rec = {"id": int(time.time() * 1000), "sid": song["id"], "name": song["name"], "artist": song.get("artist", ""),
                   "msg": (msg or "")[:200], "at": int(time.time()), "seen": False}
            r.append(rec)
            self.save("recs", r[-500:])
            return rec

    def recs(self):
        return [dict(x, id=x["sid"], rid=x["id"]) for x in self.load("recs", [])[::-1][:100]]

    def mark_rec_seen(self, sid=None, rid=None):
        with self.lock:
            r = self.load("recs", [])
            for x in r:
                if (sid is not None and x["sid"] == sid) or (rid is not None and x["id"] == rid):
                    x["seen"] = True
            self.save("recs", r)

    # ---- 听歌描述缓存 ----
    def desc(self, sid):
        try:
            return json.load(open(os.path.join(self.desc_dir, f"{sid}.json"), encoding="utf-8"))
        except Exception:
            return {}

    def save_desc(self, sid, d):
        with open(os.path.join(self.desc_dir, f"{sid}.json"), "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False)

    # ---- 浮字对话 ----
    def talk_add(self, who, text, eid=None):
        with self.lock:
            item = {"id": eid or f"{who}-{time.time():.3f}", "who": who, "text": text, "at": time.time()}
            self.talk.append(item)
            del self.talk[:-80]
            return item

    def talk_since(self, since):
        with self.lock:
            return [x for x in self.talk if x["at"] > since]

    def talk_recent(self, n=10):
        with self.lock:
            return self.talk[-n:]
