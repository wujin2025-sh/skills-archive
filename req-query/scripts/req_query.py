#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
req_query.py — 需求查询（极速版 v2.2）
============================================
访问国泰海通金融科技平台需求详情页，
支持 --no-story 参数（需求分析阶段专属），1-2 秒内毫秒级提取需求核心要素。
"""

import sys
import os
import re
import asyncio
import argparse
import json
from playwright.async_api import async_playwright

def decrypt_password(enc_str, key_path='~/.workbuddy/.meeting_skill_key'):
    """解密存储在代码中的加密密码"""
    if not enc_str or not isinstance(enc_str, str):
        return ""
    if not enc_str.startswith('ENC:'):
        return enc_str
    kp = os.path.expanduser(key_path)
    if not os.path.exists(kp):
        return enc_str
    try:
        from cryptography.fernet import Fernet
        with open(kp, 'rb') as f:
            key = f.read()
        fern = Fernet(key)
        return fern.decrypt(enc_str[4:].encode('utf-8')).decode('utf-8')
    except Exception:
        return enc_str

def load_credentials():
    username = os.environ.get("PLATFORM_USERNAME") or os.environ.get("FINTECH_USERNAME") or ""
    password = os.environ.get("PLATFORM_PASSWORD") or os.environ.get("FINTECH_PASSWORD") or ""
    platform_url = os.environ.get("PLATFORM_URL") or "https://fintech.gtht.com.cn"

    script_dir = os.path.dirname(os.path.abspath(__file__))
    skill_root = os.path.dirname(script_dir)

    config_paths = [
        os.path.join(os.getcwd(), "config.json"),
        os.path.join(skill_root, "config.json"),
        os.path.join(script_dir, "config.json"),
        "/Volumes/Macintosh HD_Data/WorkBuddy/需求管理/config.json",
        os.path.expanduser("~/.workbuddy/config.json"),
    ]

    for p in config_paths:
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    creds = json.load(f)
                    u = str(creds.get("username", "")).strip()
                    p_plain = str(creds.get("password", "")).strip()
                    p_enc = str(creds.get("password_encrypted", "")).strip()
                    url_val = str(creds.get("platform_url", "")).strip()

                    if url_val:
                        platform_url = url_val.rstrip("/")
                    if u and u not in ("YOUR_USERNAME", "你的工号") and not username:
                        username = u

                    if not password:
                        if p_plain and p_plain not in ("YOUR_PASSWORD", "YOUR_PLAIN_PASSWORD", "你的登录密码", "密码"):
                            password = p_plain
                        elif p_enc:
                            dec = decrypt_password(p_enc)
                            if dec:
                                password = dec
                if username and password:
                    break
            except Exception:
                pass

    if not username or not password:
        print("❌ [配置缺失错误] 未找到有效的科技平台登录凭据 (USERNAME / PASSWORD)", file=sys.stderr)

    return username, password, platform_url

USERNAME, PASSWORD, PLATFORM_URL = load_credentials()
LOGIN_URL = f"{PLATFORM_URL}/kjpt/user/login"
DETAIL_URL_TEMPL = f"{PLATFORM_URL}/kjpt/DemandManage/details?demandId={{}}&templateId=8888&flag=1"

WORKSPACE = "/Volumes/Macintosh HD_Data/WorkBuddy/需求管理"
SESSION_FILE = os.path.join(WORKSPACE, ".fintech_session.json")

STORY_HEADER_MAP = {
    "Story编号": "id",
    "Story名称": "name",
    "Story状态": "status",
    "所属系统": "system",
    "SIT测试负责人": "sit_owner",
    "UAT测试负责人": "uat_owner",
}

STORY_COL_FALLBACK = {
    "id": 1, "name": 2, "status": 4, "system": 5,
    "sit_owner": 14, "uat_owner": 15,
}

def _clean(s):
    if not s:
        return ""
    return re.sub(r"\s+", " ", str(s)).strip()

async def _do_login(page, context):
    await page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=30000)
    await page.wait_for_selector('input[placeholder*="工号"]', timeout=8000)
    await page.locator('input[placeholder*="工号"]').fill(USERNAME)
    await page.locator('input[placeholder*="密码"], input[type="password"]').fill(PASSWORD)
    submit_btn = page.locator('button.ant-btn-primary, button:has-text("Submit"), button:has-text("提 交"), button:has-text("登录")').first
    await submit_btn.click()
    await page.wait_for_load_state("domcontentloaded", timeout=30000)
    await asyncio.sleep(2)
    os.makedirs(os.path.dirname(SESSION_FILE), exist_ok=True)
    try:
        await context.storage_state(path=SESSION_FILE)
    except Exception:
        pass

async def ensure_login(context, page):
    if os.path.exists(SESSION_FILE):
        return
    await _do_login(page, context)

async def get_demand_details(page, demand_id, skip_stories=False, context=None):
    url = DETAIL_URL_TEMPL.format(demand_id)
    await page.goto(url, wait_until="domcontentloaded", timeout=15000)
    
    if "login" in page.url.lower():
        if os.path.exists(SESSION_FILE):
            try:
                os.remove(SESSION_FILE)
            except Exception:
                pass
        if context:
            await _do_login(page, context)
            await page.goto(url, wait_until="domcontentloaded", timeout=15000)
        if "login" in page.url.lower():
            return None, [], {}

    if not skip_stories:
        try:
            await page.wait_for_selector('.ant-table-tbody .ant-table-row', timeout=6000)
        except Exception:
            pass

    # 等待顶部卡片异步渲染
    await asyncio.sleep(0.8)

    data = await page.evaluate("""({demandId, skipStories}) => {
        const fullText = document.body.innerText || '';
        const lines = fullText.split('\\n').map(l => l.trim()).filter(Boolean);

        let title = '';
        const titleLine = lines.find(l => l.includes('【') && l.includes('】'));
        if (titleLine) {
            title = titleLine;
        } else {
            const idx = lines.findIndex(l => l.includes(demandId));
            if (idx > 0) title = lines[idx - 1];
        }

        let status = '', level = '', oaStatus = '';
        const tagLine = lines.find(l => l.includes(demandId) && (l.includes('|') || l.includes('OA')));
        if (tagLine) {
            const parts = tagLine.split('|').map(s => s.trim());
            if (parts.length >= 2) status = parts[0];
            if (parts.length >= 3) {
                level = parts[2].split('OA')[0].trim();
                if (parts[2].includes('OA')) {
                    oaStatus = 'OA' + parts[2].split('OA')[1].replace(/关注.*/, '').trim();
                }
            }
        }
        if (!oaStatus && fullText.includes('OA已提交')) oaStatus = 'OA已提交';

        function extractVal(label) {
            const idx = lines.findIndex(l => l.startsWith(label) || l === label);
            if (idx !== -1 && idx + 1 < lines.length) {
                return lines[idx + 1];
            }
            return '';
        }

        const requester = extractVal('需求提交人') || extractVal('提出人');
        const handler = extractVal('受理人');

        let stories = [];
        let colMap = {};

        if (!skipStories) {
            const tables = document.querySelectorAll('.ant-table');
            let storyTable = null;
            for (const t of tables) {
                if (t.textContent.includes('Story编号')) {
                    storyTable = t;
                    break;
                }
            }

            if (storyTable) {
                const headerCells = storyTable.querySelectorAll('.ant-table-thead th');
                Array.from(headerCells).forEach((th, idx) => {
                    const name = th.textContent?.trim() || '';
                    if (name) colMap[name] = idx;
                });

                const rows = storyTable.querySelectorAll('.ant-table-tbody .ant-table-row');
                stories = Array.from(rows).map(row => {
                    const cells = row.querySelectorAll('td');
                    return Array.from(cells).map(td => td.textContent?.trim() || '');
                });
            }
        }

        let rName = requester, rDept = '';
        if (requester.includes('-')) {
            rName = requester.split('-')[0].trim();
            rDept = requester.split('-')[1].trim();
        }

        let hName = handler;
        if (handler.includes('主')) hName = handler.replace(/主.*/, '').trim();
        if (hName.includes('-')) hName = hName.split('-')[0].trim();

        let background = '';
        let content = '';
        const bgMatch = fullText.match(/(?:一[、.．]\\s*需求背景)([\\s\\S]*?)(?=二[、.．]\\s*需求内容|$)/i);
        if (bgMatch) {
            background = bgMatch[1].trim();
        }
        const contentMatch = fullText.match(/(?:二[、.．]\\s*需求内容)([\\s\\S]*?)(?=三[、.．]\\s*技术实现|上传技术实现方案|需求内容补充|关联设计需求|附件|OA审批|$)/i);
        if (contentMatch) {
            content = contentMatch[1].trim();
        }

        let expDate = '';
        const labels = Array.from(document.querySelectorAll('*')).filter(el => el.children.length === 0 && el.textContent.includes('期望上线时间'));
        for (const lbl of labels) {
            const parentText = lbl.parentElement?.innerText || lbl.parentElement?.textContent || '';
            const labelPos = parentText.indexOf('期望上线时间');
            if (labelPos !== -1) {
                const subStr = parentText.substring(labelPos, labelPos + 100);
                const dm = subStr.match(/([0-9]{4}[-/][0-9]{2}[-/][0-9]{2})/);
                if (dm) {
                    expDate = dm[1];
                    break;
                }
            }
        }
        if (!expDate) {
            const m = fullText.match(/期望上线时间[\\s\\S]{1,50}?([0-9]{4}[-/][0-9]{2}[-/][0-9]{2})/);
            if (m) expDate = m[1];
        }
        if (!expDate) expDate = '未设定';

        const attachments = [];
        const attElements = document.querySelectorAll('.ant-upload-list-item, a[href*="download"], a[href*="attachment"], .attachment-name, .file-name');
        attElements.forEach(el => {
            const text = el.textContent?.trim() || '';
            const href = el.getAttribute('href') || el.querySelector('a')?.getAttribute('href') || '';
            if (text && text.length > 2 && !attachments.some(a => a.name === text)) {
                attachments.push({ name: text, href });
            }
        });

        let attachmentText = '';
        const attSecMatch = fullText.match(/(?:附件说明|附件列表|需求附件|附件文件)([\\s\\S]*?)(?=OA审批|关联设计需求|设计需求|评论|修改记录|$)/i);
        if (attSecMatch) {
            attachmentText = attSecMatch[1].trim();
        }

        return {
            info: {
                '编号': demandId,
                '标题': title,
                '级别': level || 'P4(普通需求)',
                '状态': status || '待受理',
                'OA状态': oaStatus || 'OA未提交',
                '提出人': rName,
                '提出部门': rDept,
                '受理人': hName,
                '期望上线时间': expDate,
                '需求背景': background,
                '需求内容': content,
                '附件列表': attachments,
                '附件说明文案': attachmentText
            },
            stories,
            colMap
        };
    }""", {"demandId": demand_id, "skipStories": skip_stories})

    return data.get("info"), (None if skip_stories else data.get("stories", [])), data.get("colMap", {})

def _build_col_index(col_map):
    result = {}
    for header_text, th_idx in col_map.items():
        field_name = None
        for key, val in STORY_HEADER_MAP.items():
            if key in header_text or header_text in key:
                field_name = val
                break
        if field_name:
            result[field_name] = th_idx
    return result

def format_demand(info, stories=None, col_map=None):
    if not info:
        return "**需求查询　|　未找到匹配结果**\n"

    plan_date = "2026-08-07"
    remark = "公司督办项"

    lines = []
    lines.append(f"### 需求基本信息 (`{info['编号']}`)")
    lines.append("")
    lines.append("| 属性 | 详细内容 |")
    lines.append("| :--- | :--- |")
    lines.append(f"| **需求编号** | `{info['编号']}` |")
    lines.append(f"| **需求标题** | {info['标题']} |")
    lines.append(f"| **级别** | {info['级别']} |")
    lines.append(f"| **状态** | {info['状态']} |")
    lines.append(f"| **OA状态** | {info['OA状态']} |")
    lines.append(f"| **提出人** | {info['提出人']}（{info['提出部门']}） |")
    lines.append(f"| **受理人** | {info['受理人']} |")
    lines.append(f"| **期望上线时间** | {info['期望上线时间']} |")
    lines.append(f"| **详情页链接** | [查看详情]({DETAIL_URL_TEMPL.format(info['编号'])}) |")
    lines.append("")

    if info.get('需求背景'):
        lines.append("#### **一、需求背景**")
        lines.append(info['需求背景'])
        lines.append("")
    if info.get('需求内容'):
        lines.append("#### **二、需求内容**")
        lines.append(info['需求内容'])
        lines.append("")

    atts = info.get('附件列表', [])
    att_text = info.get('附件说明文案', '')
    if atts or att_text:
        lines.append("#### **【附件列表与说明】**")
        if atts:
            lines.append("**需求挂载附件文件列表：**")
            for a in atts:
                link = f" ({a['href']})" if a.get('href') else ""
                lines.append(f"- 📎 `{a['name']}`{link}")
            lines.append("")
        if att_text:
            lines.append("**附件说明与提取文本：**")
            lines.append(att_text)
            lines.append("")

    if stories is not None:
        ci = _build_col_index(col_map) if col_map else STORY_COL_FALLBACK

        lines.append(f"### 关联 Story 列表（{len(stories)} 条）")
        lines.append("")
        if stories:
            lines.append("| # | Story 编号 | Story 名称 | 所属系统 | 状态 | SIT负责人 | UAT负责人 | 计划生产排期 | 备注 |")
            lines.append("| :-: | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |")

            for i, s in enumerate(stories, 1):
                def scol(name):
                    idx = ci.get(name)
                    if idx is not None and idx < len(s):
                        return _clean(s[idx])
                    return ""

                story_system = scol('system')

                lines.append(
                    f"| {i} | `{scol('id')}` | {scol('name')} | {story_system} | "
                    f"{scol('status')} | {scol('sit_owner')} | {scol('uat_owner')} | "
                    f"{plan_date} | {remark} |"
                )
            lines.append("")
        else:
            lines.append("*暂无关联 Story*")
            lines.append("")

    return "\n".join(lines)

async def run(demand_id, headed, output, skip_stories=False):
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=not headed,
            args=["--disable-blink-features=AutomationControlled"]
        )
        context = await browser.new_context(
            storage_state=SESSION_FILE if os.path.exists(SESSION_FILE) else None,
            viewport={"width": 1440, "height": 900},
            locale="zh-CN",
        )
        
        # 拦截静态文件，加速网络抓取
        await context.route(
            "**/*.{png,jpg,jpeg,gif,svg,woff,woff2,ttf,eot,ico}",
            lambda route: route.abort()
        )

        page1 = await context.new_page()

        await ensure_login(context, page1)
        info, stories, col_map = await get_demand_details(page1, demand_id, skip_stories=skip_stories, context=context)
        await page1.close()

        output_text = format_demand(info, stories, col_map)
        print("\n" + "=" * 60)
        print(output_text)
        print("=" * 60)

        if output:
            os.makedirs(os.path.dirname(os.path.abspath(output)), exist_ok=True)
            with open(output, "w", encoding="utf-8") as f:
                f.write(output_text)
                f.write("\n")

        await browser.close()

def main():
    parser = argparse.ArgumentParser(description="需求查询（极速版）")
    parser.add_argument("demand_id", help="需求编号（如 R2604090033）")
    parser.add_argument("--headed", action="store_true", help="显示浏览器窗口")
    parser.add_argument("--no-story", action="store_true", help="需求分析阶段跳过 Story 列表查询（极速秒切）")
    parser.add_argument("--output", "-o", help="输出文件路径")
    args = parser.parse_args()

    demand_id = args.demand_id.strip().upper()
    if not demand_id:
        print("错误：请输入需求编号")
        sys.exit(1)

    asyncio.run(run(demand_id, args.headed, args.output, skip_stories=args.no_story))

if __name__ == "__main__":
    main()
