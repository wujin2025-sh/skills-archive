#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
config.py — gtht-demand-fetch 统一配置入口（平台无关，唯一配置事实源）

加载优先级（高 → 低）：
  1. `GTHT_*` 环境变量
  2. `~/.config/gtht/config.json`（`GTHT_CONFIG_FILE` 可覆盖）——真实配置（含凭据，chmod 600）
  3. 包内 `config.example.json` —— 内建默认（无真实密钥）

运行期状态（session.json / .browser_profile / *.pkl）一律外置到
`~/.local/share/gtht/`（`GTHT_STATE_DIR` 可覆盖），不随包走、不进 git。

用法：
    import config
    cfg = config.load_config()
    api = config.get_api_base()
    attach = config.get_attach_dir()
    creds = config.get_credential("pingcode")
    state = config.get_state_dir()
"""
import json
import os
import re
from pathlib import Path
from urllib.parse import urlparse

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_EXAMPLE = PACKAGE_ROOT / "config.example.json"
DEFAULT_STATE_DIR = Path.home() / ".local" / "share" / "gtht"
DEFAULT_CONFIG_FILE = Path.home() / ".config" / "gtht" / "config.json"
DEFAULT_OCR_ORDER = ["swift", "pytesseract", "paddleocr"]

_internal_cfg = None


# ---------------------------------------------------------------------------
# 路径 / 环境
# ---------------------------------------------------------------------------
def _env(name: str, default: str = None):
    return os.environ.get(name, default)


def get_config_file() -> Path:
    p = _env("GTHT_CONFIG_FILE")
    if p:
        return Path(p).expanduser()
    return DEFAULT_CONFIG_FILE


def get_state_dir() -> Path:
    p = _env("GTHT_STATE_DIR")
    if p:
        return Path(p).expanduser()
    return DEFAULT_STATE_DIR


def ensure_state_dir() -> Path:
    d = get_state_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_state_file(name: str) -> Path:
    """state_dir 下的某个运行期文件，如 session.json / .sheet_rows_cache.pkl"""
    return ensure_state_dir() / name


# ---------------------------------------------------------------------------
# 配置加载与合并
# ---------------------------------------------------------------------------
def _deep_merge(base: dict, override: dict) -> dict:
    out = dict(base or {})
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _apply_env(cfg: dict) -> dict:
    """GTHT_* 环境变量覆盖（仅覆盖已存在的键或明确支持的键）"""
    env_map = [
        ("base_url", "GTHT_BASE_URL"),
        ("login_url", "GTHT_LOGIN_URL"),
        ("api_base", "GTHT_API_BASE"),
        ("ws_base", "GTHT_WS_BASE"),
        ("vault_root", "GTHT_VAULT_ROOT"),
        ("template_dir", "GTHT_TEMPLATE_DIR"),
        ("attach_dir", "GTHT_ATTACH_DIR"),
        ("pingcode_cache_dir", "GTHT_PINGCODE_CACHE_DIR"),
        ("table_id", "GTHT_TABLE_ID"),
        ("sheet_id", "GTHT_SHEET_ID"),
        ("username", "GTHT_USERNAME"),
        ("password", "GTHT_PASSWORD"),
    ]
    for key, en in env_map:
        v = _env(en)
        if v:
            cfg[key] = v

    # pingcode 子配置
    pc = cfg.get("pingcode") or {}
    for key, en in [("login_url", "GTHT_PINGCODE_LOGIN_URL"),
                    ("username", "GTHT_PINGCODE_USERNAME"),
                    ("password", "GTHT_PINGCODE_PASSWORD")]:
        v = _env(en)
        if v:
            pc[key] = v
    if pc:
        cfg["pingcode"] = pc

    # defaults
    defaults = cfg.get("defaults") or {}
    for key, en in [("cur_user_no", "GTHT_CUR_USER_NO"),
                    ("cur_user_name", "GTHT_CUR_USER_NAME"),
                    ("default_assign_user_no", "GTHT_DEFAULT_ASSIGN_USER_NO"),
                    ("default_evaluator_no", "GTHT_DEFAULT_EVALUATOR_NO")]:
        v = _env(en)
        if v:
            defaults[key] = v
    if defaults:
        cfg["defaults"] = defaults

    # OCR 后端顺序（逗号分隔）
    ocr = _env("GTHT_OCR_BACKEND")
    if ocr:
        cfg["ocr_backend_order"] = [x.strip() for x in ocr.split(",") if x.strip()]
    return cfg


def load_config(force: bool = False) -> dict:
    """加载合并后的配置（env > 用户 config.json > 包内 example）。"""
    global _internal_cfg
    if _internal_cfg is not None and not force:
        return _internal_cfg

    cfg: dict = {}
    if DEFAULT_EXAMPLE.exists():
        try:
            cfg = json.loads(DEFAULT_EXAMPLE.read_text(encoding="utf-8"))
        except Exception:
            cfg = {}

    cfile = get_config_file()
    if cfile.exists():
        try:
            user = json.loads(cfile.read_text(encoding="utf-8"))
            cfg = _deep_merge(cfg, user)
        except Exception as e:
            print(f"[config] ⚠️ 用户配置文件解析失败（{cfile}）: {e}", file=__import__("sys").stderr)

    cfg = _apply_env(cfg)
    _internal_cfg = cfg
    return cfg


def reload() -> dict:
    """强制重载配置（测试/热更场景）"""
    return load_config(force=True)


# ---------------------------------------------------------------------------
# 站点 / API 派生
# ---------------------------------------------------------------------------
def get_base_url() -> str:
    cfg = load_config()
    return (cfg.get("base_url") or "").rstrip("/")


def get_login_url() -> str:
    cfg = load_config()
    if cfg.get("login_url"):
        return cfg["login_url"]
    return get_base_url() + "/user/login"


def get_api_base() -> str:
    """API 根：优先显式配置，否则由 base_url 推导（.../kjpt → .../api）。"""
    cfg = load_config()
    if cfg.get("api_base"):
        return cfg["api_base"].rstrip("/")
    base = get_base_url()
    # https://host/kjpt → https://host/api
    return base.rsplit("/", 1)[0] + "/api"


def _netloc() -> str:
    return urlparse(get_api_base()).netloc or ""


def get_ws_base() -> str:
    """WebSocket 根：优先显式配置，否则由 api_base 推导（wss://host）。"""
    cfg = load_config()
    if cfg.get("ws_base"):
        return cfg["ws_base"].rstrip("/")
    return "wss://" + _netloc()


