#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
upload_to_tencent.py — 将本地 HTML 文件上传到腾讯文档指定文件夹（同名覆盖 / 不同名新增）
=============================================================================================
功能：
  1. 使用腾讯文档 aipage 通路将本地 HTML 打包为 .aipage 并导入为在线文档；
  2. 支持将导入后的在线文档放进指定文件夹（folder_id）；
  3. 「同名覆盖」：若目标文件夹已存在同名文档，先删除旧文档再放入新文档；
  4. 「不同名新增」：目标文件夹不存在同名文档时，直接放入新文档。

依赖：
  - 受管 Node（mcporter + aipage_pack.js 需要，避免系统 PATH 中的 connector-runtime 崩溃）
  - mcporter（已配置 tencent-docs 服务）
  - 腾讯文档 MCP 走代理（系统代理 172.16.0.11:3128）

作为独立命令行工具：
  python3 upload_to_tencent.py <html_path> --folder "TNLKgDkNdIvP" [--title <title>] [--dry-run]

被 proposed_schedule_confirm.py 调用：在上传 HTML 时自动启用。
"""

import os
import sys
import re
import json
import tempfile
import argparse
import subprocess
import hashlib
import time

# ── 环境常量 ──────────────────────────────────────────────────────────────────
# 受管 Node 绝对路径（避免系统 PATH 中空/损坏的 node 导致 V8 崩溃）
MANAGED_NODE = "/Users/wujin/.chat/runtimes/darwin-x64/node/versions/22.22.2/bin/node"
# mcporter 可执行入口（受管 Node 可直接运行其 dist/cli.js）
MCPORTER_CLI = "/Users/wujin/.npm-global/lib/node_modules/mcporter/dist/cli.js"
# tencent-docs skill 目录（aipage_pack.js / import_file.sh）
TENCENT_DOCS_DIR = "/Users/wujin/.claude/skills/tencent-docs"
AIPAGE_PACK_JS = os.path.join(TENCENT_DOCS_DIR, "aipage_pack.js")
IMPORT_FILE_SH = os.path.join(TENCENT_DOCS_DIR, "import_file.sh")

# 系统 HTTP/HTTPS 代理（通过 scutil 获取；腾讯文档 MCP 需走代理才能连通)
PROXY = "http://172.16.0.11:3128"
NO_PROXY = "localhost,127.0.0.1,.gtht.com.cn,.gtja.net"

# mcporter 默认读取 ~/.mcporter/mcporter.json 中的 tencent-docs 配置（含 Authorization）


def _env_with_proxy():
    """构造 subprocess 环境变量：显式受管 Node + 完整代理（大小写都要，供 undici EnvHttpProxyAgent 读取）。"""
    env = dict(os.environ)
    env["PATH"] = os.path.dirname(MANAGED_NODE) + ":" + env.get("PATH", "")
    env["NODE_USE_ENV_PROXY"] = "1"
    env["https_proxy"] = PROXY
    env["http_proxy"] = PROXY
    env["HTTPS_PROXY"] = PROXY
    env["HTTP_PROXY"] = PROXY
    env["ALL_PROXY"] = PROXY
    env["all_proxy"] = PROXY
    env["no_proxy"] = NO_PROXY
    env["NO_PROXY"] = NO_PROXY
    return env


def _run(args, timeout=120, env=None):
    """执行命令并返回合并输出；非零退出码抛 RuntimeError。"""
    env = env or _env_with_proxy()
    proc = subprocess.run(args, capture_output=True, text=True, env=env, timeout=timeout)
    output = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode != 0:
        raise RuntimeError(f"命令失败 ({proc.returncode}): {' '.join(args)}\n{output}")
    return output


def _clean_output(text):
    """去掉 undici EnvHttpProxyAgent 的 warning 行与空行。"""
    lines = []
    for line in text.splitlines():
        if "EnvHttpProxyAgent is experimental" in line:
            continue
        if "trace-warnings" in line:
            continue
        if line.startswith("(node:") and "Warning:" in line:
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def _mcp_call(tool, args_dict, timeout=120):
    """调用 mcporter call tencent-docs <tool> --args <json>，返回解析后的 dict。"""
    args_json = json.dumps(args_dict, ensure_ascii=False)
    out = _run([MANAGED_NODE, MCPORTER_CLI, "call", "tencent-docs", tool, "--args", args_json],
               timeout=timeout)
    cleaned = _clean_output(out)
    # mcporter call 输出通常是 JSON；去掉前后非 JSON 噪音
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        # 找到第一个 { 和最后一个 } 截取
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(cleaned[start:end + 1])
            except json.JSONDecodeError:
                pass
        raise RuntimeError(f"mcporter 返回无法解析: {cleaned}")


# ── Step 1-4：aipage 打包 + 导入 ─────────────────────────────────────────────

def pack_html(html_path, title=None, out_dir=None):
    """用 aipage_pack.js 将 HTML 打包为 .aipage，返回 (aipage_path, size, md5, title)。"""
    if not os.path.isfile(html_path):
        raise FileNotFoundError(f"HTML 文件不存在: {html_path}")

    stem = os.path.splitext(os.path.basename(html_path))[0]
    args = [MANAGED_NODE, AIPAGE_PACK_JS, "--html", html_path]
    if title:
        args += ["--title", title]
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
        args += ["--output", os.path.join(out_dir, stem + ".aipage")]

    out = _run(args)
    # 解析 KEY=VALUE 输出
    parsed = {}
    for line in out.splitlines():
        m = re.match(r"^([A-Z_]+)=(.*)$", line.strip())
        if m:
            parsed[m.group(1)] = m.group(2).strip()

    aipage_path = parsed.get("AIPAGE_PATH")
    if not aipage_path or not os.path.isfile(aipage_path):
        raise RuntimeError(f"aipage 打包失败，输出: {out}")

    aipage_size = int(parsed.get("AIPAGE_SIZE", os.path.getsize(aipage_path)))
    aipage_md5 = parsed.get("AIPAGE_MD5") or _md5(aipage_path)
    aipage_title = parsed.get("AIPAGE_TITLE") or title or stem
    return aipage_path, aipage_size, aipage_md5, aipage_title


def _md5(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def pre_import_and_upload(aipage_path, aipage_size, aipage_md5, aipage_title):
    """pre_import 获取 COS 上传链接 → PUT 上传，返回 (task_id, file_key, file_name)。"""
    # 用干净标题作为 aipage 文件名（在线文档名=其去扩展名后的 basename），
    # 去掉净化文件名带上的 __tencent_sanitized 后缀。
    base = os.path.basename(aipage_path)
    base = base.replace("__tencent_sanitized", "").replace("_tencent_sanitized", "")
    if not base.lower().endswith(".aipage"):
        base += ".aipage"
    file_name = base
    prep = _mcp_call("manage.pre_import", {
        "file_name": file_name,
        "file_size": aipage_size,
        "file_md5": aipage_md5,
    })
    upload_url = prep.get("upload_url") or prep.get("url")
    file_key = prep.get("file_key") or prep.get("key")
    task_id = prep.get("task_id")
    if not (upload_url and file_key and task_id):
        raise RuntimeError(f"pre_import 缺少 upload_url/file_key/task_id: {prep}")

    # PUT 上传到 COS（不走 MCP，直接 curl）
    env = _env_with_proxy()
    proc = subprocess.run(
        ["curl", "-sS", "-X", "PUT", "-H", "Content-Type: application/octet-stream",
         "--data-binary", "@" + aipage_path, upload_url],
        capture_output=True, text=True, env=env, timeout=180)
    if proc.returncode != 0 or (proc.stdout and not proc.stdout.startswith("{")):
        # HTTP 2xx 视为成功；curl 失败会有非零退出码
        if proc.returncode != 0:
            raise RuntimeError(f"COS 上传失败: {proc.stderr or proc.stdout}")
    return task_id, file_key, file_name


def async_import(task_id, file_key, file_name, md5, size, poll=60, interval=5):
    """触发 async_import 并轮询 import_progress，返回 (file_id, file_url, file_name)。"""
    _mcp_call("manage.async_import", {
        "task_id": task_id,
        "file_key": file_key,
        "file_name": file_name,
        "file_md5": md5,
        "file_size": size,
    })
    elapsed = 0
    while elapsed < poll:
        time.sleep(interval)
        elapsed += interval
        res = _mcp_call("manage.import_progress", {"task_id": task_id})
        progress = res.get("progress")
        if res.get("file_id") or (progress is not None and progress >= 100):
            return res.get("file_id"), res.get("file_url"), res.get("file_name") or file_name
        if res.get("error"):
            raise RuntimeError(f"导入失败: {res}")
    raise TimeoutError(f"导入轮询超时（{poll}s）: {task_id}")


# ── Step 5-6：同名覆盖 / 不同名新增 + 移动到目标文件夹 ─────────────────────

def list_folder(folder_id, limit=200):
    """列出目标文件夹下的所有文件。返回 [(id, title, is_folder, url)]。"""
    items = []
    start = 0
    while True:
        res = _mcp_call("manage.folder_list", {"folder_id": folder_id, "start": start})
        lst = res.get("list") or []
        for it in lst:
            items.append({
                "id": it.get("id"),
                "title": it.get("title", ""),
                "is_folder": it.get("is_folder", False),
                "url": it.get("url", ""),
            })
        if res.get("finish", True) or len(lst) == 0:
            break
        start += len(lst)
        if len(items) >= limit:
            break
    return items


def find_by_title(folder_items, title):
    """在目标文件夹中按标题精确匹配（忽略扩展名差异），返回匹配项列表（非文件夹）。"""
    norm = title.strip().lower()
    norm_noext = os.path.splitext(norm)[0]
    matches = []
    for it in folder_items:
        if it["is_folder"]:
            continue
        it_title = (it.get("title") or "").strip().lower()
        it_noext = os.path.splitext(it_title)[0]
        if it_title == norm or it_noext == norm_noext or it_noext == norm or it_title == norm_noext:
            matches.append(it)
    return matches


def delete_file(file_id):
    """删除腾讯文档文件（首页，进回收站不物理删除）。"""
    _mcp_call("manage.delete_file", {"file_id": file_id, "delete_type": "origin"})


def move_file(file_id, target_folder_id):
    """将文件移动到目标文件夹（首页文件夹）。"""
    _mcp_call("manage.move_file", {"file_id": file_id, "target_folder_id": target_folder_id})


def set_privilege(file_id, policy):
    """设置文档权限策略。policy：2-所有人可读（只读），3-所有人可编辑。"""
    _mcp_call("manage.set_privilege", {"file_id": file_id, "policy": policy})


# ── 腾讯文档 aipage 净化 ────────────────────────────────────────────────────
# 腾讯文档 aipage 导入对含「属性值内嵌完整 HTML + 大量未转义引号」的结构解析不兼容，
# 会把部分源码当作文本泄漏渲染（表现为表格上方出现 HTML 源码乱码）。
# 这些元素仅服务于本地浏览器 JS 交互，腾讯文档在线渲染不执行 JS 且不需要，
# 故在上传前生成净化版：移除 data-flat 巨型属性 + 内联 <script>。

def sanitize_html_for_tencent(html_path):
    """读取 HTML，生成净化版（移除 data-flat 属性与 <script>），返回净化版路径。

    返回 (净化文件路径, 净化前是否发生变化)。净化版写入系统临时目录。
    """
    with open(html_path, "r", encoding="utf-8") as f:
        html = f.read()

    # 1. 移除 data-flat='...' 巨型属性（单引号包裹，内部不含单引号）
    sanitized, n_flat = re.subn(r"data-flat='[^']*'\s*", "", html)
    # 2. 移除内联 <script>...</script> 及其内容
    sanitized, n_script = re.subn(r"<script[\s\S]*?</script>", "", sanitized)
    # 3. 清理可能残留的多余空白
    sanitized = re.sub(r"[ \t]{2,}", " ", sanitized)

    changed = (n_flat > 0 or n_script > 0)
    if not changed:
        return html_path, False

    stem = os.path.splitext(os.path.basename(html_path))[0]
    tmp_dir = tempfile.gettempdir()
    sanitized_path = os.path.join(tmp_dir, f"{stem}__tencent_sanitized.html")
    with open(sanitized_path, "w", encoding="utf-8") as f:
        f.write(sanitized)
    return sanitized_path, True


# ── 主入口 ────────────────────────────────────────────────────────────────────

def upload_html(html_path, target_folder_id="TNLKgDkNdIvP", title=None, dry_run=False, privilege=2):
    """完整上传流程：净化 → 打包 → 导入 → 同名覆盖/新增 → 移动到目标文件夹。

    上传成功后自动设置文档权限为 `privilege`（默认 2=所有人可读，只读）。
    dry_run=True 时只做查询不真正上传。
    """
    result = {"html_path": html_path, "target_folder_id": target_folder_id,
              "action": "unknown", "online_url": "", "file_id": "", "sanitized": False}

    # Step A：查询目标文件夹当前内容（用于同名判定）
    folder_items = list_folder(target_folder_id)
    stem = os.path.splitext(os.path.basename(html_path))[0]
    eff_title = title or stem
    existing = find_by_title(folder_items, eff_title)

    if dry_run:
        result["action"] = "overwrite" if existing else "create"
        result["existing"] = existing
        return result

    # Step A2：净化 HTML（腾讯文档 aipage 兼容）
    sanitized_path, sanitized = sanitize_html_for_tencent(html_path)
    result["sanitized"] = sanitized

    # Step B：打包（净化版）— 传入干净标题，避免 aipage 用净化文件名做标题
    aipage_path, aipage_size, aipage_md5, eff_title = pack_html(sanitized_path, title=eff_title)
    try:
        # Step C：导入
        task_id, file_key, file_name = pre_import_and_upload(aipage_path, aipage_size, aipage_md5, eff_title)
        new_id, new_url, _ = async_import(task_id, file_key, file_name, aipage_md5, aipage_size)

        # Step D：同文件夹去重后移动（若已在目标文件夹则跳过删除）
        if existing:
            # 同名覆盖：删除旧的（保留新导入的）
            result["action"] = "overwrite"
            for old in existing:
                try:
                    delete_file(old["id"])
                except Exception as e:
                    print(f"⚠️ 删除旧同名文档失败 {old.get('title')}: {e}")
        else:
            result["action"] = "create"

        # Step E：移动新文档到目标文件夹
        if new_id:
            try:
                move_file(new_id, target_folder_id)
            except Exception as e:
                print(f"⚠️ 移动文档到文件夹失败: {e}")

            # Step F：设置文档权限（默认所有人可读/只读，保持公开但不可编辑）
            try:
                set_privilege(new_id, privilege)
            except Exception as e:
                print(f"⚠️ 设置文档权限失败: {e}")

        result["file_id"] = new_id or ""
        result["online_url"] = new_url or ""
        return result
    finally:
        # 清理临时 .aipage 与净化版 HTML
        for tmp in (aipage_path, sanitized_path):
            try:
                if tmp and tmp != html_path and os.path.isfile(tmp):
                    os.remove(tmp)
            except OSError:
                pass


def main():
    parser = argparse.ArgumentParser(description="上传本地 HTML 到腾讯文档指定文件夹（同名覆盖/不同名新增）")
    parser.add_argument("html_path", help="本地 HTML 文件路径")
    parser.add_argument("--folder", default="TNLKgDkNdIvP", help="目标文件夹 ID（默认版本计划排期）")
    parser.add_argument("--title", default=None, help="在线文档标题（缺省用 HTML 文件名）")
    parser.add_argument("--privilege", type=int, default=2, choices=[2, 3], help="文档权限策略：2=所有人可读(只读,默认)，3=所有人可编辑")
    parser.add_argument("--dry-run", action="store_true", help="只查询同名情况，不真正上传")
    args = parser.parse_args()

    res = upload_html(args.html_path, target_folder_id=args.folder, title=args.title,
                      dry_run=args.dry_run, privilege=args.privilege)
    print(json.dumps(res, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()