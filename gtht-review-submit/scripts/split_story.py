#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
split_story.py — 科技平台需求 Story 自动拆分

按「需求评审结论」将需求拆分为各目标系统的 Story（所属Story 模块），
支持「使用模板」自动填充 + 手动补齐模板未覆盖字段 + 复制父需求描述 + 配合测试前缀。

用法:
  python3 split_story.py <req_id> \
      --systems "集中清算:配合测试,集中交易:配合测试,三方存管:配合测试,参数管理中心后台:配合测试" \
      [--template-map "参数管理中心后台=参数后台"] \
      [--impact-grayscale 否] \
      [--need-biz-accept auto|是|否] \
      [--biz-acceptor auto|姓名] \
      [--dry-run]

参数:
  req_id        需求编号，如 R2608100032
  --systems     必填，逗号分隔 "系统名:类型"，类型 ∈ 改造|配合测试
  --template-map 可选，逗号分隔 "系统名=模板名"，用于系统名与模板名不一致的映射
  --impact-grayscale 是否影响灰度升级：是|否（跨系统接口有变更一般选是，否则否），默认 否
  --need-biz-accept 是否需要业务验收：auto(按需求提交人部门推断)|是|否，默认 auto
  --biz-acceptor  业务验收人：auto(取需求提交人)|姓名，默认 auto
  --dry-run     只填写不提交

规则（来自需求受理流程）:
  1. 目标系统若已有 Story，则跳过，每个系统仅拆一个 Story；
  2. 使用模板：右上角「使用模板」→ 选对应系统模板，自动填充大部分属性；
  3. 模板未覆盖字段：
     - 是否影响灰度升级：按评审结论（跨系统接口有变更→是，否则→否）
     - 是否需要业务验收：需求提交人非「技术研发部」→是，否则→否
     - 业务验收人：需要业务验收时取需求提交人，否则置空
  4. 点击「复制父需求描述」填充 Story 正文；
  5. 配合测试系统在 Story 名称前加「【配合测试】」，改造系统不加。