def get_origin() -> str:
    """浏览器 Origin 请求头（https://host）。"""
    return "https://" + _netloc()


def get_pingcode_login_url() -> str:
    return (get_credential("pingcode") or {}).get("login_url") or "https://pingcode.gtht.com.cn/login"


# ---------------------------------------------------------------------------
# 路径类
# ---------------------------------------------------------------------------
def get_vault_root() -> Path:
    cfg = load_config()
    return Path(cfg.get("vault_root") or "~/Documents/vault").expanduser()


def get_attach_dir() -> Path:
    cfg = load_config()
    if cfg.get("attach_dir"):
        return Path(cfg["attach_dir"]).expanduser()
    return get_vault_root() / "附件"


def get_template_dir() -> Path:
    """模板目录：优先 config.template_dir；否则 vault 90-模板；否则包内 references/templates。"""
    cfg = load_config()
    if cfg.get("template_dir"):
        return Path(cfg["template_dir"]).expanduser()
    vault_tpl = get_vault_root() / "90-模板"
    if vault_tpl.exists():
        return vault_tpl
    return PACKAGE_ROOT / "references" / "templates"


def get_pingcode_cache_dir() -> Path:
    cfg = load_config()
    if cfg.get("pingcode_cache_dir"):
        return Path(cfg["pingcode_cache_dir"]).expanduser()
    return get_vault_root() / "50-业务知识" / "wiki-cache"


# ---------------------------------------------------------------------------
# 凭据 / 默认值
# ---------------------------------------------------------------------------
def get_credential(name: str) -> dict:
    """返回某个凭据子配置（如 get_credential("pingcode") → {login_url, username, password}）。"""
    cfg = load_config()
    return cfg.get(name) or {}


def get_platform_credentials() -> dict:
    """科技平台登录凭据（登录表单 #workno/#password）。"""
    cfg = load_config()
    return {"username": cfg.get("username") or "", "password": cfg.get("password") or ""}


def get_default(key: str, fallback: str = "") -> str:
    cfg = load_config()
    defaults = cfg.get("defaults") or {}
    return defaults.get(key, fallback)


def get_table_sheet():
    """返回 (table_id, sheet_id)。"""
    cfg = load_config()
    return cfg.get("table_id") or "", cfg.get("sheet_id") or ""


# ---------------------------------------------------------------------------
# OCR
# ---------------------------------------------------------------------------
def get_ocr_backend_order() -> list:
    cfg = load_config()
    return cfg.get("ocr_backend_order") or DEFAULT_OCR_ORDER


# ---------------------------------------------------------------------------
# 便捷入口（供 __main__ 调试）
# ---------------------------------------------------------------------------
def _summary() -> dict:
    cfg = load_config()
    return {
        "config_file": str(get_config_file()),
        "state_dir": str(get_state_dir()),
        "base_url": get_base_url(),
        "api_base": get_api_base(),
        "ws_base": get_ws_base(),
        "login_url": get_login_url(),
        "vault_root": str(get_vault_root()),
        "attach_dir": str(get_attach_dir()),
        "template_dir": str(get_template_dir()),
        "cache_dir": str(get_pingcode_cache_dir()),
        "table_id": cfg.get("table_id"),
        "sheet_id": cfg.get("sheet_id"),
        "ocr_backend_order": get_ocr_backend_order(),
        "has_platform_credential": bool((cfg.get("username") or "") and (cfg.get("password") or "")),
        "has_pingcode_credential": bool((cfg.get("pingcode") or {}).get("username")),
    }


if __name__ == "__main__":
    import sys
    if "--dump" in sys.argv:
        import json as _json
        print(_json.dumps(load_config(), ensure_ascii=False, indent=2))
    else:
        for k, v in _summary().items():
            print(f"{k}: {v}")
