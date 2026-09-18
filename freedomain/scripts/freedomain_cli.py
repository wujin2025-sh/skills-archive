#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
DigitalPlat FreeDomain / Domain-OSS CLI Client
用于通过 REST API 管理 FreeDomain / Domain-OSS 域名、DNS解析、ACME 证书挑战，并支持一键启动/停止/重启本地服务。
"""

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
import urllib.request
import urllib.error

CONFIG_DIR = Path.home() / ".config" / "freedomain"
CONFIG_FILE = CONFIG_DIR / "config.json"
PID_FILE = CONFIG_DIR / "freedomain.pid"
LOG_FILE = CONFIG_DIR / "freedomain.log"
DEFAULT_BASE_URL = "http://127.0.0.1:8080/api/v1"
DEFAULT_DOMAIN_OSS_PATH = Path("/Volumes/Macintosh HD_Data/Project/personal-cockpit/Domain-OSS")


def load_config() -> Dict[str, str]:
    config = {
        "base_url": os.getenv("FREEDOMAIN_BASE_URL", DEFAULT_BASE_URL).rstrip("/"),
        "api_key": os.getenv("FREEDOMAIN_API_KEY", ""),
        "app_dir": os.getenv("FREEDOMAIN_APP_DIR", str(DEFAULT_DOMAIN_OSS_PATH)),
    }
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
                if saved.get("base_url"):
                    config["base_url"] = saved["base_url"].rstrip("/")
                if saved.get("api_key"):
                    config["api_key"] = saved["api_key"]
                if saved.get("app_dir"):
                    config["app_dir"] = saved["app_dir"]
        except Exception:
            pass
    return config


def save_config(base_url: Optional[str] = None, api_key: Optional[str] = None, app_dir: Optional[str] = None) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    current = load_config()
    if base_url:
        current["base_url"] = base_url.rstrip("/")
    if api_key is not None:
        current["api_key"] = api_key
    if app_dir:
        current["app_dir"] = app_dir
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(current, f, indent=2, ensure_ascii=False)
    print(f"✅ 配置已保存到: {CONFIG_FILE}")


def make_request(method: str, path: str, data: Optional[Dict[str, Any]] = None, config: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    cfg = config or load_config()
    base_url = cfg["base_url"]
    api_key = cfg["api_key"]

    url = f"{base_url}{path}" if path.startswith("/") else f"{base_url}/{path}"
    headers = {
        "User-Agent": "FreeDomain-Agent-CLI/1.0",
        "Accept": "application/json",
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    body_bytes = None
    if data is not None:
        headers["Content-Type"] = "application/json"
        body_bytes = json.dumps(data).encode("utf-8")

    req = urllib.request.Request(url, data=body_bytes, headers=headers, method=method.upper())

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            if resp.status == 204:
                return {"status": 204, "message": "Success (No Content)"}
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw_err = e.read().decode("utf-8")
        try:
            err_json = json.loads(raw_err)
            msg = err_json.get("error", {}).get("message") or err_json.get("message") or raw_err
        except Exception:
            msg = raw_err or str(e)
        print(f"❌ 请求失败 [HTTP {e.code}]: {msg}", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"❌ 无法连接到服务 ({url}): {e.reason}", file=sys.stderr)
        print("💡 请确认本地 Domain-OSS 服务是否已启动 (freedomain service start) 或检查 base_url 配置。", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"❌ 发生异常: {e}", file=sys.stderr)
        sys.exit(1)


# --- Service Management (Start/Stop/Restart/Status) ---

def find_running_gunicorn_pids() -> List[int]:
    pids = []
    try:
        output = subprocess.check_output(["pgrep", "-f", "domain_oss:create_app()"], text=True)
        for line in output.strip().splitlines():
            if line.strip().isdigit():
                pids.append(int(line.strip()))
    except Exception:
        pass
    return pids


def is_service_alive(base_url: str) -> bool:
    try:
        check_url = f"{base_url}/openapi.json"
        req = urllib.request.Request(check_url, headers={"User-Agent": "FreeDomain-HealthCheck"})
        with urllib.request.urlopen(req, timeout=2) as resp:
            return resp.status in (200, 401, 403)
    except Exception:
        return False


def cmd_service_start(args):
    cfg = load_config()
    app_dir = Path(cfg["app_dir"])
    panel_script = app_dir / "panel"
    host = args.host
    port = args.port

    if not panel_script.exists():
        print(f"❌ 找不到 Domain-OSS panel 启动脚本: {panel_script}", file=sys.stderr)
        sys.exit(1)

    pids = find_running_gunicorn_pids()
    if pids and is_service_alive(f"http://{host}:{port}/api/v1"):
        print(f"ℹ️ FreeDomain (Domain-OSS) 服务已在运行中 (PID: {pids[0]}, http://{host}:{port})。")
        return

    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["HOST"] = host
    env["PORT"] = str(port)

    print(f"🚀 正在启动 FreeDomain 服务 (http://{host}:{port}) ...")
    with open(LOG_FILE, "a", encoding="utf-8") as log_f:
        proc = subprocess.Popen(
            [str(panel_script), "start"],
            cwd=str(app_dir),
            env=env,
            stdout=log_f,
            stderr=log_f,
            start_new_session=True
        )

    PID_FILE.write_text(str(proc.pid), encoding="utf-8")

    # Wait for service readiness
    ready = False
    for _ in range(10):
        time.sleep(0.5)
        if is_service_alive(f"http://{host}:{port}/api/v1"):
            ready = True
            break

    if ready:
        print(f"✅ FreeDomain 服务启动成功！")
        print(f"  • 主进程 PID  : {proc.pid}")
        print(f"  • 服务地址    : http://{host}:{port}/")
        print(f"  • 个人驾驶舱  : http://{host}:{port}/cockpit")
        print(f"  • 日志文件    : {LOG_FILE}")
    else:
        print(f"⚠️ 服务已派发后台 (PID: {proc.pid})，请检查日志确认: {LOG_FILE}")


def cmd_service_stop(args):
    pids = find_running_gunicorn_pids()
    if PID_FILE.exists():
        try:
            stored_pid = int(PID_FILE.read_text().strip())
            if stored_pid not in pids:
                pids.append(stored_pid)
        except Exception:
            pass

    if not pids:
        print("ℹ️ 未检测到正在运行的 FreeDomain (Domain-OSS) 服务进程。")
        if PID_FILE.exists():
            PID_FILE.unlink(missing_ok=True)
        return

    print(f"🛑 正在停止 FreeDomain 服务 (PID: {', '.join(map(str, pids))}) ...")
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        except Exception as e:
            print(f"  停止 PID {pid} 失败: {e}")

    time.sleep(1)
    # Double check if any PID is still alive
    remaining = find_running_gunicorn_pids()
    if remaining:
        print("⚠️ 正在强制终止残留子进程 ...")
        for pid in remaining:
            try:
                os.kill(pid, signal.SIGKILL)
            except Exception:
                pass

    if PID_FILE.exists():
        PID_FILE.unlink(missing_ok=True)

    print("✅ FreeDomain (Domain-OSS) 服务已成功停止。")


def cmd_service_restart(args):
    print("🔄 正在重启 FreeDomain 服务 ...")
    cmd_service_stop(args)
    time.sleep(1)
    cmd_service_start(args)


def cmd_service_status(args):
    cfg = load_config()
    pids = find_running_gunicorn_pids()
    alive = is_service_alive(cfg["base_url"])

    print("\n📊 FreeDomain (Domain-OSS) 服务运行状态:")
    print("-" * 60)
    print(f"  • API 基础地址 : {cfg['base_url']}")
    print(f"  • 状态         : {'🟢 运行中 (ONLINE)' if alive else '🔴 已停止 (OFFLINE)'}")
    print(f"  • 活动进程 PID : {', '.join(map(str, pids)) if pids else '无'}")
    print(f"  • 驾驶舱访问   : {cfg['base_url'].replace('/api/v1', '')}/cockpit")
    print(f"  • 日志文件     : {LOG_FILE}")
    print("-" * 60)
    print()


# --- CLI Commands ---

def cmd_config(args):
    if args.action == "set":
        save_config(args.url, args.key, args.app_dir)
    elif args.action == "show":
        cfg = load_config()
        key_display = (cfg['api_key'][:8] + "..." + cfg['api_key'][-4:]) if len(cfg['api_key']) > 12 else (cfg['api_key'] or "(未设置)")
        print("🔧 当前 FreeDomain CLI 配置:")
        print(f"  • API 基础地址 (Base URL) : {cfg['base_url']}")
        print(f"  • API Key (Bearer Token)  : {key_display}")
        print(f"  • 应用目录 (App Dir)      : {cfg['app_dir']}")
        print(f"  • 配置文件路径            : {CONFIG_FILE}")


def cmd_status(args):
    cfg = load_config()
    print(f"🔍 检查服务状态: {cfg['base_url']} ...")
    res = make_request("GET", "/openapi.json", config=cfg)
    title = res.get("info", {}).get("title", "DigitalPlat Domain OSS API")
    version = res.get("info", {}).get("version", "1.0.0")
    print(f"✅ 服务在线: {title} (v{version})")
    print("   已就绪，可进行域名与 DNS 自动化管理。")


def cmd_domains_list(args):
    path = "/domains?all=1" if args.all else "/domains"
    res = make_request("GET", path)
    data = res.get("data", [])
    if not data:
        print("📭 当前名下暂无域名。")
        return

    print(f"\n📋 域名列表 (共 {len(data)} 个):")
    print(f"{'ID':<6} {'完整域名 (FQDN)':<30} {'前缀 Label':<16} {'所属 Zone':<16} {'状态':<10}")
    print("-" * 80)
    for d in data:
        print(f"{d.get('id', ''):<6} {d.get('name', ''):<30} {d.get('label', ''):<16} {d.get('zone', ''):<16} {d.get('status', ''):<10}")
    print()


def cmd_domains_get(args):
    res = make_request("GET", f"/domains/{args.domain_id}")
    d = res.get("data", {})
    print(f"\n🔎 域名详情 [ID: {d.get('id')}]:")
    print(f"  • 完整域名: {d.get('name')}")
    print(f"  • 前缀名  : {d.get('label')}")
    print(f"  • 托管Zone: {d.get('zone')}")
    print(f"  • 状态    : {d.get('status')}")
    print(f"  • 创建时间: {d.get('created_at')}")


def cmd_domains_create(args):
    payload = {
        "label": args.label.strip().lower(),
        "zone_id": args.zone_id,
    }
    print(f"🚀 正在申请创建域名: {payload['label']} (Zone ID: {payload['zone_id']}) ...")
    res = make_request("POST", "/domains", data=payload)
    d = res.get("data", {})
    print(f"🎉 域名创建成功！")
    print(f"  • 域名: {d.get('name')} [ID: {d.get('id')}]")
    print(f"  • 状态: {d.get('status')}")


def cmd_domains_delete(args):
    print(f"⚠️ 正在删除域名 ID: {args.domain_id} ...")
    make_request("DELETE", f"/domains/{args.domain_id}")
    print(f"🗑️ 域名 [ID: {args.domain_id}] 已成功删除，相关 DNS 记录已清空。")


def cmd_records_list(args):
    res = make_request("GET", f"/domains/{args.domain_id}/records")
    records = res.get("data", [])
    if not records:
        print(f"📭 域名 [ID: {args.domain_id}] 下暂无解析记录。")
        return

    print(f"\n🌐 DNS 解析记录列表 (域名 ID: {args.domain_id} | 共 {len(records)} 条):")
    print(f"{'记录ID':<8} {'主机记录 (Name)':<20} {'类型':<8} {'记录值 (Content)':<32} {'TTL':<8} {'优先级':<8}")
    print("-" * 90)
    for r in records:
        prio = str(r.get('priority') or '-')
        print(f"{r.get('id', ''):<8} {r.get('name', ''):<20} {r.get('type', ''):<8} {r.get('content', ''):<32} {r.get('ttl', ''):<8} {prio:<8}")
    print()


def cmd_records_add(args):
    payload = {
        "name": args.name,
        "type": args.type.upper(),
        "content": args.content,
        "ttl": args.ttl,
    }
    if args.priority is not None:
        payload["priority"] = args.priority

    print(f"🚀 正在添加 DNS 记录: {payload['name']} {payload['type']} -> {payload['content']} ...")
    res = make_request("POST", f"/domains/{args.domain_id}/records", data=payload)
    rec = res.get("data", {})
    job_id = res.get("job_id")
    sync_status = res.get("sync_status")
    print(f"✅ DNS 记录已添加！[记录ID: {rec.get('id')}]")
    if job_id:
        print(f"   后台同步 Job ID: {job_id} (状态: {sync_status})")


def cmd_records_update(args):
    payload = {}
    if args.name:
        payload["name"] = args.name
    if args.type:
        payload["type"] = args.type.upper()
    if args.content:
        payload["content"] = args.content
    if args.ttl:
        payload["ttl"] = args.ttl
    if args.priority is not None:
        payload["priority"] = args.priority

    if not payload:
        print("❌ 未提供任何需要更新的字段 (--name, --type, --content, --ttl, --priority)", file=sys.stderr)
        sys.exit(1)

    print(f"🚀 正在更新 DNS 记录 [ID: {args.record_id}] ...")
    res = make_request("PATCH", f"/domains/{args.domain_id}/records/{args.record_id}", data=payload)
    rec = res.get("data", {})
    print(f"✅ DNS 记录更新成功！[记录ID: {rec.get('id')}]")


def cmd_records_delete(args):
    print(f"⚠️ 正在删除 DNS 记录 [ID: {args.record_id}] (域名 ID: {args.domain_id}) ...")
    make_request("DELETE", f"/domains/{args.domain_id}/records/{args.record_id}")
    print(f"🗑️ DNS 记录 [ID: {args.record_id}] 已成功删除并触发同步。")


def cmd_acme_add(args):
    payload = {
        "value": args.value,
        "name": args.name or "_acme-challenge",
    }
    print(f"🚀 正在下发 ACME DNS-01 验证挑战 TXT 记录 ...")
    res = make_request("POST", f"/domains/{args.domain_id}/acme-challenges", data=payload)
    d = res.get("data", {})
    print(f"✅ ACME 验证记录已发布！")
    print(f"  • 记录全名: {d.get('name')}")
    print(f"  • 验证值  : {d.get('value')}")
    print(f"  • 挑战令牌: {d.get('token')}")
    print(f"  • 过期时间: {d.get('expires_at')}")


def cmd_acme_delete(args):
    print(f"⚠️ 正在清理 ACME 挑战 [Token: {args.token}] ...")
    make_request("DELETE", f"/domains/{args.domain_id}/acme-challenges/{args.token}")
    print(f"🗑️ ACME 挑战记录已清除。")


def main():
    parser = argparse.ArgumentParser(
        description="DigitalPlat FreeDomain / Domain-OSS 自动化管理工具",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    subparsers = parser.add_subparsers(dest="command", help="子命令")

    # service (start, stop, restart, status)
    p_srv = subparsers.add_parser("service", help="服务进程生命周期管理 (start, stop, restart, status)")
    srv_sub = p_srv.add_subparsers(dest="srv_action", required=True)

    p_srv_start = srv_sub.add_parser("start", help="启动 FreeDomain 本地服务")
    p_srv_start.add_argument("--host", default="127.0.0.1", help="绑定主机地址 (默认 127.0.0.1)")
    p_srv_start.add_argument("--port", type=int, default=8080, help="绑定端口 (默认 8080)")
    p_srv_start.set_defaults(func=cmd_service_start)

    p_srv_stop = srv_sub.add_parser("stop", help="停止 FreeDomain 本地服务")
    p_srv_stop.set_defaults(func=cmd_service_stop)

    p_srv_restart = srv_sub.add_parser("restart", help="重启 FreeDomain 本地服务")
    p_srv_restart.add_argument("--host", default="127.0.0.1", help="绑定主机地址 (默认 127.0.0.1)")
    p_srv_restart.add_argument("--port", type=int, default=8080, help="绑定端口 (默认 8080)")
    p_srv_restart.set_defaults(func=cmd_service_restart)

    p_srv_stat = srv_sub.add_parser("status", help="查询 FreeDomain 本地服务运行状态")
    p_srv_stat.set_defaults(func=cmd_service_status)

    # config
    p_cfg = subparsers.add_parser("config", help="配置 API URL 与 API Key")
    p_cfg.add_argument("action", choices=["set", "show"], help="操作: set(设置) 或 show(查看)")
    p_cfg.add_argument("--url", help="API 基础地址 (如 http://127.0.0.1:8080/api/v1)")
    p_cfg.add_argument("--key", help="API Bearer Token (dpo_xxxx)")
    p_cfg.add_argument("--app-dir", help="Domain-OSS 本地应用目录路径")
    p_cfg.set_defaults(func=cmd_config)

    # status
    p_stat = subparsers.add_parser("status", help="检查 API 服务连接与健康状态")
    p_stat.set_defaults(func=cmd_status)

    # domains
    p_dom = subparsers.add_parser("domains", help="域名管理 (list, get, create, delete)")
    dom_sub = p_dom.add_subparsers(dest="dom_action", required=True)

    p_dom_list = dom_sub.add_parser("list", help="列出名下所有域名")
    p_dom_list.add_argument("--all", action="store_true", help="管理员模式: 查看全量域名")
    p_dom_list.set_defaults(func=cmd_domains_list)

    p_dom_get = dom_sub.add_parser("get", help="查看单个域名详情")
    p_dom_get.add_argument("domain_id", type=int, help="域名 ID")
    p_dom_get.set_defaults(func=cmd_domains_get)

    p_dom_create = dom_sub.add_parser("create", help="申请注册新二级域名")
    p_dom_create.add_argument("label", help="子域名前缀 (如 myblog)")
    p_dom_create.add_argument("--zone-id", type=int, default=1, help="所属 Managed Zone ID (默认: 1)")
    p_dom_create.set_defaults(func=cmd_domains_create)

    p_dom_del = dom_sub.add_parser("delete", help="删除域名")
    p_dom_del.add_argument("domain_id", type=int, help="域名 ID")
    p_dom_del.set_defaults(func=cmd_domains_delete)

    # records
    p_rec = subparsers.add_parser("records", help="DNS 解析记录管理 (list, add, update, delete)")
    rec_sub = p_rec.add_subparsers(dest="rec_action", required=True)

    p_rec_list = rec_sub.add_parser("list", help="列出域名的所有解析记录")
    p_rec_list.add_argument("domain_id", type=int, help="域名 ID")
    p_rec_list.set_defaults(func=cmd_records_list)

    p_rec_add = rec_sub.add_parser("add", help="添加一条 DNS 解析记录")
    p_rec_add.add_argument("domain_id", type=int, help="域名 ID")
    p_rec_add.add_argument("--type", required=True, choices=["A", "AAAA", "CNAME", "TXT", "MX", "SRV", "CAA", "NS"], help="记录类型")
    p_rec_add.add_argument("--name", default="@", help="主机记录名称 (如 @, www, api, 默认 @)")
    p_rec_add.add_argument("--content", required=True, help="记录值 (如 IP 地址或目标域名)")
    p_rec_add.add_argument("--ttl", type=int, default=300, help="TTL 缓存时间 (秒, 默认 300)")
    p_rec_add.add_argument("--priority", type=int, help="MX/SRV 优先级")
    p_rec_add.set_defaults(func=cmd_records_add)

    p_rec_update = rec_sub.add_parser("update", help="更新一条 DNS 解析记录")
    p_rec_update.add_argument("domain_id", type=int, help="域名 ID")
    p_rec_update.add_argument("record_id", type=int, help="记录 ID")
    p_rec_update.add_argument("--type", choices=["A", "AAAA", "CNAME", "TXT", "MX", "SRV", "CAA", "NS"], help="记录类型")
    p_rec_update.add_argument("--name", help="主机记录名称")
    p_rec_update.add_argument("--content", help="记录值")
    p_rec_update.add_argument("--ttl", type=int, help="TTL 缓存时间 (秒)")
    p_rec_update.add_argument("--priority", type=int, help="优先级")
    p_rec_update.set_defaults(func=cmd_records_update)

    p_rec_del = rec_sub.add_parser("delete", help="删除一条 DNS 解析记录")
    p_rec_del.add_argument("domain_id", type=int, help="域名 ID")
    p_rec_del.add_argument("record_id", type=int, help="记录 ID")
    p_rec_del.set_defaults(func=cmd_records_delete)

    # acme
    p_acme = subparsers.add_parser("acme", help="ACME DNS-01 证书验证挑战管理")
    acme_sub = p_acme.add_subparsers(dest="acme_action", required=True)

    p_acme_add = acme_sub.add_parser("add", help="发布 ACME TXT 验证记录")
    p_acme_add.add_argument("domain_id", type=int, help="域名 ID")
    p_acme_add.add_argument("--value", required=True, help="ACME 挑战验证值")
    p_acme_add.add_argument("--name", default="_acme-challenge", help="记录名称 (默认 _acme-challenge)")
    p_acme_add.set_defaults(func=cmd_acme_add)

    p_acme_del = acme_sub.add_parser("delete", help="清理 ACME 验证记录")
    p_acme_del.add_argument("domain_id", type=int, help="域名 ID")
    p_acme_del.add_argument("token", help="创建时返回的 challenge_token")
    p_acme_del.set_defaults(func=cmd_acme_delete)

    args = parser.parse_args()
    if not hasattr(args, "func"):
        parser.print_help()
        sys.exit(0)

    args.func(args)


if __name__ == "__main__":
    main()