"""
import sys, json, asyncio, argparse, re

from playwright.async_api import async_playwright

import session as SESSION
import config

# 需求信息 API 缓存（一次加载，多处复用）
_DEMAND_INFO_CACHE = None
_CURRENT_REQ_ID = ""


def get_demand_info_api(req_id: str) -> dict:
    """API 获取需求要素（提交人/部门/已有 Story/标题），替代 DOM 读取"""
    global _DEMAND_INFO_CACHE
    if _DEMAND_INFO_CACHE is None:
        sess = SESSION.get_session()
        ui = sess.get("user_info") or {}
        uid = ui.get("workno") or config.get_default("cur_user_no", "020822")
        uname = ui.get("personname") or config.get_default("cur_user_name", "刘辉")
        _DEMAND_INFO_CACHE = SESSION.api_post(
            "/demand-service/demandsub/queryDemandsubInfo",
            {"demandId": req_id, "userId": uid, "userName": uname})
    return _DEMAND_INFO_CACHE


def get_existing_story_systems_api(req_id: str) -> set:
    """API 读取已有 Story 的所属系统集合"""
    data = SESSION.api_get("/demand-service/demandsub/queryStoryDemand",
                           {"current": 1, "demandId": req_id, "pageSize": 9999})
    systems = set()
    for s in (data or {}).get("voList", []):
        nm = (s.get("systemName") or "").strip()
        if nm:
            systems.add(nm)
    return systems


def load_cfg():
    return config.load_config()


def parse_systems(s):
    """解析 --systems: "集中清算:配合测试,集中交易:改造" → [{'name':'集中清算','type':'配合测试'}, ...]"""
    out = []
    for item in s.split(","):
        item = item.strip()
        if not item:
            continue
        if ":" in item:
            name, typ = item.rsplit(":", 1)
        else:
            name, typ = item, "改造"
        out.append({"name": name.strip(), "type": typ.strip()})
    return out


def parse_template_map(s):
    """解析 --template-map: "参数管理中心后台=参数后台,集中清算=集中清算" → dict"""
    out = {}
    if not s:
        return out
    for item in s.split(","):
        item = item.strip()
        if not item:
            continue
        if "=" in item:
            k, v = item.split("=", 1)
            out[k.strip()] = v.strip()
    return out


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


async def read_submitter(page):
    """从需求要素板块读取需求提交人，返回 (姓名, 部门)"""
    txt = await page.evaluate("() => document.body.innerText")
    m = re.search(r"需求提交人\s*([一-龥A-Za-z]+)-([一-龥A-Za-z]+)", txt)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return "", ""


async def read_submitter_id(page, name):
    """从页面文本查找需求提交人编号（如 徐德亮-113622 → 113622）"""
    txt = await page.evaluate("() => document.body.innerText")
    matches = re.findall(rf"{re.escape(name)}-(\d+)", txt)
    if matches:
        # 取出现次数最多者，规避重复 ID 干扰
        from collections import Counter
        return Counter(matches).most_common(1)[0][0]
    return ""


async def read_existing_systems(page):
    """读取所属Story表格中已有 Story 的「所属系统」列表（兼容 antd Table）"""
    data = await page.evaluate("""() => {
        // antd Table 结构：.ant-table-thead th / .ant-table-tbody tr td
        const tables = [...document.querySelectorAll('.ant-table, table')];
        for (const tbl of tables) {
            const text = tbl.innerText || '';
            if (text.includes('Story编号') && text.includes('所属系统')) {
                const headers = [...tbl.querySelectorAll('.ant-table-thead th, thead th, thead td')]
                    .map(h => (h.innerText||'').trim());
                const sysIdx = headers.findIndex(h => h.includes('所属系统'));
                const rows = [...tbl.querySelectorAll('.ant-table-tbody tr, tbody tr')].map(tr =>
                    [...tr.querySelectorAll('td')].map(td => (td.innerText||'').trim()));
                return { headers, sysIdx, rows };
            }
        }
        return null;
    }""")
    systems = set()
    if data and data["sysIdx"] >= 0:
        for row in data["rows"]:
            if row and len(row) > data["sysIdx"] and row[data["sysIdx"]]:
                systems.add(row[data["sysIdx"]])
    return systems


async def scroll_to_story_section(page):
    """滚动到「所属Story」模块"""
    await page.evaluate("""() => {
        const all = [...document.querySelectorAll('*')];
        const el = all.find(e => e.children.length < 30 && e.innerText && e.innerText.includes('所属Story'));
        if (el) el.scrollIntoView({block: 'center'});
    }""")
    await page.wait_for_timeout(1500)


async def close_open_drawer(page):
    """关闭已打开的抽屉（若存在）"""
    drawer = page.locator('.ant-drawer-content').first
    if await drawer.count() > 0:
        try:
            await page.keyboard.press('Escape')
            await page.wait_for_timeout(800)
        except Exception:
            pass


async def open_new_story_drawer(page):
    """点击「新建Story」打开抽屉，返回 drawer"""
    btn = page.locator('button:has-text("新建Story")').first
    if await btn.count() == 0:
        print("  ❌ 未找到「新建Story」按钮")
        return None
    await btn.scroll_into_view_if_needed()
    await btn.click()
    await SESSION.wait_for_condition(
        page, "() => !!document.querySelector('.ant-drawer-content')",
        timeout=10000, desc="新建Story抽屉出现")
    drawer = page.locator('.ant-drawer-content').first
    return drawer


async def apply_template(page, drawer, template_name):
    """点击「使用模板」并选择模板，返回是否成功"""
    tmpl = page.locator('.ant-drawer button:has-text("使用模板")').first
    if await tmpl.count() == 0:
        print(f"  ⚠️ 未找到「使用模板」按钮（{template_name}）")
        return False
    await tmpl.click()
    await SESSION.wait_for_condition(
        page, "() => !!document.querySelector('.ant-dropdown:visible')",
        timeout=8000, desc="模板下拉出现")
    opt = page.locator(f'.ant-dropdown:visible >> text="{template_name}"').first
    if await opt.count() == 0:
        print(f"  ⚠️ 模板下拉中未找到「{template_name}」")
        await page.keyboard.press('Escape')
        await page.wait_for_timeout(500)
        return False
    await opt.click()
    # 条件等待：抽屉内「所属系统」select 回显模板系统名
    await SESSION.wait_for_condition(
        page, "() => { const d = document.querySelector('.ant-drawer-content'); if (!d) return false;"
              " const items = [...d.querySelectorAll('.ant-form-item')];"
              " const it = items.find(x => (x.innerText||'').includes('所属系统'));"
              " return it && (it.innerText||'').includes('请选择') === false; }",
        timeout=8000, desc="模板字段填充")
    return True


async def get_drawer_field_value(drawer, label):
    """读取抽屉内指定 label 表单项的当前值"""
    items = drawer.locator('.ant-form-item')
    for i in range(await items.count()):
        it = items.nth(i)
        if label in (await it.inner_text()):
            sel = it.locator('.ant-select').first
            if await sel.count() > 0:
                return (await sel.inner_text()).strip()
            inp = it.locator('input').first
            if await inp.count() > 0:
                return await inp.input_value()
            return (await it.inner_text()).strip()
    return ""


async def set_antd_select(page, drawer, label, value):
    """点击 label 对应的 ant-select 并选择指定选项，返回是否生效"""
    items = drawer.locator('.ant-form-item')
    for i in range(await items.count()):
        it = items.nth(i)
        if label not in (await it.inner_text()):
            continue
        sel = it.locator('.ant-select').first
        if await sel.count() == 0:
            print(f"  ⚠️ 「{label}」无下拉控件")
            return False
        await sel.click()
        await page.wait_for_timeout(1000)
        opt = page.locator(f'.ant-select-dropdown:visible [class*="option"]:has-text("{value}")').first
        if await opt.count() == 0:
            opt = page.locator(f'.ant-select-dropdown:visible >> text="{value}"').first
        if await opt.count() > 0:
            await opt.click()
            await page.wait_for_timeout(800)
            cur = (await sel.inner_text()).strip()
            # 校验：目标为「是」时需含「是」且不含「否」；目标为「否」时需含「否」
            if value == "是":
                ok = ("是" in cur) and ("否" not in cur)
            else:
                ok = (value in cur)
            if ok:
                return True
            print(f"  ⚠️ 「{label}」选择「{value}」未生效（当前: {cur}），重试...")
        else:
            print(f"  ⚠️ 「{label}」下拉中未找到选项「{value}」")
        await page.keyboard.press('Escape')
        await page.wait_for_timeout(500)
        return False
    print(f"  ⚠️ 未找到表单项「{label}」")
    return False


async def set_biz_acceptor(page, drawer, name, person_id):
    """选择业务验收人：搜索姓名，选 {name}-{person_id} 选项；若已预设该人则跳过"""
    items = drawer.locator('.ant-form-item')
    for i in range(await items.count()):
        it = items.nth(i)
        if "业务验收人" not in (await it.inner_text()):
            continue
        sel = it.locator('.ant-select').first
        if await sel.count() == 0:
            return False
        # 若当前已选中目标人（模板预设），直接跳过
        cur_val = (await sel.inner_text()).strip()
        target = f"{name}-{person_id}" if person_id else name
        if target in cur_val:
            print(f"  业务验收人 → 已预设 {cur_val}（跳过）")
            return True
        await sel.click()
        await page.wait_for_timeout(1000)
        search = it.locator('.ant-select-selection-search-input').first
        if await search.count() > 0:
            await search.fill(name)
            await page.wait_for_timeout(1200)
        opt = page.locator(f'.ant-select-dropdown:visible [class*="option"]:has-text("{target}")').first
        if await opt.count() == 0:
            opt = page.locator(f'.ant-select-dropdown:visible >> text="{target}"').first
        if await opt.count() > 0:
            # 若选项已处于选中态（模板预设/已选），无需点击
            aria_sel = await opt.get_attribute("aria-selected")
            if aria_sel == "true":
                await page.keyboard.press('Escape')
                await page.wait_for_timeout(500)
                print(f"  业务验收人 → 已选中 {target}（跳过）")
                return True
            await opt.click()
            await page.wait_for_timeout(800)
            cur = (await sel.inner_text()).strip()
            print(f"  业务验收人 → {cur}")
            return target in cur
        print(f"  ⚠️ 业务验收人下拉未找到「{target}」")
        await page.keyboard.press('Escape')
        await page.wait_for_timeout(500)
        return False
    return False


async def set_story_name(drawer, name):
    """填写 Story 名称"""
    inp = drawer.locator('#summary, input[placeholder="请输入Story名称"]').first
    if await inp.count() == 0:
        print("  ⚠️ 未找到 Story名称 输入框")
        return False
    await inp.fill(name)
    return True


async def copy_parent_desc(page, drawer):
    """点击「复制父需求描述」"""
    btn = drawer.locator('button:has-text("复制父需求描述")').first
    if await btn.count() == 0:
        print("  ⚠️ 未找到「复制父需求描述」")
        return False
    await btn.click()
    await page.wait_for_timeout(1500)
    return True


async def submit_story(page, dry_run=False):
    """点击「提 交」"""
    if dry_run:
        print("  [dry-run] 跳过提交")
        return True
    for sel in ['button:has-text("提 交")', 'button:has-text("提交")',
                'button:has-text("确认")', 'button:has-text("确定")']:
        b = page.locator(f'.ant-drawer {sel}').first
        if await b.count() == 0:
            b = page.locator(sel).first
        if await b.count() > 0:
            await b.click()
            await SESSION.wait_for_condition(
                page, "() => !!document.querySelector('.ant-message-success') || !document.querySelector('.ant-drawer-content')",
                timeout=8000, desc="Story提交成功")
            print("  ✅ 已点击提交")
            return True
    print("  ⚠️ 未找到提交按钮")
    return False


async def _story_row_checkbox_state(page, idx):
    """读取指定行索引复选框的勾选状态"""
    return await page.evaluate(f"""() => {{
        const tbls = [...document.querySelectorAll('.ant-table, table')];
        for (const tbl of tbls) {{
            const text = tbl.innerText || '';
            if (text.includes('Story编号') && text.includes('所属系统')) {{
                const tr = tbl.querySelectorAll('.ant-table-tbody tr, tbody tr')[{idx}];
                const cb = tr ? tr.querySelector('input[type=checkbox], .ant-checkbox-input') : null;
                return cb ? cb.checked : false;
            }}
        }}
        return false;
    }}""")


async def _story_row_click_checkbox(page, idx):
    """点击指定行复选框"""
    await page.evaluate(f"""() => {{
        const tbls = [...document.querySelectorAll('.ant-table, table')];
        for (const tbl of tbls) {{
            const text = tbl.innerText || '';
            if (text.includes('Story编号') && text.includes('所属系统')) {{
                const tr = tbl.querySelectorAll('.ant-table-tbody tr, tbody tr')[{idx}];
                const cb = tr ? tr.querySelector('input[type=checkbox], .ant-checkbox-input') : null;
                if (cb && !cb.checked) cb.click();
            }}
        }}
    }}""")


async def select_green_dot_stories(page):
    """勾选 Story名称列为绿色点（未发起技术评估）的所有 Story（逐行勾选+校验+重试），返回实际勾选数量"""
    await scroll_to_story_section(page)
    # 识别所有绿色点（未发起评估）的 Story 行索引
    rows = await page.evaluate("""() => {
        const tbls = [...document.querySelectorAll('.ant-table, table')];
        for (const tbl of tbls) {
            const text = tbl.innerText || '';
            if (text.includes('Story编号') && text.includes('所属系统')) {
                const headers = [...tbl.querySelectorAll('.ant-table-thead th, thead th, thead td')]
                    .map(h => (h.innerText||'').trim());
                const nameIdx = headers.findIndex(h => h.includes('Story名称'));
                return [...tbl.querySelectorAll('.ant-table-tbody tr, tbody tr')].map((tr, i) => {
                    const cells = [...tr.querySelectorAll('td')];
                    const nameCell = cells[nameIdx];
                    const cb = tr.querySelector('input[type=checkbox], .ant-checkbox-input');
                    return { idx: i, green: !!(nameCell && nameCell.querySelector('.ant-badge-status-success')), hasCb: !!cb };
                });
            }
        }
        return [];
    }""")
    green_rows = [r for r in rows if r["green"] and r["hasCb"]]
    print(f"识别到 {len(green_rows)} 个未发起技术评估的 Story")
    selected = 0
    for r in green_rows:
        # 逐行勾选 + 校验，避免 React 重渲染导致后续点击失效
        for attempt in range(3):
            await _story_row_click_checkbox(page, r["idx"])
            await page.wait_for_timeout(500)
            if await _story_row_checkbox_state(page, r["idx"]):
                selected += 1
                break
        else:
            print(f"  ⚠️ 第 {r['idx']} 行复选框勾选失败")
    print(f"实际勾选 {selected} 个")
    return selected


async def initiate_assessment(page, dry_run=False):
    """勾选未发起技术评估（绿点）的 Story 并点击「发起技术评估」"""
    await scroll_to_story_section(page)
    selected = await select_green_dot_stories(page)
    await page.wait_for_timeout(1500)
    print(f"已勾选 {selected} 个未发起技术评估的 Story")
    if selected == 0:
        print("没有需要发起技术评估的 Story（全部已评估或无绿点）")
        return False
    if dry_run:
        print("[dry-run] 跳过点击「发起技术评估」")
        return True
    btn = page.locator('button:has-text("发起技术评估")').first
    if await btn.count() == 0:
        print("⚠️ 未找到「发起技术评估」按钮")
        return False
    await btn.click()
    await SESSION.wait_for_condition(
        page, "() => !!document.querySelector('.ant-modal-content') || "
              "!!document.querySelector('.ant-message-success')",
        timeout=8000, desc="发起技术评估弹窗/成功提示")
    # 处理可能出现的确认弹窗
    modal = page.locator('.ant-modal-content:visible').first
    if await modal.count() > 0:
        mtxt = (await modal.inner_text())[:500]
        print(f"出现弹窗: {mtxt}")
        for sel in ['button:has-text("确 定")', 'button:has-text("确定")',
                    'button:has-text("确 认")', 'button:has-text("确认")',
                    'button:has-text("提 交")', 'button:has-text("提交")',
                    'button:has-text("保 存")', 'button:has-text("保存")']:
            b = page.locator(f'.ant-modal {sel}').first
            if await b.count() > 0:
                await b.click()
                await SESSION.wait_for_condition(
                    page, "() => !document.querySelector('.ant-modal-content')",
                    timeout=8000, desc="评估确认弹窗关闭")
                print(f"✅ 已点击弹窗确认按钮: {sel}")
                return True
    print("✅ 已点击「发起技术评估」")
    return True


async def _scroll_to_demand_info(page):
    """滚动到「需求要素」板块"""
    await page.evaluate("""() => {
        const all = [...document.querySelectorAll('*')];
        const el = all.find(e => e.children.length < 8 && e.innerText && e.innerText.trim() === '需求要素');
        if (el) el.scrollIntoView({block: 'center'});
    }""")
    await page.wait_for_timeout(1200)


async def _click_tag_add(page):
    """在需求自定义标签值单元格点击添加按钮（加号/添加），返回是否成功"""
    return await page.evaluate("""() => {
        const all = [...document.querySelectorAll('*')];
        const el = all.find(e => e.children.length < 8 && e.innerText && e.innerText.trim() === '需求自定义标签');
        if (!el) return false;
        const row = el.closest('tr');
        if (!row) return false;
        const cell = row.querySelector('td.ant-descriptions-item-content');
        if (!cell) return false;
        // 优先点加号图标，其次点 button/a
        const plus = cell.querySelector('.anticon-plus, .anticon-plus-circle, [class*="add"] , [class*="Add"]');
        if (plus) { plus.click(); return true; }
        const btn = cell.querySelector('button, a');
        if (btn) { btn.click(); return true; }
        return false;
    }""")


async def read_demand_project(page):
    """读取需求要素板块「公司信息技术项目」"""
    txt = await page.evaluate("() => document.body.innerText")
    m = re.search(r"公司信息技术项目\s*\n?\s*([^\n\t]+)", txt)
    return m.group(1).strip() if m else ""


async def _read_existing_tags(page):
    """读取需求自定义标签单元格中已有的标签集合（ant-tag 文本）"""
    return set(await page.evaluate("""() => {
        const all = [...document.querySelectorAll('*')];
        const el = all.find(e => e.children.length < 8 && e.innerText && e.innerText.trim() === '需求自定义标签');
        if (!el) return [];
        const row = el.closest('tr');
        const cell = row ? row.querySelector('td.ant-descriptions-item-content') : null;
        if (!cell) return [];
        return [...cell.querySelectorAll('.ant-tag')].map(t => t.innerText.trim()).filter(Boolean);
    }"""))


async def set_custom_tags(page, tags, dry_run=False):
    """在需求要素板块填写需求自定义标签（多个标签逐个添加）

    tags: 逗号分隔的标签，如 "CX-使能B,CX-业务"
    规则：公司信息技术项目为「道合大宗平台(P26196)」时自动补充 CX-道合大宗
    """
    await _scroll_to_demand_info(page)
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]

    # 自动识别：公司信息技术项目 = 道合大宗平台 → 补充 CX-道合大宗
    project = await read_demand_project(page)
    print(f"公司信息技术项目: {project if project else '（未读取到）'}")
    if ("道合大宗" in project) or ("P26196" in project):
        if "CX-道合大宗" not in tag_list:
            tag_list.insert(0, "CX-道合大宗")
            print("  自动补充标签: CX-道合大宗（公司信息技术项目=道合大宗平台）")

    # 读取当前已有标签，跳过已存在的（避免重复添加）
    existing = await _read_existing_tags(page)
    if existing:
        skipped = [t for t in tag_list if t in existing]
        if skipped:
            print(f"  跳过已有标签: {skipped}")
        tag_list = [t for t in tag_list if t not in existing]
    if not tag_list:
        print("  所有标签均已存在，无需添加")
        return
    print(f"待填写需求自定义标签: {tag_list}")
    for i, tag in enumerate(tag_list):
        # 确保上一个弹窗已完全关闭，避免定位到残留弹窗
        await _ensure_modal_closed(page)
        ok = await _click_tag_add(page)
        if not ok:
            print(f"  ⚠️ 未找到标签添加按钮（第{i+1}个「{tag}」）")
            break
        # 等待新弹窗出现（替代固定 1500ms）
        modal = page.locator('.ant-modal-content:visible').first
        try:
            await modal.wait_for(state="visible", timeout=6000)
        except Exception:
            print(f"  ⚠️ 未弹出标签输入弹窗（第{i+1}个「{tag}」）")
            break
        await page.wait_for_timeout(400)
        inp = modal.locator('input').first
        if await inp.count() == 0:
            print(f"  ⚠️ 标签弹窗无输入框（第{i+1}个「{tag}」）")
            await page.keyboard.press('Escape')
            await page.wait_for_timeout(500)
            break
        await inp.fill(tag)
        # 校验输入已生效（React 受控组件偶发 fill 不触发）
        val = await inp.input_value()
        if val.strip() != tag:
            await inp.click()
            await inp.press("Control+A")
            await inp.type(tag)
            await page.wait_for_timeout(300)
        if dry_run:
            print(f"  [dry-run] 标签「{tag}」已填写未保存")
            await page.keyboard.press('Escape')
            await page.wait_for_timeout(500)
            continue
        ok_btn = modal.locator('button:has-text("OK"), button:has-text("确 定"), button:has-text("确定")').first
        if await ok_btn.count() > 0:
            await ok_btn.click()
            # 等待弹窗关闭（落库完成），再处理下一个标签
            await _ensure_modal_closed(page, timeout=6000)
            print(f"  ✅ 已添加标签「{tag}」")
        else:
            print(f"  ⚠️ 未找到标签确认按钮（第{i+1}个「{tag}」）")
            break


async def _ensure_modal_closed(page, timeout=4000):
    """等待所有 .ant-modal 弹窗关闭（或不存在），避免残留弹窗干扰下一步"""
    try:
        await page.wait_for_function(
            "() => ![...document.querySelectorAll('.ant-modal-wrap')].some(w => w.style.display !== 'none' && w.offsetParent !== null)",
            timeout=timeout)
    except Exception:
        # 兜底：按 Esc 关闭可能残留的弹窗
        try:
            await page.keyboard.press('Escape')
            await page.wait_for_timeout(400)
        except Exception:
            pass
    await page.wait_for_timeout(300)


async def _scroll_to_ndw(page):
    """滚动到「非开发工作」模块"""
    await page.evaluate("""() => {
        const all = [...document.querySelectorAll('*')];
        const el = all.find(e => e.children.length < 30 && e.innerText && e.innerText.includes('非开发工作'));
        if (el) el.scrollIntoView({block: 'center'});
    }""")
    await page.wait_for_timeout(1200)


async def _read_first_story_info(page):
    """读取第一个 Story 的所属系统及 Story 总数（API 替代 DOM）"""
    info = get_demand_info_api(_CURRENT_REQ_ID)
    first_system = (info.get("storySystem") or "").split(",")[0].strip()
    try:
        data = SESSION.api_get("/demand-service/demandsub/queryStoryDemand",
                               {"current": 1, "demandId": _CURRENT_REQ_ID, "pageSize": 9999})
        count = len((data or {}).get("voList", []))
        if (data or {}).get("voList"):
            first_system = (data["voList"][0].get("systemName") or first_system).strip()
    except Exception:
        count = 0
    return first_system, count


async def _read_demand_title(page):
    """读取需求标题（API 替代 DOM）"""
    info = get_demand_info_api(_CURRENT_REQ_ID)
    return (info.get("summary") or "").strip()


async def _modal_fill_input(page, modal, label, value):
    """在弹窗中按 label 填写 input"""
    items = modal.locator('.ant-form-item')
    for i in range(await items.count()):
        it = items.nth(i)
        if label in (await it.inner_text()):
            inp = it.locator('input').first
            if await inp.count() > 0:
                await inp.fill(value)
                await page.wait_for_timeout(300)
                return True
    print(f"  ⚠️ 未找到输入框「{label}」")
    return False


async def _modal_select(page, modal, label, value):
    """在弹窗中按 label 选择 ant-select 选项（支持搜索）"""
    items = modal.locator('.ant-form-item')
    for i in range(await items.count()):
        it = items.nth(i)
        if label not in (await it.inner_text()):
            continue
        sel = it.locator('.ant-select').first
        if await sel.count() == 0:
            print(f"  ⚠️ 「{label}」无下拉控件")
            return False
        await sel.click()
        await page.wait_for_timeout(1000)
        # 仅当搜索输入框可编辑时才输入搜索（readonly 下拉不可搜索）
        search_inp = it.locator('.ant-select-selection-search-input, input').first
        if await search_inp.count() > 0:
            is_editable = await search_inp.evaluate("el => !el.readOnly && el.type !== 'hidden'")
            if is_editable:
                await search_inp.fill(value)
                await page.wait_for_timeout(1200)
        opt = page.locator(f'.ant-select-dropdown:visible [class*="option"]:has-text("{value}")').first
        if await opt.count() == 0:
            opt = page.locator(f'.ant-select-dropdown:visible >> text="{value}"').first
        if await opt.count() > 0:
            await opt.click()
            await page.wait_for_timeout(800)
            cur = (await sel.inner_text()).strip().replace("\n", " ")
            print(f"  {label} → {cur}")
            return value in cur
        print(f"  ⚠️ 下拉未找到「{label}={value}」")
        await page.keyboard.press('Escape')
        await page.wait_for_timeout(500)
        return False
    print(f"  ⚠️ 未找到表单项「{label}」")
    return False


async def register_non_dev_work(page, req_id, value, dry_run=False):
    """登记非开发工作量（需求分析类）"""
    await _scroll_to_ndw(page)
    first_system, story_count = await _read_first_story_info(page)
    title = await _read_demand_title(page)
    is_cross = story_count > 1
    name = f"【跨系统】{title}" if is_cross else title
    print(f"非开发工作名称: {name}")
    print(f"非开发工作类别: 需求分析")
    print(f"所属系统: {first_system}（第一个Story，共{story_count}个Story）")
    print(f"关联需求: {req_id}")
    print(f"申请价值量: {value}")

    btn = page.locator('button:has-text("新增非开发工作")').first
    if await btn.count() == 0:
        print("❌ 未找到「新增非开发工作」按钮")
        return False
    await btn.scroll_into_view_if_needed()
    await btn.click()
    await SESSION.wait_for_condition(
        page, "() => !!document.querySelector('.ant-modal-content')",
        timeout=10000, desc="新增非开发工作弹窗出现")
    modal = page.locator('.ant-modal-content:visible').first
    if await modal.count() == 0:
        print("❌ 未弹出新增非开发工作弹窗")
        return False

    # 填写字段（经办人/评估人/状态/开始/完成时间 保持默认）
    await _modal_fill_input(page, modal, "非开发工作名称", name)
    await _modal_select(page, modal, "非开发工作类别", "需求分析")
    await _modal_select(page, modal, "所属系统", first_system)
    await _modal_select(page, modal, "关联需求", req_id)
    await _modal_fill_input(page, modal, "申请价值量", value)

    if dry_run:
        print("[dry-run] 跳过确认提交")
        await page.keyboard.press('Escape')
        await page.wait_for_timeout(500)
        return True

    ok_btn = modal.locator('button:has-text("确 认"), button:has-text("确认")').first
    if await ok_btn.count() > 0:
        await ok_btn.click()
        await SESSION.wait_for_condition(
            page, "() => !!document.querySelector('.ant-message-success') || !document.querySelector('.ant-modal-content')",
            timeout=8000, desc="非开发工作登记成功")
        print("✅ 已点击确认，非开发工作登记完成")
        return True
    print("⚠️ 未找到确认按钮")
    return False


async def main():
    global _CURRENT_REQ_ID
    parser = argparse.ArgumentParser(description="科技平台需求 Story 自动拆分")
    parser.add_argument("req_id", help="需求编号，如 R2608100032")
    parser.add_argument("--systems", required=False, help="逗号分隔 系统名:类型(改造|配合测试)")
    parser.add_argument("--template-map", default="", help="逗号分隔 系统名=模板名")
    parser.add_argument("--impact-grayscale", choices=["是", "否"], default="否", help="是否影响灰度升级")
    parser.add_argument("--need-biz-accept", default="auto", help="auto|是|否")
    parser.add_argument("--biz-acceptor", default="auto", help="auto|姓名")
    parser.add_argument("--assess", action="store_true", help="拆分后发起技术评估（勾选绿点 Story）")
    parser.add_argument("--assess-only", action="store_true", help="仅发起技术评估，不拆分 Story")
    parser.add_argument("--tags", default="", help="需求自定义标签，逗号分隔（如 CX-使能B,CX-业务）")
    parser.add_argument("--ndw", default="", help="登记非开发工作量（需求分析），值为申请价值量，如 0.3")
    parser.add_argument("--ndw-system", default="", help="NDW 所属系统名（默认按需求 storySystem 主系统推断）")
    parser.add_argument("--dry-run", action="store_true", help="只填写不提交")
    parser.add_argument("--browser", action="store_true",
                        help="强制 Playwright 兜底（默认 API 优先：Story/NDW 直调 REST，≤1s）")
    args = parser.parse_args()

    if not args.assess_only and not args.systems and not args.tags and not args.ndw:
        parser.error("--systems / --assess-only / --tags / --ndw 至少提供其一")

    # ---------- API 快速路径（默认）：Story 拆分 + 非开发工作量 ----------
    # 注：--assess / --assess-only / --tags 暂无可验证的保存 API，仍走浏览器。
    if not args.browser and (args.systems or args.ndw) and not (args.assess or args.assess_only or args.tags):
        import platform_api
        _CURRENT_REQ_ID = args.req_id
        systems = parse_systems(args.systems) if args.systems else []
        tpl_map = parse_template_map(args.template_map)
        info = platform_api.get_demand_info(args.req_id)
        submitter, dept = info.get("userName", ""), info.get("deptName", "")
        submitter_id = info.get("userId", "")
        need_biz = "是" if dept != "技术研发部" else "否"
        biz_acceptor = args.biz_acceptor if args.biz_acceptor != "auto" else submitter
        existing = platform_api.get_stories(args.req_id)
        existing_systems = {(s.get("systemName") or "").strip() for s in existing if s.get("systemName")}
        print(f"[api] 需求提交人: {submitter}（{dept}）需要业务验收: {need_biz}")
        t0 = __import__("time").time()
        ok_count = 0
        for idx, sys_item in enumerate(systems):
            sys_name, sys_type = sys_item["name"], sys_item["type"]
            if sys_name in existing_systems:
                print(f"[api] ⏭ 系统「{sys_name}」已有 Story，跳过")
                continue
            template = platform_api.get_template_by_system(platform_api.list_templates(), tpl_map.get(sys_name, sys_name))
            if not template:
                print(f"[api] ⚠️ 系统「{sys_name}」无模板，跳过（需人工/浏览器拆分）")
                continue
            res = platform_api.save_story(
                args.req_id, sys_name, story_type=sys_type, template=template,
                impact_grayscale=args.impact_grayscale, need_biz_accept=need_biz,
                biz_acceptor=biz_acceptor, dry_run=args.dry_run)
            if args.dry_run:
                print(f"[api] [dry-run] {sys_name}（{sys_type}）payload 如下：")
                print("  " + json.dumps(res.get("payload"), ensure_ascii=False)[:400])
                ok_count += 1
                continue
            print(f"[api] ✅ {sys_name}（{sys_type}）Story 已创建")
            ok_count += 1
        if args.ndw:
            res = platform_api.add_non_dev_work(args.req_id, float(args.ndw),
                                                system_name=args.ndw_system or None,
                                                dry_run=args.dry_run)
            print(f"[api] NDW: {json.dumps(res, ensure_ascii=False)}")
            if res.get("skipped"):
                print(f"[api] ⏭ 非开发工作量已存在（id={res.get('existingId')}），跳过")
            elif args.dry_run:
                print("[api] [dry-run] NDW 未提交")
            else:
                print("[api] ✅ 非开发工作量登记成功")
        print(f"[api] 完成，耗时 {__import__('time').time()-t0:.1f}s")
        return

    _CURRENT_REQ_ID = args.req_id
    demand_url = f"{config.get_base_url()}/DemandManage/details?demandId={args.req_id}"
    systems = parse_systems(args.systems) if args.systems else []
    tpl_map = parse_template_map(args.template_map)

    page, ctx, pw = await SESSION.open_page_async()
    try:
        print(f"打开需求详情: {args.req_id}")
        await page.goto(demand_url, wait_until="domcontentloaded", timeout=40000)
        await wait_demand_loaded(page)

        # 仅后置操作模式：发起技术评估 / 需求自定义标签 / 非开发工作量
        if args.assess_only or (not args.systems and (args.tags or args.ndw)):
            if args.assess_only:
                await initiate_assessment(page, args.dry_run)
            if args.tags:
                await set_custom_tags(page, args.tags, args.dry_run)
            if args.ndw:
                await register_non_dev_work(page, args.req_id, args.ndw, args.dry_run)
            print("\n完成。")
            return

        # 读取需求提交人（API，替代 DOM 抓取）
        info = get_demand_info_api(args.req_id)
        submitter = info.get("userName", "")
        dept = info.get("deptName", "")
        submitter_id = info.get("userId", "")
        print(f"需求提交人: {submitter}（{dept}）[API]")
        if not submitter:
            print("❌ 未读取到需求提交人")
            return
        print(f"需求提交人编号: {submitter_id}")

        # 是否需要业务验收
        if args.need_biz_accept == "auto":
            need_biz = "是" if dept != "技术研发部" else "否"
        else:
            need_biz = args.need_biz_accept
        print(f"是否需要业务验收: {need_biz}（部门规则: {'非技术研发部→是' if dept != '技术研发部' else '技术研发部→否'}）")

        # 业务验收人
        biz_acceptor = args.biz_acceptor if args.biz_acceptor != "auto" else submitter

        # 读取已有 Story 的所属系统（API，替代 DOM 抓取）
        existing = get_existing_story_systems_api(args.req_id)
        print(f"已有 Story 所属系统: {existing if existing else '（无）'}")

        # 逐系统拆分
        for idx, sys_item in enumerate(systems):
            sys_name = sys_item["name"]
            sys_type = sys_item["type"]
            template = tpl_map.get(sys_name, sys_name)
            print(f"\n===== [{idx+1}/{len(systems)}] {sys_name}（{sys_type}）模板=[{template}] =====")

            await close_open_drawer(page)
            drawer = await open_new_story_drawer(page)
            if not drawer:
                continue

            # 使用模板
            ok_tpl = await apply_template(page, drawer, template)
            if not ok_tpl:
                print(f"  ⚠️ 系统「{sys_name}」无匹配模板，跳过（需人工拆分）")
                await close_open_drawer(page)
                continue

            # 读取模板填充的所属系统，判断是否已有 Story
            sys_val = await get_drawer_field_value(drawer, "所属系统")
            print(f"  模板所属系统: {sys_val}")
            if sys_val and sys_val in existing:
                print(f"  ⏭ 系统「{sys_name}」已有 Story（所属系统={sys_val}），跳过")
                await close_open_drawer(page)
                continue

            # 字段1：是否影响灰度升级
            await set_antd_select(page, drawer, "是否影响灰度升级", args.impact_grayscale)
            print(f"  是否影响灰度升级 → {args.impact_grayscale}")

            # 字段2：是否需要业务验收
            await set_antd_select(page, drawer, "是否需要业务验收", need_biz)
            print(f"  是否需要业务验收 → {need_biz}")

            # 字段3：业务验收人
            if need_biz == "是":
                await set_biz_acceptor(page, drawer, biz_acceptor, submitter_id)
            else:
                print("  业务验收人 → 置空（无需业务验收）")

            # 复制父需求描述
            await copy_parent_desc(page, drawer)

            # Story 名称（配合测试加前缀）
            if sys_type == "配合测试":
                story_name = f"【配合测试】{await get_parent_name(page, drawer)}"
            else:
                story_name = await get_parent_name(page, drawer)
            await set_story_name(drawer, story_name)
            print(f"  Story名称 → {story_name}")

            # 提交
            await submit_story(page, args.dry_run)

        # 发起技术评估（勾选绿点 Story）
        if args.assess:
            await initiate_assessment(page, args.dry_run)

        # 填写需求自定义标签
        if args.tags:
            await set_custom_tags(page, args.tags, args.dry_run)

        # 登记非开发工作量
        if args.ndw:
            await register_non_dev_work(page, args.req_id, args.ndw, args.dry_run)
    finally:
        await SESSION.close_page(ctx, pw)

    print("\n完成。")


async def get_parent_name(page, drawer):
    """读取父需求名称（抽屉内只读字段）"""
    items = drawer.locator('.ant-form-item')
    for i in range(await items.count()):
        it = items.nth(i)
        if "父需求名称" in (await it.inner_text()):
            t = await it.inner_text()
            t = t.replace("父需求名称", "").strip()
            return t
    return ""


if __name__ == "__main__":
    asyncio.run(main())
