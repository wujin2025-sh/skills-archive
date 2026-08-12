#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
create_epic.py — 史诗创建自动化脚本
============================================
根据需求号/需求URL自动创建史诗，参考 PG202204-0269 史诗参数，
史诗名称根据需求标题自动精炼提炼，计划周期为当日到2个月后。
"""

import sys
import os
import re
import json
import asyncio
import argparse
from datetime import datetime, date
from dateutil.relativedelta import relativedelta
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
EPIC_MANAGE_URL = f"{PLATFORM_URL}/kjpt/ProjectSetManage/Epic"
DEMAND_DETAIL_URL_TEMPL = f"{PLATFORM_URL}/kjpt/DemandManage/details?demandId={{}}&flag=1"

WORKSPACE = "/Volumes/Macintosh HD_Data/WorkBuddy/需求管理"
SESSION_FILE = os.path.join(WORKSPACE, ".fintech_session.json")

def parse_demand_ids(inputs):
    """提取输入字符串中的需求号 (R\\d{10})"""
    demand_ids = []
    for inp in inputs:
        matches = re.findall(r"R\d{10}", inp)
        for m in matches:
            if m not in demand_ids:
                demand_ids.append(m)
    return demand_ids

def refine_epic_name(titles):
    """从需求标题列表中自动提炼史诗名称"""
    cleaned = []
    for t in titles:
        c = re.sub(r"【业务需求】", "", t)
        c = re.sub(r"【两融清算】", "", c)
        c = re.sub(r"^集中营运", "", c)
        c = re.sub(r"[【】]", "", c)
        c = re.sub(r"需求$", "", c)
        c = c.strip()
        if c:
            cleaned.append(c)
    
    if not cleaned:
        return "新创史诗"
    
    if len(cleaned) == 1:
        return cleaned[0]
    
    s1 = cleaned[0]
    best = ""
    for i in range(len(s1)):
        for j in range(i + 3, len(s1) + 1):
            sub = s1[i:j]
            if all(sub in title for title in cleaned) and len(sub) > len(best):
                best = sub
    
    if best and len(best) >= 3:
        return best
    return cleaned[0]

async def ensure_login(context, page):
    if os.path.exists(SESSION_FILE):
        try:
            await page.goto(EPIC_MANAGE_URL, wait_until="domcontentloaded", timeout=15000)
            if "login" not in page.url.lower():
                return
        except Exception:
            pass

    print("登录中...")
    await page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=30000)
    await page.wait_for_selector('input[placeholder*="工号"]', timeout=8000)
    await page.locator('input[placeholder*="工号"]').fill(USERNAME)
    await page.locator('input[placeholder*="密码"]').fill(PASSWORD)
    await page.locator('button:has-text("提 交")').click()
    await page.wait_for_load_state("networkidle", timeout=30000)
    try:
        await context.storage_state(path=SESSION_FILE)
    except Exception:
        pass

async def fetch_demand_title(page, headers, demand_id):
    """查询需求标题与所属部门"""
    # 尝试通过 API 检索需求名称
    try:
        d_res = await page.evaluate("""async ({headers, dId}) => {
            const r = await fetch('/api/multi-project-collaboration-service/kjptProjectCollaborationEpic/getDemandsInfo', {
                method: 'POST',
                headers: headers,
                body: JSON.stringify({ searchKeyWords: dId })
            });
            return await r.json();
        }""", {"headers": headers, "dId": demand_id})

        recs = d_res.get("data", {}).get("records", [])
        if recs:
            rec = recs[0]
            if rec.get("summary"):
                return rec.get("summary"), rec.get("deptName", "")
    except Exception:
        pass

    # 兜底：直接访问需求详情页抓取标题
    try:
        url = DEMAND_DETAIL_URL_TEMPL.format(demand_id)
        await page.goto(url, wait_until="domcontentloaded", timeout=15000)
        try:
            await page.wait_for_function("() => document.body.innerText.includes('【') || document.body.innerText.includes('SIT')", timeout=5000)
        except Exception:
            pass
        await asyncio.sleep(0.5)

        title, dept = await page.evaluate("""(dId) => {
            const text = document.body.innerText || '';
            const lines = text.split('\\n').map(l => l.trim()).filter(Boolean);
            let t = '';
            const titleLine = lines.find(l => l.includes('【') && l.includes('】'));
            if (titleLine) {
                t = titleLine;
            } else {
                const idx = lines.findIndex(l => l.includes(dId));
                if (idx > 0 && lines[idx - 1].length > 3) t = lines[idx - 1];
            }
            let d = '';
            const deptIdx = lines.findIndex(l => l === '提出部门' || l === '需求提交人');
            if (deptIdx !== -1 && deptIdx + 1 < lines.length) {
                d = lines[deptIdx + 1];
            }
            return [t || dId, d];
        }""", demand_id)
        return title, dept
    except Exception:
        return demand_id, ""

async def create_epic_workflow(demand_inputs, ref_epic_code="PG202204-0269", custom_name=None, dry_run=False):
    demand_ids = parse_demand_ids(demand_inputs)
    if not demand_ids:
        print("错误: 未检测到有效的需求编号(格式如 R2604130077)！")
        return None

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        storage_path = SESSION_FILE if os.path.exists(SESSION_FILE) else None
        context = await browser.new_context(storage_state=storage_path)
        page = await context.new_page()

        headers_captured = {}
        def handle_request(req):
            if "api/" in req.url:
                for k, v in req.headers.items():
                    headers_captured[k] = v
        page.on("request", handle_request)

        await ensure_login(context, page)
        await page.goto(EPIC_MANAGE_URL, wait_until="networkidle", timeout=30000)
        await asyncio.sleep(2)

        for _ in range(10):
            if "token" in headers_captured:
                break
            await asyncio.sleep(0.5)

        # 1. 查询参考史诗要素 (PG202204-0269)
        ref_epic_info = {
            "projectCollaborationId": "2fb5a5e08cb44d4eb0",
            "projectCollaborationName": "大新一代需求史诗集合",
            "label": "CX-两融",
            "depNames": "融资融券部",
            "status": "0",
            "type": "0"
        }

        try:
            ref_res = await page.evaluate("""async ({headers, refCode}) => {
                const r = await fetch('/api/multi-project-collaboration-service/kjptProjectCollaborationEpic/listAllByExamples', {
                    method: 'POST',
                    headers: headers,
                    body: JSON.stringify({
                        type: "0", myPutForward: "0", current: 1, size: 20, status: "0", searchKeyWords: refCode
                    })
                });
                return await r.json();
            }""", {"headers": headers_captured, "refCode": ref_epic_code})

            records = ref_res.get("data", {}).get("records", [])
            if records:
                r_obj = records[0]
                ref_epic_info["projectCollaborationId"] = r_obj.get("projectCollaborationId", ref_epic_info["projectCollaborationId"])
                ref_epic_info["projectCollaborationName"] = r_obj.get("projectCollaborationName", ref_epic_info["projectCollaborationName"])
                raw_label = r_obj.get("label", ref_epic_info["label"])
                ref_epic_info["label"] = raw_label.strip() if raw_label else "CX-两融"
                ref_epic_info["depNames"] = r_obj.get("depNames", ref_epic_info["depNames"])
                print(f"成功获取参考史诗 [{ref_epic_code}] 要素:")
                print(f"  - 所属工程集: {ref_epic_info['projectCollaborationName']} ({ref_epic_info['projectCollaborationId']})")
                print(f"  - 标签: {ref_epic_info['label']}")
                print(f"  - 提出部门: {ref_epic_info['depNames']}")
        except Exception as e:
            print(f"获取参考史诗失败，将使用默认标准参数: {e}")

        # 2. 获取需求标题与所属部门
        demand_details = []
        titles = []
        for d_id in demand_ids:
            title, dept = await fetch_demand_title(page, headers_captured, d_id)
            demand_details.append({"id": d_id, "title": title, "dept": dept})
            titles.append(title)

        epic_name = custom_name if custom_name else refine_epic_name(titles)

        # 3. 计算计划周期 (当日 到 2个月后)
        today = date.today()
        end_date = today + relativedelta(months=2)
        start_time_str = today.strftime("%Y-%m-%d")
        end_time_str = end_date.strftime("%Y-%m-%d")

        print(f"\n--- 拟创建史诗预览 ---")
        print(f"史诗名称: {epic_name}")
        print(f"参考史诗: {ref_epic_code}")
        print(f"计划周期: {start_time_str} 至 {end_time_str}")
        print(f"所属工程集: {ref_epic_info['projectCollaborationName']}")
        print(f"史诗标签: {ref_epic_info['label']}")
        print(f"关联需求 ({len(demand_ids)}笔):")
        for dd in demand_details:
            print(f"  - [{dd['id']}] {dd['title']}")

        if dry_run:
            print("\n[Dry-Run 试运行模式] 未进行实际提交。")
            await browser.close()
            return {
                "epic_name": epic_name,
                "start_time": start_time_str,
                "end_time": end_time_str,
                "demand_ids": demand_ids,
                "dry_run": True
            }

        # 4. 执行创建史诗 POST saveOrUpdate
        save_payload = {
            "name": epic_name,
            "planStartTime": start_time_str,
            "planEndTime": end_time_str,
            "projectCollaborationId": ref_epic_info["projectCollaborationId"],
            "projectCollaborationName": ref_epic_info["projectCollaborationName"],
            "labels": [ref_epic_info["label"]],
            "depNames": ref_epic_info["depNames"],
            "status": ref_epic_info["status"],
            "type": ref_epic_info["type"]
        }

        save_res = await page.evaluate("""async ({headers, payload}) => {
            const r = await fetch('/api/multi-project-collaboration-service/kjptProjectCollaborationEpic/saveOrUpdate', {
                method: 'POST',
                headers: headers,
                body: JSON.stringify(payload)
            });
            return await r.json();
        }""", {"headers": headers_captured, "payload": save_payload})

        if save_res.get("code") != 200:
            print(f"创建史诗失败: {save_res.get('msg')}")
            await browser.close()
            return None

        # 5. 获取刚创建史诗的 ID / 编号
        await asyncio.sleep(1.0)
        query_created = await page.evaluate("""async ({headers, name}) => {
            const r = await fetch('/api/multi-project-collaboration-service/kjptProjectCollaborationEpic/listAllByExamples', {
                method: 'POST',
                headers: headers,
                body: JSON.stringify({
                    type: "0", myPutForward: "0", current: 1, size: 20, status: "0", searchKeyWords: name
                })
            });
            return await r.json();
        }""", {"headers": headers_captured, "name": epic_name})

        created_recs = query_created.get("data", {}).get("records", [])
        if not created_recs:
            print("史诗创建完成，但未在列表中检索到该史诗！")
            await browser.close()
            return None

        created_obj = created_recs[0]
        epic_id = created_obj.get("id")
        epic_code = created_obj.get("code")

        print(f"\n史诗创建成功! 史诗编号: {epic_code} (内部ID: {epic_id})")

        # 6. 关联需求 saveEpicRelationDemands & saveOrUpdateEpicRelationDemands
        await page.evaluate("""async ({headers, epicId, demands}) => {
            await fetch('/api/multi-project-collaboration-service/kjptProjectCollaborationEpic/saveEpicRelationDemands', {
                method: 'POST',
                headers: headers,
                body: JSON.stringify({
                    epicId: epicId,
                    demandIdList: demands,
                    source: "0"
                })
            });
            await fetch('/api/multi-project-collaboration-service/kjptProjectCollaborationEpic/saveOrUpdateEpicRelationDemands', {
                method: 'POST',
                headers: headers,
                body: JSON.stringify({
                    epicId: epicId,
                    demandIds: demands.join(';'),
                    removeOrAdd: "0"
                })
            });
        }""", {"headers": headers_captured, "epicId": epic_id, "demands": demand_ids})

        print(f"成功将需求 [{', '.join(demand_ids)}] 关联到史诗 [{epic_code}]")

        result_data = {
            "epic_code": epic_code,
            "epic_id": epic_id,
            "epic_name": epic_name,
            "plan_start": start_time_str,
            "plan_end": end_time_str,
            "project_set": ref_epic_info["projectCollaborationName"],
            "label": ref_epic_info["label"],
            "dept": ref_epic_info["depNames"],
            "demands": demand_details
        }

        await browser.close()
        return result_data

def main():
    parser = argparse.ArgumentParser(description="根据需求号自动创建史诗技能")
    parser.add_argument("demands", nargs="+", help="需求编号或包含需求编号的URL")
    parser.add_argument("--reference", default="PG202204-0269", help="参考史诗编号 (默认: PG202204-0269)")
    parser.add_argument("--name", default=None, help="自定义史诗名称（若不提供则根据需求标题自动提炼）")
    parser.add_argument("--dry-run", action="store_true", help="试运行模式，仅输出拟创建参数，不实际提交")

    args = parser.parse_args()
    res = asyncio.run(create_epic_workflow(args.demands, args.reference, args.name, args.dry_run))

    if res and not res.get("dry_run"):
        print("\n" + "="*50)
        print("🎉 史诗自动创建完成报告")
        print("="*50)
        print(f"📌 史诗编号: {res['epic_code']}")
        print(f"📝 史诗名称: {res['epic_name']}")
        print(f"📅 计划周期: {res['plan_start']} ~ {res['plan_end']} (当日~2个月后)")
        print(f"🏗️ 所属工程集: {res['project_set']}")
        print(f"🏷️ 史诗标签: {res['label']}")
        print(f"🏢 提出部门: {res['dept']}")
        print(f"🔗 关联需求列表 ({len(res['demands'])}笔):")
        for d in res['demands']:
            print(f"   • [{d['id']}] {d['title']}")
        print("="*50)

if __name__ == "__main__":
    main()
