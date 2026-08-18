#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从国泰海通科技平台获取需求详情 —— **API 优先，秒级返回**（性能优化后）。

用法:
    python3 fetch_demand.py <demand_url> [--playwright]

流程（优化）:
  1. 复用 session.py 的 JWT token（8h 有效，缓存于 session.json，不再每次登录）；
  2. `requests` 直调 `queryDemandsubInfo` 获取需求全部要素（~0.2s）；
  3. 解析 description 富文本 → 背景/内容/图片；
  4. 并行下载图片与附件（带 token）；
  5. 输出 JSON（schema 兼容旧版，并扩充关键字段）。

--playwright: 强制走旧的 Playwright DOM 抓取兜底（API 异常时自动回退）。

输出字段:
  demand_id, title, status(boardName), priority, expected_online(wishDate),
  submitter, submitter_dept, company_project, demand_type, receiver,
  background, content, images[], attachments[], + 全量需求要素 extra
"""
import sys
import json
import re
import html as html_lib
import hashlib
import time
from pathlib import Path

import session
import config

VAULT_ATTACH = config.get_attach_dir()
VAULT_ATTACH.mkdir(parents=True, exist_ok=True)

DEMAND_PATHS = {
    "detail": "/demand-service/demandsub/queryDemandsubInfo",
    "links": "/demand-service/demandsub/queryDemandsubLink",
    "stories": "/demand-service/demandsub/queryStoryDemand",
    "roles": "/demand-service/demandsub/queryDemandRoleInfo",
    "flow": "/demand-service/demandsub/queryDemandFlowInfo",
}


def _extract_id(demand_url: str) -> str:
    m = re.search(r'demandId=([\w-]+)', demand_url)
    if not m:
        raise ValueError(f"无法从 URL 提取 demandId: {demand_url}")
    return m.group(1)


def _html_to_text(h: str) -> str:
    """富文本 → 纯文本（保留段落换行）"""
    if not h:
        return ""
    h = re.sub(r'<br\s*/?>', '\n', h)
    h = re.sub(r'</(p|div|h[1-6]|li|tr)>', '\n', h, flags=re.I)
    h = re.sub(r'<[^>]+>', '', h)
    h = html_lib.unescape(h)
    h = h.replace(' ', ' ')
    h = re.sub(r'\n{3,}', '\n\n', h)
    lines = [ln.rstrip() for ln in h.split('\n')]
    return '\n'.join(lines).strip()


def _extract_sections(text: str):
    """从纯文本中切出 一、需求背景 / 二、需求内容"""
    bg, content = "", ""
    bg_m = re.search(r'一、需求背景\s*(.*?)(?=二、需求内容|备注|上传|$)', text, re.DOTALL)
    if bg_m:
        bg = bg_m.group(1).strip()
    ct_m = re.search(r'二、需求内容\s*(.*?)(?=三、|备注|上传|$)', text, re.DOTALL)
    if ct_m:
        content = ct_m.group(1).strip()
    if not bg and not content:
        bg = text  # 未分节时整段作为背景
    return bg, content


def _parse_images(desc_html: str):
    """提取 description 中的图片 URL"""
    return list(dict.fromkeys(
        m for m in re.findall(r'<img[^>]+src=["\']([^"\']+)["\']', desc_html)
        if m and 'data:' not in m and not re.search(r'icon|logo|avatar', m, re.I)
    ))


async def _download_parallel(urls: list, prefix: str):
    """并行下载，返回保存的文件名列表"""
    import asyncio
    saved = []

    async def _one(u):
        h = hashlib.md5(u.encode()).hexdigest()[:8]
        fpath = VAULT_ATTACH / f"{prefix}_{h}.tmp"
        ok, ct = session.api_download_ext(u, fpath)
        if not ok or not fpath.exists() or fpath.stat().st_size == 0:
            fpath.unlink(missing_ok=True)
            return None
        ext = "png"
        if ct:
            m = re.search(r'image/(\w+)', ct)
            if m:
                ext = {"jpeg": "jpg", "x-png": "png"}.get(m.group(1).lower(), m.group(1).lower())
        final = VAULT_ATTACH / f"{prefix}_{h}.{ext}"
        fpath.replace(final)
        return final.name

    results = await asyncio.gather(*[_one(u) for u in urls])
    return [r for r in results if r]


def fetch_by_api(demand_id: str) -> dict:
    """API 优先：直调需求详情接口"""
    t0 = time.time()
    sess = session.get_session()
    user_info = sess.get("user_info") or {}
    uid = user_info.get("workno") or "020822"
    uname = user_info.get("personname") or "刘辉"

    d = session.api_post(DEMAND_PATHS["detail"], {"demandId": demand_id, "userId": uid, "userName": uname})

    desc_html = d.get("description", "")
    text = _html_to_text(desc_html)
    bg, content = _extract_sections(text)

    # 图片下载（并行）
    img_urls = _parse_images(desc_html)
    saved_images = asyncio_run(_download_parallel(img_urls, "demand")) if img_urls else []

    # 附件（queryDemandsubLink）
    saved_attachments = []
    try:
        links = session.api_post(DEMAND_PATHS["links"], {"demandId": demand_id})
        if links:
            for it in links:
                u = it.get("url") or it.get("fileUrl") or it.get("link") or it.get("downloadUrl")
                nm = it.get("name") or it.get("fileName") or it.get("fileRealName")
                if not u:
                    continue
                fname = re.sub(r'[/\\]', '_', str(nm or u.split("?")[0].split("/")[-1] or "att"))
                if session.api_download(u, VAULT_ATTACH / fname):
                    saved_attachments.append(fname)
    except Exception as e:
        print(f"[warn] 附件解析失败: {e}", file=sys.stderr)

    result = {
        "demand_id": demand_id,
        "title": d.get("summary", ""),
        "status": d.get("boardName", ""),
        "submitter": d.get("userName", ""),
        "submitter_id": d.get("userId", ""),
        "submitter_dept": d.get("deptName", ""),
        "priority": d.get("priority", ""),
        "expected_online": (d.get("wishDate") or "").replace("-", ""),
        "background": bg,
        "content": content,
        "images": saved_images,
        "attachments": saved_attachments,
        "elapsed_s": round(time.time() - t0, 2),
        "extra": {
            "companyProjectNo": d.get("companyProjectNo", ""),
            "companyProjectName": d.get("companyProjectName", ""),
            "demandTypeName": d.get("demandTypeName", ""),
            "subdivisionTypeName": d.get("subdivisionTypeName", ""),
            "deptName": d.get("deptName", ""),
            "deptId": d.get("deptId", ""),
            "receiver": d.get("receiver", ""),
            "commonReceiver": d.get("commonReceiver", ""),
            "businessAcceptorName": d.get("businessAcceptorName", ""),
            "devHeaderName": d.get("devHeaderName", ""),
            "taskDevHeaderName": d.get("taskDevHeaderName", ""),
            "gmName": d.get("gmName", ""),
            "demandComplexity": d.get("demandComplexity", ""),
            "storySystem": d.get("storySystem", ""),
            "storyProjectName": d.get("storyProjectName", ""),
            "isGrayscale": d.get("isGrayscale", ""),
            "oaNodeStatusName": d.get("oaNodeStatusName", ""),
            "launchTime": d.get("launchTime", ""),
            "createTime": d.get("createTime", ""),
            "description_html": desc_html,
        },
    }
    return result


def asyncio_run(coro):
    import asyncio
    try:
        return asyncio.run(coro)
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()


# ---------------------------------------------------------------------------
# Playwright 兜底（API 异常时）
# ---------------------------------------------------------------------------
def _fetch_by_playwright_fallback(demand_url: str) -> dict:
    """旧版 DOM 抓取兜底：自包含 asyncio.run，复用持久化 profile 跳过登录表单"""
    import asyncio
    return asyncio.run(_pw_fallback_impl(demand_url))


async def _pw_fallback_impl(demand_url: str) -> dict:
    import session as S
    from playwright.async_api import async_playwright

    cfg = S._load_cfg()
    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(
            str(S.PROFILE_DIR), headless=True, viewport={"width": 1920, "height": 1400})
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        await page.goto(cfg["login_url"], wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(300)
        token = ""
        try:
            token = await page.evaluate('localStorage.getItem("GTJA_TOKEN") || ""')
        except Exception:
            pass
        if not S.token_is_valid(token):
            sess = S._read_session()
            if S.token_is_valid(sess.get("token", "")):
                ui = sess.get("user_info") or {}
                await page.evaluate("""(o) => {
                    localStorage.setItem('GTJA_TOKEN', o.t);
                    if (o.u && o.u.token) localStorage.setItem('userInfo', JSON.stringify(o.u));
                }""", {"t": sess["token"], "u": ui})
                await page.reload(wait_until="domcontentloaded")
            else:
                await page.fill('#workno', cfg["username"])
                await page.fill('#password', cfg["password"])
                await page.click('button:has-text("Submit")')
                await page.wait_for_timeout(2500)
        try:
            await page.goto(demand_url, wait_until="domcontentloaded", timeout=40000)
            for _ in range(30):
                await page.wait_for_timeout(300)
                txt = await page.evaluate("() => document.body.innerText")
                if "需求背景" in txt:
                    break
            page_title = await page.title()
            m = re.search(r'【(.+?)】(.+)', page_title)
            title = f"【{m.group(1)}】{m.group(2)}" if m else page_title.replace("需求详情-", "").strip()
            text = await page.evaluate("""() => {
                const b = document.body.cloneNode(true);
                b.querySelectorAll('script,style,noscript').forEach(e => e.remove());
                return b.innerText;
            }""")
            result = {
                "demand_id": _extract_id(demand_url), "title": title,
                "status": "", "submitter": "", "priority": "", "expected_online": "",
                "background": "", "content": "", "images": [], "attachments": [],
            }
            bg_m = re.search(r'一、需求背景\s*(.+?)(?:二、需求内容|$)', text, re.DOTALL)
            ct_m = re.search(r'二、需求内容\s*(.+?)(?:备注：|上传|$)', text, re.DOTALL)
            if bg_m: result["background"] = bg_m.group(1).strip()
            if ct_m: result["content"] = ct_m.group(1).strip()
            pri = re.search(r'P[0-3]', text)
            if pri: result["priority"] = pri.group(0)
            ol = re.search(r'期望上线时间\s*(\d{4}-\d{2}-\d{2})', text)
            if ol: result["expected_online"] = ol.group(1).replace("-", "")
            return result
        finally:
            await ctx.close()


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "请提供需求链接"}, ensure_ascii=False))
        sys.exit(1)
    url = sys.argv[1]
    force_pw = "--playwright" in sys.argv[2:]
    try:
        if force_pw:
            raise RuntimeError("--playwright 强制走兜底")
        result = fetch_by_api(_extract_id(url))
    except Exception as e:
        print(f"[warn] API 路径失败({e})，回退 Playwright...", file=sys.stderr)
        result = asyncio_run(_fetch_by_playwright_fallback(url))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
