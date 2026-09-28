"""本地文件夹来源：mp3/flac/m4a/ogg/wav + 同名 .lrc（翻译放同名 .tr.lrc），封面取同名 jpg/png/webp、内嵌图、或该目录的 cover.jpg。
只用标准库，自带一个够用的 ID3v2 / FLAC 标签解析（歌名、歌手、专辑、内嵌封面）。文件名 "歌手 - 歌名.mp3" 也能认。"""
import hashlib
import os
import struct
import time

from . import MusicSource

EXTS = (".mp3", ".flac", ".m4a", ".ogg", ".wav", ".aac", ".opus")
IMG = (".jpg", ".jpeg", ".png", ".webp")


def _id3_text(data):
    if not data:
        return ""
    enc, body = data[0], data[1:]
    try:
        if enc == 0:
            return body.decode("latin-1").strip("\x00").strip()
        if enc == 1:
            return body.decode("utf-16").strip("\x00").strip()
        if enc == 2:
            return body.decode("utf-16-be").strip("\x00").strip()
        return body.decode("utf-8", "replace").strip("\x00").strip()
    except Exception:
        return ""


def _syncsafe(b):
    return (b[0] << 21) | (b[1] << 14) | (b[2] << 7) | b[3]


def read_id3(path, want_pic=False):
    """返回 {title, artist, album, pic:(mime, bytes)}；解析不了就返回 {}。"""
    out = {}
    try:
        with open(path, "rb") as f:
            h = f.read(10)
            if h[:3] != b"ID3":
                return out
            ver, flags, size = h[3], h[5], _syncsafe(h[6:10])
            data = f.read(size)
        pos = 10 if flags & 0x40 and ver == 3 else 0
        if flags & 0x40 and ver == 4:
            pos = _syncsafe(data[:4])
        while pos + 10 <= len(data):
            fid = data[pos:pos + 4]
            if fid == b"\x00\x00\x00\x00":
                break
            fsz = _syncsafe(data[pos + 4:pos + 8]) if ver == 4 else struct.unpack(">I", data[pos + 4:pos + 8])[0]
            body = data[pos + 10:pos + 10 + fsz]
            pos += 10 + fsz
            if fid == b"TIT2":
                out["title"] = _id3_text(body)
            elif fid == b"TPE1":
                out["artist"] = _id3_text(body)
            elif fid == b"TALB":
                out["album"] = _id3_text(body)
            elif fid == b"APIC" and want_pic and "pic" not in out:
                enc = body[0]
                i = body.index(b"\x00", 1)
                mime = body[1:i].decode("latin-1")
                j = i + 2  # 跳过图片类型字节
                if enc in (1, 2):
                    k = body.find(b"\x00\x00", j)
                    while k != -1 and (k - j) % 2:
                        k = body.find(b"\x00\x00", k + 1)
                    j = k + 2
                else:
                    j = body.index(b"\x00", j) + 1
                out["pic"] = (mime or "image/jpeg", body[j:])
    except Exception:
        pass
    return out


def read_flac(path, want_pic=False):
    out = {}
    try:
        with open(path, "rb") as f:
            if f.read(4) != b"fLaC":
                return out
            last = False
            while not last:
                hdr = f.read(4)
                if len(hdr) < 4:
                    break
                last, btype = bool(hdr[0] & 0x80), hdr[0] & 0x7F
                ln = int.from_bytes(hdr[1:4], "big")
                if btype == 4:
                    b = f.read(ln)
                    p = 4 + int.from_bytes(b[:4], "little")
                    n = int.from_bytes(b[p:p + 4], "little")
                    p += 4
                    for _ in range(n):
                        l = int.from_bytes(b[p:p + 4], "little")
                        kv = b[p + 4:p + 4 + l].decode("utf-8", "replace")
                        p += 4 + l
                        k, _, v = kv.partition("=")
                        k = k.upper()
                        if k == "TITLE":
                            out["title"] = v
                        elif k == "ARTIST":
                            out["artist"] = v
                        elif k == "ALBUM":
                            out["album"] = v
                elif btype == 6 and want_pic and "pic" not in out:
                    b = f.read(ln)
                    p = 4
                    ml = int.from_bytes(b[p:p + 4], "big")
                    mime = b[p + 4:p + 4 + ml].decode("latin-1")
                    p += 4 + ml
                    dl = int.from_bytes(b[p:p + 4], "big")
                    p += 4 + dl + 16
                    n = int.from_bytes(b[p:p + 4], "big")
                    out["pic"] = (mime, b[p + 4:p + 4 + n])
                else:
                    f.seek(ln, 1)
    except Exception:
        pass
    return out


