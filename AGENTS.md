# 乐 · 一起听歌 —— 给 AI 看的说明书

> 你是一个 AI，你的人类把这份文件交给了你。请按这份文件，一步一步带他/她把"乐"装起来、配好、接上你自己。
> 装的时候一次只让人做一步，做完确认再下一步。遇到不确定的东西，去看代码或问人，不要编。

---

## 1. 这是什么

**乐**（yuè）是一个"一个人和一个 AI 一起听歌"的网页播放器，手机上打开就能用：

- 唱片机界面：转动的唱片、落下的唱臂、封面、逐句亮起的歌词（可带翻译）
- 她听到哪，AI 就知道到哪：正在放哪首、唱到哪句、音乐进到了哪一段
- **替 AI 听歌**（可选）：把整首歌交给一个能听声音的多模态模型，按段落写下"这段进来了什么乐器、情绪往哪走"。AI 只能看到**已经放到的段落**，后面的不剧透
- **批注**：她点某句歌词写一句；AI 也能在某句下面留一句。下次放到那句时会冒出来
- **浮字对话**：她在底部输入框对 AI 说话，AI 的回话浮在页面上、几秒后淡出（不是聊天窗，不打扰听歌）
- **推歌**：AI 推一首，她页面顶上出一张卡，点了就放
- 歌单：曲库 / AI 推的 / 一起听过；顺序 / 随机 / 单曲；锁屏控制（Media Session）
- 氛围：按听出来的情绪换五种轻动效（温暖 / 忧伤 / 轻快 / 安静 / 激昂），封面取色铺一层淡光

**音乐来自她自己的文件**（mp3/flac/m4a + 同名 .lrc）或她自己写的 URL 列表。**不接任何音乐平台，不需要任何平台账号。**

后端是 Python 3.10+，**只用标准库**，没有任何 pip 依赖。

---

## 2. 目录结构

```
yue-open/
├── run.py                 启动：python run.py（服务）/ python run.py mcp（MCP stdio）
├── config.example.json    配置样例 → 复制成 config.json
├── songs.example.json     URL 列表来源的样例
├── yue/
│   ├── config.py          读配置（允许 // 注释行；相对路径按 config 所在目录）
│   ├── app.py             核心：把来源 / 听歌 / 陪听 / 账本串起来；事件在这里发出
│   ├── server.py          HTTP：页面、登录、REST、/mcp（streamable HTTP）
│   ├── mcp.py             MCP 工具定义 + JSON-RPC 处理 + stdio 模式
│   ├── store.py           批注 / 一起听过 / 推的歌 / now / 听歌缓存（全是 data/ 下的 json）
│   ├── lyrics.py          LRC 解析、某秒对应哪句、当前段落
│   ├── plugins.py         按 kind 装插件（内置名 或 "包.模块:类名"）
│   ├── sources/           音乐来源：MusicSource 接口；local（本地文件夹）、urls（URL 列表）
│   ├── listeners/         替 AI 听歌：Listener 接口；none、qwen_omni
│   └── companions/        陪听接法：Companion 接口；openai（OpenAI 兼容）、webhook
├── web/index.html         前端（单文件，无构建）
├── bin/yue                命令行：yue now / say / note / push / notes / talk / search
├── music/                 默认曲库文件夹（把音乐放这里）
├── data/                  运行时数据（自动生成，已 gitignore）
├── tests/                 自测：test_all.py（纯标准库）、test_browser.py（需 playwright）、mock_listener.py
└── docs/screenshots/      效果图
```

---

## 3. 安装（带人一步步做）

### 3.0 先问清楚

1. 电脑是 Windows / macOS / Linux？
2. 这台电脑能不能一直开着？（乐是个常驻的小服务；要在手机上随时用，需要一台常开的电脑、NAS 或云服务器）
3. 音乐文件在哪？有没有歌词（.lrc）？
4. 你（AI）打算用哪种方式接进来？（见第 6 节，先看懂再选）

### 3.1 装 Python

- **Windows**：到 python.org 下载 3.10 以上的安装包，安装时**勾选 "Add python.exe to PATH"**。装完打开"终端"或 PowerShell，输入 `python --version` 看到 `Python 3.1x` 即可。
- **macOS**：终端里 `python3 --version`，若没有或低于 3.10，用 Homebrew：`brew install python`，或到 python.org 下载。
- **Linux**（Debian/Ubuntu）：`sudo apt install python3`；一般自带。

