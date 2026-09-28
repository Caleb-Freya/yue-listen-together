#!/usr/bin/env python3
"""启动：
  python run.py                 开服务（读同目录 config.json，或 --config 路径 / 环境变量 YUE_CONFIG）
  python run.py mcp             作为 MCP stdio 服务器（给 Claude Desktop / Claude Code 等客户端用；服务要先跑着）
"""
import sys

from yue import config


def main():
    args = sys.argv[1:]
    path = None
    if "--config" in args:
        i = args.index("--config")
        path = args[i + 1]
        del args[i:i + 2]
    cfg = config.load(path)
    if args and args[0] == "mcp":
        from yue.mcp import stdio_main
        stdio_main(cfg)
    else:
        from yue.server import serve
        serve(cfg)


if __name__ == "__main__":
    main()
