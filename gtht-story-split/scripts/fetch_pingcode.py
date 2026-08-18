#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fetch_pingcode.py — PingCode wiki 页面抓取 + 本地缓存（性能优化）

用途：快速获取 PingCode wiki 建设需求页面正文，供需求受理分析（REQ/SOL/RVW）使用。

设计要点：
  1. 直接 `launch_persistent_context(PROFILE_DIR)` 打开 wiki URL，复用已持久化的
     PingCode cookie（.browser_profile/），**不**复用 open_page_async()
     （它会去查平台 GTJA_TOKEN，触发无谓的平台登录）。
  2. 若页面跳转 LDAP 登录页（URL 含 login/sso/ldap 或存在 input[type=password]），
     用 config.json 的 `pingcode` 凭据自动登录，写回 cookie 后重访目标页。
  3. 渲染等待：body.innerText 长度稳定 2 轮且 >300 字 → 滚动到底触发懒渲染 → 回顶。
  4. 内容提取：优先 .wiki-content/.markdown-body/article/main 等容器（取 innerText 最长），
     剔除 nav/aside/header/script 等噪点；<100 字时遍历 iframe 兜底。
  5. 缓存到 `50-业务知识/wiki-cache/wiki-<pageId>.txt` + `<pageId>.meta.json`
     （sha256/fetched_at/title/len），原子写（.tmp + replace）。
     同一 wiki 页（如 NViSqBja，8 个需求共享）只抓一次，二次 <1s。

用法:
  python3 fetch_pingcode.py <wiki_url> [--force] [--wait-keyword 关键词]

输出:
  - 正文 → stdout（供 Claude 捕获）
  - 缓存路径 / 耗时 / 缓存命中 → stderr