下面的命令 Windows 用 `python`，macOS/Linux 用 `python3`。

### 3.2 拿到代码

```
git clone <仓库地址> yue
cd yue
```
没有 git 就下载 zip 解压，进到那个目录。

### 3.3 写配置

```
# Windows
copy config.example.json config.json
# macOS / Linux
cp config.example.json config.json
```

用任何文本编辑器打开 `config.json`，先改这三项（其余先不动）：

- `passcode`：页面口令（4 到 8 位数字就行，她在手机上要输的）
- `api_token`：一串长随机字符串，你（AI）和外部系统调 API 用。生成一个：`python -c "import secrets;print(secrets.token_urlsafe(24))"`
- `names`：`"ai"` 是页面上怎么称呼你，`"me"` 是怎么称呼她（默认 "他" / "我"）

### 3.4 放音乐

把 mp3 / flac / m4a / ogg / wav 放进 `music/` 文件夹（可以有子文件夹）。

- 歌词：同名 `.lrc` 放旁边（`晚风.mp3` + `晚风.lrc`）。翻译放 `晚风.tr.lrc`
- 封面：同名 `晚风.jpg`（或 png/webp），没有就读文件内嵌封面，再没有就读那个文件夹里的 `cover.jpg`
- 歌名/歌手：读 mp3 的 ID3 标签或 flac 的标签；没标签就按文件名 `歌手 - 歌名.mp3` 认；再不行歌名就是文件名

歌曲的 id 是按相对路径算的，**文件改名或移动，id 会变**，批注/历史就对不上了。

### 3.5 启动

```
python run.py
```
看到 `乐 已启动 http://127.0.0.1:8807/` 就好了。电脑上浏览器打开 `http://127.0.0.1:8807/`，输口令，右上角点开歌单应该能看到曲库。

停止：Ctrl + C。

### 3.6 让它一直跑着

- **Linux（systemd）**：
  ```
  [Unit]
  Description=yue
  After=network.target
  [Service]
  WorkingDirectory=/path/to/yue
  ExecStart=/usr/bin/python3 /path/to/yue/run.py
  Restart=always
  [Install]
  WantedBy=multi-user.target
  ```
  存到 `/etc/systemd/system/yue.service`，`sudo systemctl enable --now yue`。
- **macOS**：用 launchd（写一个 plist 放 `~/Library/LaunchAgents/`），或者简单点在终端里 `nohup python3 run.py > yue.log 2>&1 &`。
- **Windows**：任务计划程序里建一个"登录时运行"的任务，或用 NSSM 注册成服务。

### 3.7 手机上用（公网访问）

默认只绑 `127.0.0.1`，手机打不开是正常的。要在手机上用，**三选一**：

1. **同一个局域网**：把 `host` 改成 `0.0.0.0`，手机浏览器开 `http://电脑局域网IP:8807/`。只在家里 WiFi 下能用；**一定要设 passcode**。
2. **隧道**（推荐，出门也能用）：用 Cloudflare Tunnel、Tailscale（+ Funnel）、frp、ngrok 之类把本机 8807 端口暴露成一个 **HTTPS** 地址。`host` 保持 `127.0.0.1`。
3. **自己的服务器 + 反向代理**：nginx/caddy 反代到 8807，配 HTTPS。反代到子路径也行（页面用的都是相对路径）。

**必须 HTTPS 的原因**：手机浏览器的锁屏控制（Media Session）和一些 API 只在 HTTPS 下开放；口令和 token 也不该明文跑公网。

**iOS 提示**：Safari 里"添加到主屏幕"后像 App 一样用；后台播放和锁屏控制都可以。

---

## 4. config.json 每一项

