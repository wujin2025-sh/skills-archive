#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
submit_review.py — 科技平台需求评审落地

在需求详情页完成「需求评审」录入（两种情况）：

  情况一：详情页右上角有「完成评审」按钮
      → 点击进入，填写评审要素表单（一级需求类型/营运相关/史诗/所属产品/所属模块/预计交付时间/会议主题/评审结果/会议纪要）→ 点确认

  情况二：右上角无「完成评审」按钮（说明之前已评审过）
      → 往下翻到「需求评审」模块 → 点「新增纪要」→ 直接填写评审正文

用法:
  python3 submit_review.py <req_id> \
      --type <普通业务功能|缺陷> \
      --version <YYYYMMDD> \
      --result <通过|有条件通过|驳回> \
      --minutes "<评审正文>" \
      [--epic "史诗名"] [--operational "营运相关"] \
      [--dry-run] [--inspect]

必填:
  req_id      需求编号，如 R2608070151
  --type      一级需求类型：普通业务功能 / 缺陷（缺陷修复需求选缺陷）
  --version   版本排期，如 20260918（评审预计交付时间 = 版本排期迁移两周，自动计算）
  --result    评审结果：通过 / 有条件通过 / 驳回
  --minutes   评审正文（RVW 正文内容，不含标题）

可选:
  --epic        史诗名称（知道则选择，否则留空）
  --operational 营运相关（按实际情况选择）
  --dry-run     只导航并检测场景，不填写不提交
  --inspect     打印页面可交互元素（按钮/输入/下拉/标签）供校准选择器
