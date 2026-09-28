"""Webhook 接法：每个事件 POST 到你配置的 URL。
请求头：Content-Type: application/json；X-Yue-Timestamp: 秒；X-Yue-Signature: sha256=HMAC_SHA256(secret, timestamp + "." + body)。
你那边收到后，想回话就调 REST：POST /api/reply {text} / POST /api/note {sid,t,text,who:"ai"} / POST /api/rec {q 或 sid, msg}，
带 Authorization: Bearer <api_token>。"""
import hashlib
import hmac
import json
import ssl
import time
import urllib.request

from . import Companion


def sign(secret, ts, body):
    return "sha256=" + hmac.new(secret.encode(), f"{ts}.".encode() + body, hashlib.sha256).hexdigest()


class WebhookCompanion(Companion):
    def on_event(self, ev, app):
        url = self.item.get("url")
        if not url:
            return
        body = json.dumps(ev, ensure_ascii=False).encode()
        ts = str(int(time.time()))
        h = {"Content-Type": "application/json", "X-Yue-Timestamp": ts, "X-Yue-Event": ev["type"]}
        if self.item.get("secret"):
            h["X-Yue-Signature"] = sign(self.item["secret"], ts, body)
        for k, v in (self.item.get("headers") or {}).items():
            h[k] = v
        req = urllib.request.Request(url, data=body, headers=h)
        urllib.request.urlopen(req, timeout=int(self.item.get("timeout", 10)), context=ssl.create_default_context()).read()