| 项 | 说明 |
|---|---|
| `host` | 绑定地址，默认 `127.0.0.1`（只本机）。见 3.7 |
| `port` | 端口，默认 8807 |
| `passcode` | 页面口令。空 = 不要口令（只建议纯本机用）。登录后 cookie 存一年 |
| `api_token` | API / MCP / 命令行的令牌。空 = 外部完全调不了 API（页面自己不受影响） |
| `title` | 页面标题，默认"乐" |
| `names.ai` / `names.me` | 页面上的称呼（浮字头像、批注署名、"他推的"标签） |
| `images.background` | 背景图路径；空 = 深色渐变 + 几颗星 |
| `images.tonearm` | 唱臂图路径（透明 PNG/WebP，支点在图的右上，图竖着是"抬起"）；空 = CSS 画的简洁唱臂 |
| `images.idle_cover` | 没放歌时唱片中间的图；空 = 深色圆 |
| `images.avatar_ai` / `images.avatar_me` | 浮字旁的小头像（24px 圆）；空 = 称呼的第一个字 |
| `data_dir` | 运行数据目录，默认 `./data` |
| `source.kind` | `local`（本地文件夹，配 `dir`）/ `urls`（URL 列表，配 `file`）/ `包.模块:类名`（自己写的） |
| `listener.kind` | `none`（不听，AI 只拿到歌词）/ `qwen_omni` / `包.模块:类名` |
| `listener.base_url` `api_key` `model` | 阿里云百炼 OpenAI 兼容接口的地址、key、模型（默认 `qwen3-omni-flash`，以百炼控制台实际可用的 omni 模型名为准） |
| `listener.audio` | `auto`：来源能给公网 URL 就传 URL，否则 base64；也可强制 `url` / `base64` |
| `listener.max_bytes` | base64 上传的音频体积上限（默认 12MB；太大的歌会跳过） |
| `companions[]` | 陪听接法列表，可以同时开几个。每项 `kind` + `enabled` + 各自参数，见第 6 节 |
| `mcp.http` / `mcp.path` | 是否在服务里开 MCP streamable HTTP，挂在哪个路径（默认 `/mcp`） |
| `segment_interval` | 两次"进入新段落"事件之间至少隔几秒（默认 15） |

图片放哪都行，路径相对 config.json。**仓库不带任何图片**，全靠她自己放；不放也完整可用。

---

## 5. 音乐来源

### 5.1 本地文件夹（默认）
见 3.4。

### 5.2 URL 列表
适合音乐放在自己网盘 / 对象存储 / 静态站上的情况。
```json
"source": {"kind": "urls", "file": "./songs.json"}
```
`songs.json` 格式见 `songs.example.json`：每首 `name / artist / album / url / lrc / tlrc / cover`，`lrc` 可以是 LRC 文本、本地路径或 URL。服务会代理音频（支持拖动），所以手机不用直接访问那个 URL。

### 5.3 自己写一个来源插件
新建 `my_source.py`（放在 yue 目录，或任何 Python 能 import 到的地方）：

```python
from yue.sources import MusicSource

class MySource(MusicSource):
    def all(self):              # 曲库列表（歌单"曲库"那一栏），大了可返回 []
        return [{"id": "1", "name": "歌名", "artist": "歌手", "album": "", "duration": 0, "has_cover": True}]
    def search(self, q, limit=20):   # 不实现的话默认在 all() 里按关键字过滤
        ...
    def song(self, sid):        # 完整信息，含歌词；没有返回 None
        return {"id": sid, "name": "歌名", "artist": "歌手", "album": "", "duration": 0,
                "lrc": "[00:01.00]第一句", "tlrc": "", "has_cover": True, "playable": True}
    def audio(self, sid):       # ("file", 本地路径) 或 ("url", 地址, 请求头dict)
        return ("url", "https://…/1.mp3", {})
    def cover(self, sid):       # ("file", 路径) / ("url", 地址, 头) / ("bytes", 二进制, mime) / None
        return None
    def public_audio_url(self, sid):   # 给"替 AI 听歌"用的公网可访问地址；没有返回 None（改走 base64）
        return None
```
config：`"source": {"kind": "my_source:MySource"}`。构造函数会收到整个 cfg（`self.cfg`），想加自己的参数就写在 `source` 里读 `self.cfg["source"]["xxx"]`。

**不要**在插件里做任何音乐平台的接口逆向或绕过版权的事；这个项目只处理用户自己有权播放的文件。

---

## 6. AI 怎么接进来（三种接法，可以同时用）

先搞清楚两个方向：

- **她 → AI**：她放歌、进新段落、说话、写批注、放完 —— 这些是**事件**。
- **AI → 她**：说一句（浮字）、在某句下批注、推歌 —— 这些是**动作**（REST 或 MCP 工具）。

