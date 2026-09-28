"""按 kind 装插件：内置名字，或 "包.模块:类名" 这种点路径（自己写的来源/听歌/陪听插件就这么接）。"""
import importlib


def load_class(kind, builtin):
    if kind in builtin:
        mod, cls = builtin[kind].rsplit(":", 1)
    elif ":" in kind:
        mod, cls = kind.rsplit(":", 1)
    else:
        raise ValueError(f"不认识的 kind：{kind}（内置：{', '.join(builtin)}；或写成 包.模块:类名）")
    return getattr(importlib.import_module(mod), cls)