"""
import sys, json, asyncio, argparse, re, html
from datetime import datetime, timedelta

from playwright.async_api import async_playwright

import session as SESSION
import config


def load_cfg():
    return config.load_config()


def compute_review_delivery(version: str) -> str:
    """需求评审预计交付时间 = 版本排期 - 2 周（迁移两周）"""
    d = datetime.strptime(version, "%Y%m%d").date()
    return (d - timedelta(days=14)).strftime("%Y-%m-%d")


async def login(page, cfg):
    """（兼容旧调用）直接复用持久化会话，跳过登录表单"""
    await page.goto(cfg["login_url"], wait_until="domcontentloaded", timeout=30000)
    await page.wait_for_timeout(300)


async def wait_demand_loaded(page, timeout=25000):
    """条件等待：页面渲染出「需求背景/需求内容」再继续，替代固定 sleep"""
    try:
        await page.wait_for_function(
            "() => document.body.innerText.includes('需求背景') || document.body.innerText.includes('需求内容')",
            timeout=timeout)
    except Exception:
        await page.wait_for_timeout(2000)


async def detect_scenario(page):
    """检测评审入口场景：返回 'scenario1' / 'scenario2' / 'unknown'"""
    # 情况一：右上角「完成评审」按钮（首次评审入口）
    btn1 = page.locator('button:has-text("完成评审")')
    if await btn1.count() > 0:
        return 'scenario1'
    # 情况二：页面「需求评审」模块的「新增会议纪要」/「新增纪要」按钮
    for name in ["新增会议纪要", "新增纪要"]:
        btn2 = page.locator(f'button:has-text("{name}")')
        if await btn2.count() > 0:
            return 'scenario2'
    # 页面文本兜底判断
    text = await page.evaluate("() => document.body.innerText")
    if '需求评审' in text:
        return 'scenario2'
    return 'unknown'


async def find_form_item(page, label):
    """在 Ant Design 表单中按标签文本定位表单项"""
    # 常见结构: .ant-form-item 内含 label 文本 + 控件
    items = page.locator('.ant-form-item, .form-item, [class*="form-item"], [class*="ant-row"]')
    for i in range(await items.count()):
        item = items.nth(i)
        txt = (await item.inner_text()).strip()
        if label in txt:
            return item
    return None


def _option_match(text: str, target: str) -> bool:
    """选项文本匹配：精确/带前缀/后缀匹配，规避「通过」误命中「未通过」"""
    text = (text or "").strip()
    target = (target or "").strip()
    if not text or not target:
        return False
    if text == target:
        return True
    if text == "评审" + target:      # 评审通过 / 评审驳回
        return True
    if text.endswith(target) and target in text:
        if target == "通过" and "未" in text:   # 评审未通过 → 排除
            return False
        return True
    return False


async def select_antd_option(page, item, option_text):
    """在表单项内点击下拉并选择选项（精确文本匹配，规避子串误命中）"""
    select = item.locator('.ant-select, select, [class*="select"]').first
    if await select.count() == 0:
        print(f"  ⚠️ 未找到可下拉控件: {await item.inner_text()[:30]}")
        return False
    await select.click()
    await SESSION.wait_for_condition(
        page, "() => !!document.querySelector('.ant-select-dropdown:visible')",
        timeout=8000, desc="下拉选项出现")
    # 精确匹配优先：枚举所有下拉选项，按完整文本比对
    opts = page.locator('.ant-select-dropdown:visible [class*="option"], .ant-select-dropdown:visible .ant-select-item')
    for oi in range(await opts.count()):
        o = opts.nth(oi)
        t = (await o.inner_text()).strip()
        if _option_match(t, option_text):
            await o.click()
            await page.wait_for_timeout(500)
            return True
    # 兜底：native select 的 option
    loc = page.locator(f'option:has-text("{option_text}")').first
    if await loc.count() > 0:
        await loc.click()
        await page.wait_for_timeout(500)
        return True
    print(f"  ⚠️ 下拉中未找到选项: {option_text}")
    return False


async def fill_text(page, item, value):
    """在表单项内填写文本/日期输入框"""
    for sel in ['input', '.ant-input', 'textarea']:
        loc = item.locator(sel).first
        if await loc.count() > 0:
            await loc.click()
            await loc.fill(value)
            await page.keyboard.press('Enter')
            await page.wait_for_timeout(500)
            return True
    return False


def md_to_html(text):
    """会议纪要 Markdown → 富文本 HTML：**加粗** → <strong>，空行 → <p><br></p>"""
    out = []
    for line in text.split("\n"):
        if not line.strip():
            out.append("<p><br></p>")
            continue
        leading = len(line) - len(line.lstrip(" "))
        indent = "&nbsp;" * leading
        rest = html.escape(line.lstrip(" "), quote=False)
        rest = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", rest)
        out.append(f"<p>{indent}{rest}</p>")
    return "".join(out)


def strip_markdown_bold(text):
    """纯文本场景去除 ** 标记，避免出现字面星号"""
    return re.sub(r"\*\*(.+?)\*\*", r"\1", text)


async def fill_rich_editor(page, item, minutes):
    """填写会议纪要（支持 iframe富文本TinyMCE / textarea / contenteditable）"""
    # 1) iframe 富文本编辑器（TinyMCE: body.mce-content-body）
    iframe = item.locator('iframe').first
    if await iframe.count() > 0:
        try:
            fr = await iframe.element_handle()
            frame = await fr.content_frame()
            if frame:
                # Markdown → HTML：**加粗** 渲染为真正的加粗
                html_content = md_to_html(minutes)
                await frame.evaluate("""(html) => {
                    const body = document.querySelector('.mce-content-body')
                        || document.querySelector('[contenteditable="true"]')
                        || document.body;
                    body.focus();
                    document.execCommand('selectAll', false, null);
                    document.execCommand('delete', false, null);
                    document.execCommand('insertHTML', false, html);
                }""", html_content)
                await page.wait_for_timeout(500)
                return True
        except Exception as e:
            print(f"  ⚠️ iframe 富文本填写异常: {e}")
    # 2) textarea（纯文本，去除 ** 标记）
    ta = item.locator('textarea').first
    if await ta.count() > 0:
        await ta.fill(strip_markdown_bold(minutes))
        return True
    # 3) contenteditable div（非 iframe 富文本）
    editor = item.locator('[contenteditable="true"], .ql-editor, .tinymce-content').first
    if await editor.count() > 0:
        await page.evaluate("""(html) => {
            const editor = document.querySelector('[contenteditable="true"], .ql-editor, .tinymce-content');
            if (editor) {
                editor.focus();
                const range = document.createRange();
                range.selectNodeContents(editor);
                const sel = window.getSelection();
                sel.removeAllRanges();
                sel.addRange(range);
                document.execCommand('insertHTML', false, html);
            }
        }""", md_to_html(minutes))
        await page.wait_for_timeout(500)
        return True
    print("  ⚠️ 未找到会议纪要输入控件")
    return False


async def inspect_page(page):
    """打印页面可交互元素，供校准选择器"""
    txt = await page.evaluate("() => document.body.innerText")
    print("\n===== 需求标题/状态 =====")
    print(txt[:300].replace('\n', ' | '))
    print("\n===== 评审入口检测 =====")
    for kw in ["完成评审", "需求评审", "新增会议纪要", "新增纪要", "修改评审结论", "会议纪要"]:
        print(f"  '{kw}': {'✓' if kw in txt else '✗'}")
    print("\n===== 按钮 =====")
    btns = page.locator('button')
    for i in range(min(await btns.count(), 40)):
        t = (await btns.nth(i).inner_text()).strip()
        if t:
            print(f"  [{i}] {t[:50]}")
    print("\n===== 输入框 =====")
    inputs = page.locator('input, textarea')
    for i in range(min(await inputs.count(), 40)):
        el = inputs.nth(i)
        ph = await el.get_attribute('placeholder') or ''
        print(f"  [{i}] <{await el.evaluate('e => e.tagName')}> placeholder={ph[:40]}")
    print("\n===== 含标签的表单项文本 =====")
    items = page.locator('.ant-form-item, [class*="form-item"]')
    for i in range(min(await items.count(), 30)):
        txt = (await items.nth(i).inner_text()).strip().replace('\n', ' ')
        if txt:
            print(f"  [{i}] {txt[:60]}")


async def fill_scenario1(page, args, cfg):
    """情况一：点击「完成评审」→ 填写表单 → 确认"""
    print("  [场景1] 检测到「完成评审」按钮，点击进入...")
    await page.locator('button:has-text("完成评审")').first.click()
    await SESSION.wait_for_condition(
        page, "() => !!document.querySelector('.ant-modal-content')",
        timeout=10000, desc="完成评审弹窗出现")

    delivery = compute_review_delivery(args.version)
    print(f"  预计交付时间（版本 {args.version} 迁移两周）: {delivery}")

    # 1) 一级需求类型
    item = await find_form_item(page, "一级需求类型")
    if item:
        await select_antd_option(page, item, args.type)

    # 2) 营运相关（可选）
    if args.operational:
        item = await find_form_item(page, "营运相关")
        if item:
            await select_antd_option(page, item, args.operational)

    # 3) 史诗（可选）
    if args.epic:
        item = await find_form_item(page, "史诗")
        if item:
            await select_antd_option(page, item, args.epic)

    # 4) 所属产品 / 所属模块：不填（跳过）

    # 5) 需求评审预计交付时间
    item = await find_form_item(page, "需求评审预计交付时间")
    if item:
        await fill_text(page, item, delivery)

    # 6) 会议主题：默认（跳过）

    # 7) 评审结果
    item = await find_form_item(page, "评审结果")
    if item:
        await select_antd_option(page, item, args.result)

    # 8) 会议纪要：RVW 正文
    item = await find_form_item(page, "会议纪要")
    if item:
        await fill_rich_editor(page, item, args.minutes)

    if args.dry_run:
        print("  [dry-run] 已检测并填写，跳过确认提交")
        return
    print("  点击「确认」提交...")
    for sel in ['button:has-text("确认")', 'button:has-text("确定")',
                'button:has-text("提 交")', 'button:has-text("提交")']:
        btn = page.locator(sel).first
        if await btn.count() > 0:
            await btn.click()
            await SESSION.wait_for_condition(
                page, "() => !!document.querySelector('.ant-message-success') || !document.querySelector('.ant-modal-content')",
                timeout=8000, desc="提交成功提示/弹窗关闭")
            print("  ✅ 已点击提交按钮")
            return
    print("  ⚠️ 未找到确认/提交按钮，请人工确认")


async def select_review_result(page, modal, result_text):
    """选择评审结果并校验生效（含失败重试），避免默认值「评审未通过」被提交"""
    # 优先在含「评审结果」标签的表单项内定位下拉；找不到则回退到弹窗内第一个下拉
    item = await find_form_item(page, "评审结果")
    target = item if item else modal
    for attempt in range(2):
        await select_antd_option(page, target, result_text)
        await page.wait_for_timeout(800)
        sel = target.locator('.ant-select').first
        cur_clean = (await sel.inner_text()).replace("\n", " ").strip() if await sel.count() > 0 else ""
        # 校验：目标为「通过」时，需含「通过」且不含「未通过」
        if result_text == "通过":
            if "通过" in cur_clean and "未" not in cur_clean:
                return True
        else:
            if result_text in cur_clean:
                return True
        print(f"  ⚠️ 第{attempt+1}次选择「{result_text}」未生效（当前: {cur_clean}），重试...")
        await page.wait_for_timeout(800)
    print(f"  ⚠️ 评审结果选择失败，当前值: {cur_clean}，请人工确认")
    return False


async def fill_scenario2(page, args, cfg):
    """情况二：无「完成评审」→ 需求评审模块 → 新增会议纪要 → 弹窗填写评审正文"""
    print("  [场景2] 检测到已评审过，定位「需求评审」模块「新增会议纪要」...")
    # 需求评审模块可能在页面下方，先滚动到「需求评审」区域
    text = await page.evaluate("() => document.body.innerText")
    if "需求评审" in text:
        await page.mouse.wheel(0, 800)
        await page.wait_for_timeout(1200)
    btn = None
    for name in ["新增会议纪要", "新增纪要"]:
        loc = page.locator(f'button:has-text("{name}")').first
        if await loc.count() > 0:
            btn = loc
            break
    if btn and await btn.count() > 0:
        await btn.scroll_into_view_if_needed()
        await btn.click()
        # 等待弹窗出现
        await SESSION.wait_for_condition(
            page, "() => !!document.querySelector('.ant-modal-content')",
            timeout=10000, desc="新增会议纪要弹窗出现")
        await page.wait_for_timeout(300)

    # 定位弹窗（新增会议纪要）
    modal = page.locator('.ant-modal-content:visible').first

    # 1) 评审结果（下拉，校验生效）
    if args.result:
        await select_review_result(page, modal, args.result)

    # 2) 会议纪要正文（iframe 富文本编辑器）
    filled = await fill_rich_editor(page, modal, args.minutes) if await modal.count() > 0 else False
    if not filled:
        print("  ⚠️ 未能自动填入会议纪要正文，请人工在弹窗中粘贴")

    if args.dry_run:
        print("  [dry-run] 已填写评审正文，跳过提交")
        return
    # 3) 提交
    for sel in ['button:has-text("提 交")', 'button:has-text("提交")',
                'button:has-text("确认")', 'button:has-text("确定")', 'button:has-text("保存")']:
        b = page.locator(sel).first
        if await b.count() > 0:
            await b.click()
            await SESSION.wait_for_condition(
                page, "() => !!document.querySelector('.ant-message-success') || !document.querySelector('.ant-modal-content')",
                timeout=8000, desc="提交成功提示/弹窗关闭")
            print("  ✅ 已点击提交按钮")
            return
    print("  ⚠️ 未找到提交按钮，请人工确认")


def main():
    parser = argparse.ArgumentParser(description="科技平台需求评审落地")
    parser.add_argument("req_id", help="需求编号，如 R2608070151")
    parser.add_argument("--type", choices=["普通业务功能", "缺陷"], help="一级需求类型")
    parser.add_argument("--version", help="版本排期 YYYYMMDD，如 20260918")
    parser.add_argument("--result", choices=["通过", "有条件通过", "驳回"], help="评审结果")
    parser.add_argument("--minutes", help="评审正文（RVW 正文，不含标题）")
    parser.add_argument("--epic", default="", help="史诗名称（可选）")
    parser.add_argument("--operational", default="", help="营运相关（可选）")
    parser.add_argument("--dry-run", action="store_true", help="只检测不提交")
    parser.add_argument("--inspect", action="store_true", help="打印页面元素供校准")
    parser.add_argument("--api", dest="mode", action="store_const", const="api",
                        default="api", help="REST API 落地（默认，≤1s）")
    parser.add_argument("--browser", dest="mode", action="store_const", const="browser",
                        help="强制 Playwright 兜底（~10s）")
    args = parser.parse_args()

    # 非 inspect 模式需校验必填参数
    if not args.inspect and not (args.type and args.version and args.result and args.minutes):
        parser.error("--type/--version/--result/--minutes 为必填（--inspect 模式除外）")

    # ---------- API 快速路径（默认，≤1s；失败自动回退浏览器） ----------
    if args.mode == "api" and not args.inspect:
        try:
            import platform_api
            print(f"[api] 评审落地 {args.req_id}：{args.result}...")
            res = platform_api.save_review(
                args.req_id, args.result, args.minutes,
                type_=args.type, version=args.version, epic=args.epic, operational=args.operational,
                dry_run=args.dry_run)
            import json
            print(json.dumps(res, ensure_ascii=False, indent=2))
            if res.get("dry_run"):
                print("[api] dry-run，未提交")
            elif res.get("skipped"):
                print(f"[api] ⏭ 幂等跳过：{res.get('reason')} (id={res.get('id')})")
            else:
                print(f"[api] ✅ 评审落地成功")
            return
        except Exception as e:
            print(f"[api] 失败（{e}），回退浏览器...", flush=True)

    # 仅在非 API 模式或 API 模式报错失败时，通过 asyncio 启动异步浏览器逻辑
    asyncio.run(run_browser(args))


async def run_browser(args):
    cfg = load_cfg()
    # base_url 已含 /kjpt（如 https://fintech.gtht.com.cn/kjpt）
    demand_url = f"{config.get_base_url()}/DemandManage/details?demandId={args.req_id}"

    page, ctx, pw = await SESSION.open_page_async()
    try:
        print(f"打开需求详情: {args.req_id}")
        await page.goto(demand_url, wait_until="domcontentloaded", timeout=40000)
        await wait_demand_loaded(page)

        if args.inspect:
            await inspect_page(page)
            return

        scenario = await detect_scenario(page)
        print(f"检测到评审场景: {scenario}")

        if scenario == 'scenario1':
            await fill_scenario1(page, args, cfg)
        elif scenario == 'scenario2':
            await fill_scenario2(page, args, cfg)
        else:
            print("⚠️ 无法检测评审入口场景，请人工确认页面结构")
            await inspect_page(page)
    finally:
        await SESSION.close_page(ctx, pw)

    print("\n完成。")


if __name__ == "__main__":
    main()