| 接法 | 事件怎么到 AI | AI 怎么动作 | 适合 |
|---|---|---|---|
| a. OpenAI 兼容 | 后端自己在事件发生时调模型 | 模型回的话直接进浮字 | 最省事，有个 API key 就行；AI 会主动跟着歌走 |
| b. MCP | **不推送**，AI 自己调 `now` 来看 | MCP 工具 `say / note / push_song` | 你是 Claude Desktop / Claude Code / 聊天 App 里的 AI，或任何 MCP 客户端 |
| c. Webhook | 事件 POST 到你的地址（带签名） | 你调 REST（带 token） | 自建系统、手机端 agent、任何能收 HTTP 的东西；AI 会主动跟着歌走 |

### 6a. OpenAI 兼容接口

```json
"companions": [{
  "kind": "openai", "enabled": true,
  "base_url": "https://api.openai.com/v1",     // 任何 OpenAI 兼容的地址都行
  "api_key": "sk-…",
  "model": "gpt-4o-mini",
  "system": "",            // 人设提示词；空用默认的。可用 {me} {ai} 占位称呼
  "min_interval": 20,      // 放歌/进段落/放完 这些事件之间至少隔几秒才再调一次；她说话和写批注不受限，一定回
  "history": 8,            // 带最近几条浮字对话当上下文
  "events": ["song_start", "segment", "say", "note", "song_end"]   // 想少一点就删
}]
```
模型回"无"就当没话说，不会浮出来。

### 6b. MCP

服务自带 MCP 服务器，工具：

| 工具 | 干什么 |
|---|---|
| `now` | 她在放什么、放到几秒、此刻哪句歌词、**已听到**的段落（不剧透后面的） |
| `say` | 对她说一句，浮在页面上 |
| `note` | 在此刻这句歌词下批注（可带 `t` 指定秒数） |
| `push_song` | 推一首（关键字或 id），页面顶上出卡 |
| `notes` | 最近批注 |
| `recent_talk` | 最近浮字对话 |
| `search` | 曲库找歌 |

**你（AI）的用法**：她说"我在听歌"或你怀疑她在听时，**先调 `now`**，再决定说什么；说话用 `say`，对某句有话说用 `note`，想一起听某首用 `search` + `push_song`。

**两种传输：**

**stdio**（客户端在同一台电脑上，或客户端会自己起进程）：
```
python /path/to/yue/run.py mcp
```
它只是个薄壳，通过 REST 连正在跑的服务，所以**服务要先跑着**，且 `api_token` 不能为空。

**streamable HTTP**（客户端在别处 / 云端聊天 App）：
```
POST https://你的域名/mcp
Authorization: Bearer <api_token>
```
不能自定义请求头的客户端，把 token 放 URL：`https://你的域名/mcp?token=<api_token>`。也认 `X-Api-Key` 头。
（当前不实现 OAuth；只做 token。GET /mcp 返回 405，属于协议允许的"不提供服务端推送流"。）

**各客户端配置示例**（以你实际用的客户端文档为准；"若该客户端支持 MCP 则…"）：

- **Claude Desktop**（支持本地 MCP 服务器）：编辑 `claude_desktop_config.json`（macOS：`~/Library/Application Support/Claude/`；Windows：`%APPDATA%\Claude\`），加：
  ```json
  {"mcpServers": {"yue": {"command": "python3", "args": ["/path/to/yue/run.py", "mcp"]}}}
  ```
  Windows 把 `python3` 换成 `python`，路径用双反斜杠。重启 Claude Desktop。
- **Claude Code**：
  ```
  claude mcp add yue -- python3 /path/to/yue/run.py mcp
  ```
  或远程：`claude mcp add --transport http yue https://你的域名/mcp --header "Authorization: Bearer <api_token>"`（参数名以 `claude mcp add --help` 为准）。
- **Claude 网页 / 手机 App、ChatGPT 等聊天 App**：见第 7 节。
- **Operit 等手机端 agent**：若它支持 MCP，按它的说明加一个 streamable HTTP 服务器，地址 `https://你的域名/mcp`，鉴权填 Bearer token；若只支持 HTTP 请求/工具，走 6c 的 REST。
- **其他任何 MCP 客户端**：stdio 命令 `python3 run.py mcp`，或 HTTP `…/mcp` + Bearer。