def read_tags(path, want_pic=False):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".mp3":
        return read_id3(path, want_pic)
    if ext == ".flac":
        return read_flac(path, want_pic)
    return {}


class LocalFolderSource(MusicSource):
    def __init__(self, cfg):
        super().__init__(cfg)
        self.dir = cfg["source"].get("dir") or os.path.join(cfg["_dir"], "music")
        os.makedirs(self.dir, exist_ok=True)
        self._cache = {}
        self._scan_at = 0
        self._sig = None

    def _signature(self):
        sig = []
        for root, _, files in os.walk(self.dir):
            for fn in files:
                if fn.lower().endswith(EXTS):
                    p = os.path.join(root, fn)
                    try:
                        sig.append((p, os.path.getmtime(p)))
                    except OSError:
                        pass
        return tuple(sorted(sig))

    def _scan(self):
        if time.time() - self._scan_at < 5:
            return
        self._scan_at = time.time()
        sig = self._signature()
        if sig == self._sig:
            return
        self._sig = sig
        cache = {}
        for p, _ in sig:
            rel = os.path.relpath(p, self.dir)
            sid = hashlib.sha1(rel.encode("utf-8")).hexdigest()[:12]
            stem = os.path.splitext(os.path.basename(p))[0]
            tags = read_tags(p)
            name, artist = tags.get("title") or "", tags.get("artist") or ""
            if not name:
                if " - " in stem:
                    artist, name = [x.strip() for x in stem.split(" - ", 1)] if not artist else (artist, stem.split(" - ", 1)[1].strip())
                else:
                    name = stem
            cache[sid] = {"id": sid, "name": name, "artist": artist, "album": tags.get("album") or "",
                          "path": p, "rel": rel, "duration": 0}
        self._cache = cache

    def all(self):
        self._scan()
        return [dict(s, has_cover=self.cover(s["id"]) is not None) for s in sorted(self._cache.values(), key=lambda s: s["rel"].lower())]

    def _sidecar(self, sid, exts):
        s = self._cache.get(sid)
        if not s:
            return None
        base = os.path.splitext(s["path"])[0]
        for e in exts:
            if os.path.exists(base + e):
                return base + e
        return None

    def song(self, sid):
        self._scan()
        s = self._cache.get(sid)
        if not s:
            return None
        lrc = tlrc = ""
        f = self._sidecar(sid, (".lrc", ".LRC"))
        if f:
            lrc = open(f, encoding="utf-8", errors="replace").read()
        f = self._sidecar(sid, (".tr.lrc", ".tlrc"))
        if f:
            tlrc = open(f, encoding="utf-8", errors="replace").read()
        return dict(s, lrc=lrc, tlrc=tlrc, has_cover=self.cover(sid) is not None, playable=True)

    def audio(self, sid):
        self._scan()
        s = self._cache.get(sid)
        return ("file", s["path"]) if s else None

    def cover(self, sid):
        s = self._cache.get(sid)
        if not s:
            return None
        f = self._sidecar(sid, IMG)
        if f:
            return ("file", f)
        pic = read_tags(s["path"], want_pic=True).get("pic")
        if pic and pic[1]:
            return ("bytes", pic[1], pic[0])
        d = os.path.dirname(s["path"])
        for fn in ("cover.jpg", "cover.png", "folder.jpg", "Cover.jpg"):
            if os.path.exists(os.path.join(d, fn)):
                return ("file", os.path.join(d, fn))
        return None
