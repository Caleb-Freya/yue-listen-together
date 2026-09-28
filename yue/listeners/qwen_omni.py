"""阿里云百炼 Qwen-Omni（OpenAI 兼容接口）听歌。音频给公网 URL，或者本地文件转 base64 一起发。
只用标准库；Omni 系列要求流式输出，这里逐行读 SSE 拼起来。"""
import base64
import json
import re
import ssl
import urllib.request

from . import Listener

PROMPT = ("这是《{name}》- {artist}{dur}。请从头到尾认真听，按音乐自然的段落（前奏/主歌/副歌/间奏/桥段/尾奏）切成 5 到 10 段，"
          "每段用一两句中文写你听到的：进来了什么乐器、节奏和力度怎么变、人声的状态、情绪往哪走。不要复述歌词，不要客套。"
          '只输出 JSON：{{"segs":[{{"start":秒数,"part":"段落名","hear":"听到的"}}],"whole":"整首一句话的感觉",'
          '"mood":"从 温暖/忧伤/轻快/安静/激昂 里选最贴的一个"}}')


class QwenOmniListener(Listener):
    def listen(self, song, audio):
        c = self.cfg["listener"]
        if not c.get("api_key"):
            raise RuntimeError("listener.api_key 没填")
        mode = c.get("audio", "auto")
        if audio.get("url") and mode in ("auto", "url"):
            data = audio["url"]
        elif audio.get("path"):
            raw = open(audio["path"], "rb").read()
            if len(raw) > int(c.get("max_bytes", 12 * 1024 * 1024)):
                raise RuntimeError("音频太大，base64 上传超过 listener.max_bytes")
            data = "data:;base64," + base64.b64encode(raw).decode()
        else:
            raise RuntimeError("没有可用的音频")
        dur = f"，全长约 {int(song.get('duration') or 0)} 秒" if song.get("duration") else ""
        body = {"model": c.get("model", "qwen3-omni-flash"), "stream": True, "modalities": ["text"],
                "messages": [{"role": "user", "content": [
                    {"type": "input_audio", "input_audio": {"data": data, "format": audio.get("format", "mp3")}},
                    {"type": "text", "text": PROMPT.format(name=song["name"], artist=song.get("artist", ""), dur=dur)}]}]}
        req = urllib.request.Request(c["base_url"].rstrip("/") + "/chat/completions", data=json.dumps(body).encode(),
                                     headers={"Authorization": "Bearer " + c["api_key"], "Content-Type": "application/json"})
        out = ""
        with urllib.request.urlopen(req, timeout=int(c.get("timeout", 240)), context=ssl.create_default_context()) as r:
            for line in r:
                line = line.decode("utf-8", "replace").strip()
                if line.startswith("data:") and "[DONE]" not in line:
                    try:
                        for ch in json.loads(line[5:]).get("choices", []):
                            out += (ch.get("delta") or {}).get("content") or ""
                    except Exception:
                        pass
        m = re.search(r"\{[\s\S]*\}", out)
        if not m:
            raise RuntimeError("模型没有输出 JSON：" + out[:120])
        return json.loads(m.group(0))