"""
import sys
import json
import time
import re
import asyncio
import hashlib
from pathlib import Path
from typing import Optional

import session as SESSION
import config

VAULT_ROOT = config.get_vault_root()
CACHE_DIR = config.get_pingcode_cache_dir()

# 内容提取 JS：优先命中最长的正文容器；剔除导航等噪点
EXTRACT_JS = """() => {
  const strip = 'script,style,noscript,nav,aside,header,footer,svg,' +
                '.wiki-sidebar,.ant-layout-sider,[class*="menu"],[class*="nav"],[class*="breadcrumb"],' +
                '[class*="toolbar"],[class*="header"],[class*="footer"]';
  const sels = ['.wiki-content', '.markdown-body', '.ql-editor', '.wiki-page-content',
                '[class*="page-content"]', '[class*="editor"]',
                'article', 'main', '.prose', '.page-content', '#page-content'];
  let best = null;
  for (const sel of sels) {
    const els = document.querySelectorAll(sel);
    for (const el of els) {
      const clone = el.cloneNode(true);
      clone.querySelectorAll(strip).forEach(n => n.remove());
      const t = (clone.innerText || clone.textContent || '').replace(/\\n{3,}/g, '\\n\\n').trim();
      if (t.length > 50 && (!best || t.length > best.length)) best = t;
    }
  }
  if (!best) {
    const b = document.body.cloneNode(true);
    b.querySelectorAll(strip).forEach(n => n.remove());
    best = (b.innerText || b.textContent || '').replace(/\\n{3,}/g, '\\n\\n').trim();
  }
  return best;
}"""


def extract_page_id(url: str) -> str:
    """从 wiki URL 提取 pageId，如 .../pages/NViSqBja → NViSqBja"""
    m = re.search(r'/pages/([A-Za-z0-9_-]+)', url)
    if m:
        return m.group(1)
    # 兜底：取 URL 最后一段
    return url.rstrip("/").split("/")[-1] or "page"


# ---------------------------------------------------------------------------
# 缓存
# ---------------------------------------------------------------------------
def _read_cache(page_id: str, wait_keyword: Optional[str]):
    """命中返回 (text, title, meta)；否则 None。wait_keyword 不在缓存正文中时视为未命中重抓"""
    txt = CACHE_DIR / f"wiki-{page_id}.txt"
    meta = CACHE_DIR / f"{page_id}.meta.json"
    if not (txt.exists() and meta.exists()):
        return None
    try:
        m = json.loads(meta.read_text(encoding="utf-8"))
        content = txt.read_text(encoding="utf-8")
    except Exception:
        return None
    if wait_keyword and wait_keyword not in content:
        return None
    return content, m.get("title", ""), m


def _write_cache(page_id: str, text: str, title: str):
    """原子写缓存（.tmp + replace）"""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
    meta = {"sha256": sha, "fetched_at": int(time.time()), "title": title, "len": len(text)}
    txt_tmp = CACHE_DIR / f"wiki-{page_id}.txt.tmp"
    meta_tmp = CACHE_DIR / f"{page_id}.meta.json.tmp"
    txt_tmp.write_text(text, encoding="utf-8")
    txt_tmp.replace(CACHE_DIR / f"wiki-{page_id}.txt")
    meta_tmp.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    meta_tmp.replace(CACHE_DIR / f"{page_id}.meta.json")
    return meta


# ---------------------------------------------------------------------------
# 浏览器抓取
# ---------------------------------------------------------------------------
async def _ensure_login(page, url: str, pingcode_cfg: dict) -> bool:
    """若页面在登录/LDAP 页，用 pingcode 凭据自动登录并重访目标页。返回是否发生过登录"""
    cur = page.url.lower()
    has_pw = await page.query_selector('input[type="password"]')
    if not (has_pw or "login" in cur or "sso" in cur or "ldap" in cur):
        return False  # 已登录

    print("[pingcode] 检测到登录页，自动登录...", file=sys.stderr, flush=True)
    await page.wait_for_timeout(600)
    ok_fill = False
    try:
        ok_fill = await page.evaluate("""(creds) => {
          const pw = document.querySelector('input[type="password"]');
          if (!pw) return false;
          const inputs = Array.from(document.querySelectorAll('input'));
          const textInput = inputs.find(i => {
            const t = (i.getAttribute('type') || 'text').toLowerCase();
            return ['text','email','username','tel',''].includes(t) && i.offsetParent !== null;
          });
          const setVal = (el, v) => {
            const proto = el instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
            const setter = Object.getOwnPropertyDescriptor(proto, 'value').set;
            setter.call(el, v);
            el.dispatchEvent(new Event('input', {bubbles: true}));
            el.dispatchEvent(new Event('change', {bubbles: true}));
          };
          if (textInput) setVal(textInput, creds.username);
          setVal(pw, creds.password);
          return true;
        }""", {"username": pingcode_cfg.get("username", ""), "password": pingcode_cfg.get("password", "")})
    except Exception:
        ok_fill = False

    if not ok_fill:
        print("[pingcode] ⚠️ 未找到登录表单，无法自动登录", file=sys.stderr)
        return True

    try:
        await page.evaluate("""() => {
          const btns = Array.from(document.querySelectorAll('button, input[type="submit"]'));
          const t = btns.find(b => /登录|登\\s*录|sign\\s*in|login|登 录/i.test(b.innerText || b.value || ''));
          (t || btns[btns.length - 1])?.click();
        }""")
    except Exception:
        pass

    # 等待离开登录页
    for _ in range(40):
        await page.wait_for_timeout(500)
        cur = page.url.lower()
        has_pw = await page.query_selector('input[type="password"]')
        if not (has_pw or "login" in cur or "sso" in cur or "ldap" in cur):
            break
    # 重访目标页（cookie 已写回 profile）
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=45000)
    except Exception as e:
        print(f"[pingcode] 登录后重访目标页失败: {e}", file=sys.stderr)
    return True


async def _wait_render(page, wait_keyword: Optional[str]):
    """渲染等待：body.innerText 稳定 2 轮且 >300 字；滚动触发懒渲染；可选等关键词出现"""
    last_len, stable = -1, 0
    for _ in range(40):
        await page.wait_for_timeout(250)
        try:
            txt = await page.evaluate("() => document.body ? document.body.innerText.length : 0")
        except Exception:
            txt = 0
        if txt == last_len:
            stable += 1
        else:
            stable = 0
            last_len = txt
        if stable >= 2 and txt > 300:
            break
    # 懒渲染触发：滚到底 → 300ms 条件轮询 → 回顶
    try:
        await page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
        # 300ms 轮询等正文长度再增长（懒加载内容追加），稳定即回顶
        for _ in range(4):
            before = await page.evaluate("() => document.body ? document.body.innerText.length : 0")
            await page.wait_for_timeout(300)
            after = await page.evaluate("() => document.body ? document.body.innerText.length : 0")
            if after == before:
                break
        await page.evaluate("() => window.scrollTo(0, 0)")
        await page.wait_for_timeout(300)
    except Exception:
        pass
    # 可选：等待关键词出现（内容懒加载未完成时）
    if wait_keyword:
        for _ in range(24):
            try:
                t = await page.evaluate(EXTRACT_JS) or ""
            except Exception:
                t = ""
            if wait_keyword in t:
                return
            await page.wait_for_timeout(500)


async def _extract_text(page):
    """提取正文 + 标题；<100 字时遍历 iframe 兜底"""
    text = ""
    try:
        text = (await page.evaluate(EXTRACT_JS)) or ""
    except Exception:
        pass
    if len(text) < 100:
        for fr in page.frames:
            if fr == page.main_frame:
                continue
            try:
                t = (await fr.evaluate(EXTRACT_JS)) or ""
                if len(t) > len(text):
                    text = t
            except Exception:
                pass
    title = ""
    try:
        title = await page.title()
    except Exception:
        pass
    return text.strip(), title


async def _fetch(url: str, wait_keyword: Optional[str]):
    """抓取 wiki 页面正文，返回 (text, title, elapsed_s)"""
    from playwright.async_api import async_playwright

    cfg = SESSION._load_cfg()
    pingcode_cfg = cfg.get("pingcode", {})
    p = await async_playwright().start()
    ctx = None
    t0 = time.time()
    try:
        ctx = await p.chromium.launch_persistent_context(
            str(SESSION.PROFILE_DIR), headless=True, viewport={"width": 1920, "height": 1400})
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        await page.goto(url, wait_until="domcontentloaded", timeout=45000)
        await page.wait_for_timeout(300)
        await _ensure_login(page, url, pingcode_cfg)
        await _wait_render(page, wait_keyword)
        text, title = await _extract_text(page)
        return text, title, time.time() - t0
    finally:
        if ctx is not None:
            try:
                await ctx.close()
            except Exception:
                pass
        try:
            await p.stop()
        except Exception:
            pass


def main():
    args = sys.argv[1:]
    force = "--force" in args
    args = [a for a in args if a != "--force"]
    wait_keyword = None
    if "--wait-keyword" in args:
        i = args.index("--wait-keyword")
        wait_keyword = args[i + 1] if i + 1 < len(args) else None
        del args[i:i + 2]

    if len(args) < 1:
        print("用法: python3 fetch_pingcode.py <wiki_url> [--force] [--wait-keyword 关键词]",
              file=sys.stderr)
        sys.exit(1)

    url = args[0]
    page_id = extract_page_id(url)
    t0 = time.time()

    if not force:
        cached = _read_cache(page_id, wait_keyword)
        if cached:
            text, title, meta = cached
            print(f"[cache] hit  page={page_id}  sha={meta['sha256'][:8]}  len={meta['len']}  "
                  f"({time.time()-t0:.2f}s)", file=sys.stderr)
            print(text, end="" if text.endswith("\n") else "\n")
            return

    print(f"[pingcode] 抓取 wiki 页面 page={page_id} url={url}"
          + (f"  wait_keyword={wait_keyword}" if wait_keyword else ""), file=sys.stderr, flush=True)
    try:
        text, title, elapsed = asyncio.run(_fetch(url, wait_keyword))
    except Exception as e:
        print(f"[pingcode] ❌ 抓取失败: {e}", file=sys.stderr)
        sys.exit(2)

    if not text:
        print("[pingcode] ⚠️ 页面正文为空（可能需人工登录后重试）", file=sys.stderr)
        sys.exit(3)

    meta = _write_cache(page_id, text, title)
    out_path = CACHE_DIR / f"wiki-{page_id}.txt"
    print(f"[pingcode] 已缓存 → {out_path}  len={meta['len']}  title={title or ''}  "
          f"耗时 {elapsed:.1f}s（首次抓取）", file=sys.stderr)
    print(text, end="" if text.endswith("\n") else "\n")


if __name__ == "__main__":
    main()