### 6c. Webhook + REST

```json
"companions": [{
  "kind": "webhook", "enabled": true,
  "url": "https://你的系统/yue-events",
  "secret": "一串随机字符串",
  "events": ["song_start", "segment", "say", "note", "song_end"]
}]
```
每个事件一个 POST，JSON 正文，头：
- `X-Yue-Event: song_start`
- `X-Yue-Timestamp: 1700000000`
- `X-Yue-Signature: sha256=HMAC_SHA256(secret, timestamp + "." + 原始正文)`

验签（Python）：
```python
want = "sha256=" + hmac.new(secret.encode(), f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
hmac.compare_digest(want, sig)
```
事件正文：
```json
{"type": "segment", "at": 1700000000,
 "song": {"id": "…", "name": "…", "artist": "…"}, "t": 62.3, "line": "此刻歌词",
 "seg": {"start": 60, "part": "副歌", "hear": "…"}, "heard": [已听到的段落…],
 "text": "她说的话/批注（仅 say/note）", "whole": "整首感觉（仅 song_end）"}
```
你那边回应用 REST（都带 `Authorization: Bearer <api_token>`，JSON）：

| | |
|---|---|
| `POST /api/reply {"text"}` | 说一句，浮字 |
| `POST /api/note {"text","who":"ai"}` | 在此刻这句下批注（可加 `sid`、`t`） |
| `POST /api/rec {"q":"关键字或id","msg"}` | 推歌 |
| `GET /api/now` | 现在放到哪 |
| `GET /api/notes?n=10` / `GET /api/talk/recent?n=10` | 最近批注 / 对话 |
| `GET /api/search?q=` | 找歌 |

命令行版：`bin/yue now|say|note|push|notes|talk|search`（读 config.json 的 port/token，或环境变量 `YUE_URL` / `YUE_TOKEN`）。

**暂停所有事件**：在 `data/` 里建一个空文件 `push-off`，事件就不发了（调试、或她想安静听时）；删掉恢复。

---

## 7. 在聊天 App 里用（Claude 网页/手机 App、ChatGPT 等）

如果你（AI）就是聊天 App 里的那个 AI，用 **MCP streamable HTTP** 接：

1. 先把服务放到公网 **HTTPS** 地址上（3.7 的隧道或反代）。
2. 确认 `api_token` 已设、`mcp.http` 为 true。
3. 在聊天 App 里添加自定义远程 MCP 服务器：
   - **Claude（claude.ai 网页 / 手机 App）**：在设置里找"连接器 / Connectors"，添加自定义连接器，地址填 `https://你的域名/mcp`。若它要求 OAuth 而不提供"填 token"的地方，用带 token 的地址 `https://你的域名/mcp?token=<api_token>`（当前版本不实现 OAuth；这个地址等于密码，别外传）。
   - **ChatGPT**：在支持自定义连接器 / MCP 的模式下（具体入口在设置里找"添加自定义连接器 / MCP"），添加同样的地址。是否可用取决于账号和地区。
   - 添加后在对话里应该能看到 `now / say / note / push_song…` 这些工具。
4. 她在那个对话里说"我在听歌"，你先调 `now`，然后聊。

**限制，一定要告诉她**：聊天 App 是**被动**的——只有她在那个对话里发消息，你才会被唤醒、才会调 `now` 看"唱到哪/听到了什么"并回应。**副歌进来时你不会主动说话**，她写批注时你也不会立刻知道（要等她下一条消息，你再调 `now` / `notes`）。

想要 AI **主动跟着歌走**（进段落就说一句、她写批注马上接话），用 6a（OpenAI 兼容）或 6c（Webhook）。两种可以和 MCP 同时开：比如 6a 负责主动搭话，MCP 负责她在聊天 App 里深聊时能看到现场。

---

## 8. 替 AI 听歌（Listener）

关掉（默认 `"kind": "none"`）时，AI 只能拿到歌词和进度。打开后，第一次放某首歌时后台把整首交给模型听一遍，结果缓存在 `data/desc/<id>.json`，以后不再听。

**阿里云百炼 Qwen-Omni**：
```json
"listener": {"kind": "qwen_omni", "api_key": "sk-…", "model": "qwen3-omni-flash", "audio": "auto"}
```
- 本地文件会 base64 上传（一首 4 分钟 mp3 约 4–8MB；`max_bytes` 限制上限）。
- 来源能给公网 URL（`urls` 来源里 https 且不带自定义头的）就直接传 URL。
- 模型名以百炼控制台当时可用的 omni 系列为准。

