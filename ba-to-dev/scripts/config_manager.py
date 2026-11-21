#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ba-to-dev 配置管理器（v1 初稿，2026-11-20）

借鉴 universal-requirement-review「配置与 Skill 本体分离 + 升级保留旧字段」：

目的：
  把 ba-to-dev 的可编辑偏好（三域检索源开关 / 默认系统清单 / 模板偏好等）放
  到"外部持久目录"，与 Skill 安装目录（SKILL.md / scripts/）彻底分离。
  升级 Skill 本体不丢配置；升级脚本发现旧 config_version 时自动备份并迁移，
  已存在的字段绝不重问、绝不覆盖。

外部持久目录（与 ba-to-dev 规范一致）：
  ~/.workbuddy/skill-data/ba-to-dev/config.json   （软链 .chat 同步，改一处即生效）

当前 config_version = 1（v1 初稿）。后续若新增字段/改结构，递增 config_version
并在此实现迁移（保留旧字段，仅补新字段默认值）。

命令（普通用户只跑 --init / --status，不需手改 JSON）：
  python3 config_manager.py --init      # 首次创建默认配置（已存在则幂等，不覆盖）
  python3 config_manager.py --status    # 打印当前配置与路径
  python3 config_manager.py --get <key> # 读单个键
  python3 config_manager.py --set <key> <value>  # 写入单个键（值为 JSON 字面量或非 JSON 明文）
  python3 config_manager.py --migrate   # 手动触发版本迁移（通常 --init/--load 时自动做）

退出码：0=成功；1=错误（不可写/损坏则如实说明，不静默改写）。
"""
import json
import os
import sys

BASE = os.path.expanduser("~/.workbuddy/skill-data/ba-to-dev")
PATH = os.path.join(BASE, "config.json")
CURRENT_VERSION = 1

# 默认配置。各键含义见 SKILL.md「🧰 配置与偏好（外部持久化）」
DEFAULTS = {
    "config_version": CURRENT_VERSION,
    "search": {
        "business_rule": True,   # openviking 业务规则域开关
        "code_lookup": True,     # CBM 代码图谱域开关
        "data_verify": True,     # dbq 数据库域开关
    },
    "system_list": "/Volumes/Macintosh HD_Data/WorkBuddy/需求分析/rules-raw/system_list.csv",
    "template": {},
}


def load():
    """读配置。不存在/损坏时返回 (None, error)；正常返回 (dict, None)。"""
    if not os.path.exists(PATH):
        return None, "配置文件不存在，请先运行 --init"
    try:
        with open(PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        return None, f"配置损坏无法解析: {e}（不静默改写，请人工检查 {PATH}）"
    return cfg, None


def save(cfg):
    """原子写回。目录不存在则创建。失败返回错误串。"""
    try:
        os.makedirs(BASE, exist_ok=True)
        tmp = PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        os.replace(tmp, PATH)  # 原子替换，避免写一半损坏
    except OSError as e:
        return f"写入失败: {e}"
    return None


def migrate(cfg):
    """版本迁移：保留旧字段，仅补新字段默认值。返回 (merged_cfg, changed_or_new)。"""
    ver = cfg.get("config_version", 0)
    if ver == CURRENT_VERSION:
        return cfg, False
    # 保留旧配置，补 DEFAULTS 中缺失的键（多级浅合并）
    merged = dict(DEFAULTS)
    for k, v in cfg.items():
        if k in merged and isinstance(v, dict) and isinstance(merged[k], dict):
            merged[k] = {**merged[k], **v}
        else:
            merged[k] = v
    merged["config_version"] = CURRENT_VERSION
    bak = PATH + f".bak_v{ver}" if os.path.exists(PATH) else None
    if bak and not os.path.exists(bak):
        try:
            os.replace(PATH, bak)  # 迁移前备份旧版本
        except OSError:
            pass
    return merged, True


def main():
    args = sys.argv[1:]
    do_init = "--init" in args
    do_status = "--status" in args
    do_get = "--get" in args
    do_set = "--set" in args
    do_migrate = "--migrate" in args

    if do_init:
        cfg, err = load()
        if cfg is not None:
            merged, changed = migrate(cfg)
            if changed:
                e = save(merged)
                if e:
                    print(f"[ERR] {e}", file=sys.stderr); sys.exit(1)
                print(f"配置已迁移到 v{CURRENT_VERSION}（旧字段保留，仅补新字段）")
            else:
                print(f"配置已存在（v{CURRENT_VERSION}），幂等，未改动: {PATH}")
        else:
            e = save(dict(DEFAULTS))
            if e:
                print(f"[ERR] {e}", file=sys.stderr); sys.exit(1)
            print(f"已创建默认配置 v{CURRENT_VERSION}: {PATH}")
        sys.exit(0)

    if do_status:
        cfg, err = load()
        if cfg is None:
            print(f"未初始化: {PATH}\n提示: 运行 --init 创建，或 --init 前已存在则迁移。")
            sys.exit(0)
        print(f"配置路径: {PATH}")
        print(json.dumps(cfg, ensure_ascii=False, indent=2))
        sys.exit(0)

    if do_get:
        idx = args.index("--get")
        key = args[idx + 1] if idx + 1 < len(args) else None
        if not key:
            print("用法: config_manager.py --get <key>", file=sys.stderr); sys.exit(2)
        cfg, err = load()
        if cfg is None:
            print(f"[ERR] {err}", file=sys.stderr); sys.exit(1)
        val = cfg.get(key)
        print(json.dumps(val, ensure_ascii=False) if val is not None else "<null>")
        sys.exit(0)

    if do_set:
        idx = args.index("--set")
        key = args[idx + 1] if idx + 1 < len(args) else None
        raw = args[idx + 2] if idx + 2 < len(args) else None
        if not key or raw is None:
            print("用法: config_manager.py --set <key> <value>", file=sys.stderr); sys.exit(2)
        cfg, err = load()
        if cfg is None:
            cfg = dict(DEFAULTS)  # --set 前未初始化则从默认开始
        try:
            val = json.loads(raw)  # 优先按 JSON 字面量解析（bool/int/嵌套对象）
        except json.JSONDecodeError:
            val = raw  # 非 JSON 则按字符串
        cfg[key] = val
        e = save(cfg)
        if e:
            print(f"[ERR] {e}", file=sys.stderr); sys.exit(1)
        print(f"已写入 {key} = {json.dumps(val, ensure_ascii=False)} 到 {PATH}")
        sys.exit(0)

    if do_migrate:
        cfg, err = load()
        if cfg is None:
            print(f"[ERR] {err}（无需迁移）", file=sys.stderr); sys.exit(1)
        merged, changed = migrate(cfg)
        if changed:
            e = save(merged)
            if e:
                print(f"[ERR] {e}", file=sys.stderr); sys.exit(1)
            print("迁移完成")
        else:
            print("已是最新版本，无需迁移")
        sys.exit(0)

    print(__doc__)
    sys.exit(2)


if __name__ == "__main__":
    main()