"""配置：读 config.json（允许以 // 开头的注释行），和默认值深合并，相对路径按 config 所在目录解析。"""
import copy
import json
import os
import re

DEFAULTS = {
    "host": "127.0.0.1",
    "port": 8807,
    "passcode": "",
    "api_token": "",
    "title": "乐",
    "names": {"ai": "他", "me": "我"},
    "images": {"background": "", "tonearm": "", "idle_cover": "", "avatar_ai": "", "avatar_me": ""},
    "data_dir": "./data",
    "source": {"kind": "local", "dir": "./music"},
    "listener": {
        "kind": "none",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "api_key": "",
        "model": "qwen3-omni-flash",
        "audio": "auto",
        "timeout": 240,
    },
    "companions": [],
    "mcp": {"http": True, "path": "/mcp"},
    "segment_interval": 15,
}


def _merge(base, over):
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def _strip_comments(text):
    return "\n".join(l for l in text.splitlines() if not re.match(r"^\s*//", l))


def find_config(path=None):
    for p in (path, os.environ.get("YUE_CONFIG"), os.path.join(os.getcwd(), "config.json"),
              os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.json")):
        if p and os.path.exists(p):
            return os.path.abspath(p)
    return None


def load(path=None):
    p = find_config(path)
    raw = {}
    if p:
        raw = json.loads(_strip_comments(open(p, encoding="utf-8").read()))
    cfg = _merge(DEFAULTS, {k: v for k, v in raw.items() if not k.startswith("//")})
    base = os.path.dirname(p) if p else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cfg["_dir"] = base
    cfg["_file"] = p

    def ab(x):
        return os.path.normpath(os.path.join(base, os.path.expanduser(x))) if x and not os.path.isabs(os.path.expanduser(x)) else os.path.expanduser(x or "")

    cfg["data_dir"] = ab(cfg["data_dir"])
    for k, v in list(cfg["images"].items()):
        cfg["images"][k] = ab(v) if v else ""
    src = cfg["source"]
    for k in ("dir", "file"):
        if src.get(k):
            src[k] = ab(src[k])
    return cfg