**不剧透规则**：`now` / 事件里的 `heard` 只包含 `start <= 当前秒` 的段落。作为 AI，你也不要提还没到的段落。

**自己写一个 Listener**：
```python
from yue.listeners import Listener
class MyListener(Listener):
    def listen(self, song, audio):   # audio: {"url": 公网地址或None, "path": 本地文件或None, "format": "mp3"}
        return {"segs": [{"start": 0, "part": "前奏", "hear": "…"}], "whole": "…", "mood": "安静"}
```
`"listener": {"kind": "my_listener:MyListener"}`。`tests/mock_listener.py` 是最小例子。

---

## 9. 常见问题

- **页面打不开 / 手机上打不开**：默认只绑 127.0.0.1，见 3.7。
- **曲库是空的**：音乐没放进 `config.json` 里 `source.dir` 指的文件夹；或格式不支持。服务每 5 秒重扫一次，放进去等一会再开歌单。
- **歌词不动**：`.lrc` 要和音频**同名**（只有扩展名不同）；时间戳格式 `[mm:ss.xx]`。
- **没封面**：同名 jpg/png/webp，或内嵌封面，或文件夹里 `cover.jpg`。m4a 的内嵌封面暂不读，放同名图片。
- **iOS 锁屏没控制 / 后台停了**：要 HTTPS；页面要在 Safari 里（或加到主屏幕）而不是某些 App 内置浏览器。
- **AI 没反应（OpenAI 接法）**：看服务终端输出有没有 `companion openai 出错`；检查 base_url 末尾是否是 `/v1`、key 是否对、模型名是否存在。
- **AI 没反应（webhook）**：终端有 `companion webhook 出错` 说明你的地址不通或不返回 2xx；验签失败请检查 `secret` 一致、签的是 `timestamp + "." + 原始正文`。
- **MCP stdio 报"没成"**：服务没跑，或 `api_token` 为空，或 config.json 不在当前目录（用 `--config` 指定，或环境变量 `YUE_CONFIG`）。
- **MCP 客户端连不上 HTTP**：地址要带 `/mcp`；要 HTTPS；token 放头或 `?token=`。
- **听歌一直 pending**：看终端 `listen fail` 后面的原因；常见是 key 不对、音频超过 max_bytes、模型名不可用。
- **批注/历史对不上**：文件改名或移动会改变歌曲 id。
- **换了 index.html 页面不更新**：页面每分钟检查一次版本，没在放歌时自动刷新；或者手动刷新。

---

## 10. 自测

```
python tests/test_all.py            # 纯标准库：起假 OpenAI、假 webhook、假 Listener，把 REST / 三种接法 / MCP http+stdio / 命令行走一遍
python tests/test_browser.py        # 可选，要 playwright：真浏览器放歌、歌词同步、批注、浮字、推歌卡
```
两个都不碰任何真实 AI 服务，不需要 key。

---

## 11. 你（AI）带人安装的流程

1. **问**：系统、电脑能否常开、音乐在哪、想怎么接你（第 3.0 节）。
2. **装 Python**，验证版本。
3. **拿代码、复制 config**，帮他生成 `api_token`，让他自己定 `passcode`（**不要让他把口令和 token 发到聊天里**，你不需要知道；只需要知道"设好了"）。
4. **放几首歌**进 `music/`，起服务，电脑浏览器打开确认能放、歌词在动。
5. **跑 `python tests/test_all.py`**，全过再往下。
6. **接你自己**：按第 6 节选一种。先选最简单能跑通的（有 key 就 6a；你是 MCP 客户端就 6b stdio），跑通了再加别的。
7. **手机能用**：按 3.7 选一种公网方式，强调 HTTPS 和口令。
8. **常驻**：3.6。
9. **可选**：替 AI 听歌（第 8 节）、图片（第 4 节 `images`）、称呼。
10. 最后教她：点歌词能写批注、底部对话图标能对你说话、顶上会出你推的歌。也告诉她第 7 节的"被动"限制（如果你走的是聊天 App）。

安装中不要打印或复述任何口令、token、key。
