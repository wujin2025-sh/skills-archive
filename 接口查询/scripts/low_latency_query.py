# -*- coding: utf-8 -*-
# 金融科技服务治理平台 - 低延时接口自动化查询工具

import json
import time
import traceback
import sys
import os
import io
import argparse
from playwright.sync_api import sync_playwright

# Force standard output encoding to UTF-8
if hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

class LowLatencyQuery:
    def __init__(self, keyword, headless=True, groups=None):
        self.keyword = keyword
        self.headless = headless
        self.groups = [g.strip() for g in groups.split(",")] if groups else None
        
        # Load local config
        script_dir = os.path.dirname(os.path.abspath(__file__))
        config_path = os.path.join(script_dir, "config.json")
        if not os.path.exists(config_path):
            print(f"❌ 配置文件不存在: {config_path}")
            sys.exit(1)
            
        with open(config_path, "r", encoding="utf-8") as f:
            self.config = json.load(f)
            
        self.username = self.config["account"]["username"]
        raw_password = self.config["account"].get("password", "")
        self.password = self._decrypt_password(raw_password)
        self.viewport = self.config["browser"]["viewport"]
        self.target_url = self.config["platform"].get("target_url", "http://sg.gtht.com.cn/fwzl/interfaceManage/interfaceManage.html")
        
        # Session path
        uat_session_dir = "/Users/wujin/.workbuddy/skills/uat_accept/scripts"
        if os.path.exists(uat_session_dir):
            self.session_file = os.path.join(uat_session_dir, ".fintech_session.json")
        else:
            self.session_file = os.path.join(script_dir, ".fintech_session.json")
            
        print(f"[初始化] 查询关键字: {self.keyword}")
        if self.groups:
            print(f"[初始化] 过滤所属分组: {self.groups}")
        print(f"[初始化] 缓存 Session: {self.session_file}")

    def _decrypt_password(self, enc_str, key_path='~/.workbuddy/.meeting_skill_key'):
        if not enc_str.startswith('ENC:'):
            return enc_str
        kp = os.path.expanduser(key_path)
        if not os.path.exists(kp):
            print(f"❌ 密钥文件不存在: {kp}")
            sys.exit(1)
        try:
            from cryptography.fernet import Fernet
        except ImportError:
            print("❌ 缺少依赖: pip install cryptography")
            sys.exit(1)
        with open(kp, 'rb') as f:
            key = f.read()
        fern = Fernet(key)
        try:
            return fern.decrypt(enc_str[4:].encode('utf-8')).decode('utf-8')
        except Exception as e:
            print(f"❌ 密码解密失败: {e}")
            sys.exit(1)

    def run(self):
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=self.headless, channel="chrome")
            context_args = {"viewport": self.viewport}
            if os.path.exists(self.session_file):
                context_args["storage_state"] = self.session_file
                
            context = browser.new_context(**context_args)
            page = context.new_page()
            
            try:
                print(f"[导航] 访问接口管理页面: {self.target_url}")
                page.goto(self.target_url, timeout=30000)
                
                # Wait for main page element or login form quickly
                try:
                    page.wait_for_selector('input[placeholder*="工号"], input[placeholder*="OA"], input[placeholder*="Employee"], input[type="password"], label[title="接口关键字"], input.ant-input', timeout=10000)
                except Exception:
                    pass
                
                # Check for login form redirection
                needs_login = page.evaluate("""() => {
                    const hasPwd = document.querySelector('input[type="password"]');
                    const hasUser = [...document.querySelectorAll('input')]
                        .some(el => (el.placeholder||'').includes('工号') || (el.placeholder||'').includes('OA') || (el.placeholder||'').includes('Employee'));
                    return !!(hasPwd && hasUser);
                }""")
                
                if needs_login:
                    print("[登录] 检测到登录表单，开始执行登录...")
                    user_input = page.locator('input[placeholder*="工号"], input[placeholder*="OA"], input[placeholder*="Employee"], input[type="text"]').first
                    user_input.fill(self.username)
                    
                    pwd_input = page.locator('input[type="password"]').first
                    pwd_input.fill(self.password)
                    
                    login_btn = page.locator('button:has-text("Login"), button:has-text("登录"), button.loginButton').first
                    if login_btn.count() > 0:
                        login_btn.click()
                    else:
                        page.keyboard.press("Enter")
                        
                    print("[登录] 等待登录完成...")
                    try:
                        page.wait_for_selector('label[title="接口关键字"], input.ant-input', timeout=15000)
                    except Exception:
                        page.wait_for_timeout(3000)
                    
                    # Save context session
                    context.storage_state(path=self.session_file)
                    print("[登录] Session 已更新保存")
                    
                    if "interfaceManage.html" not in page.url:
                        print(f"[导航] 重新载入接口管理页面: {self.target_url}")
                        page.goto(self.target_url, timeout=30000)
                        try:
                            page.wait_for_selector('label[title="接口关键字"], input.ant-input', timeout=10000)
                        except Exception:
                            page.wait_for_timeout(2000)
                
                # Verify keyword field is present
                keyword_input = page.locator('div.ant-row.ant-form-item:has(label[title="接口关键字"]) input.ant-input')
                if keyword_input.count() == 0:
                    keyword_input = page.locator('label[title="接口关键字"] >> xpath=../..//input')
                    
                if keyword_input.count() == 0:
                    print("❌ 未能在页面上找到 '接口关键字' 输入框")
                    return
                
                # Clear and fill the keyword
                keyword_input.first.click()
                page.keyboard.press("Control+A")
                page.keyboard.press("Backspace")
                keyword_input.first.fill(self.keyword)
                
                # Click Query
                query_btn = page.locator('button:has-text("查 询")')
                if query_btn.count() == 0:
                    query_btn = page.locator('button.ant-btn-primary').first
                    
                if query_btn.count() == 0:
                    print("❌ 未能在页面上找到 '查询' 按钮")
                    return
                    
                print("[查询] 提交查询请求...")
                query_btn.first.click()
                
                # Smart wait for table rows or empty result
                try:
                    page.wait_for_selector("div.ant-table-body table tbody tr", timeout=8000)
                    page.wait_for_timeout(500)  # Brief pause for DOM render
                except Exception:
                    pass
                
                # Extract Results
                print("[解析] 开始解析接口查询结果...")
                rows = page.locator("div.ant-table-body table tbody tr").all()
                
                if not rows or len(rows) == 0:
                    print("⚠️ 未查询到接口数据或数据为空")
                    return
                
                # Headers definition matching the web UI
                headers = ["接口号", "接口名称", "接口类型", "版本号", "所属分组", "负责人", "创建者", "更新时间", "操作"]
                
                # Check for "No Data" row
                first_row_text = rows[0].inner_text().strip()
                if "No Data" in first_row_text or "暂无数据" in first_row_text or not first_row_text:
                    print("\n### 接口查询结果\n\n> 🔍 未找到与关键字 **{}** 匹配的接口信息。\n".format(self.keyword))
                    return

                # Render markdown table
                md_output = []
                md_output.append("\n### 接口查询结果 (关键字: **{}** | [🔗 访问服务治理平台](http://sg.gtht.com.cn/fwzl/interfaceManage/interfaceManage.html))".format(self.keyword))
                md_output.append("| " + " | ".join(headers) + " |")
                md_output.append("| " + " | ".join(["---"] * len(headers)) + " |")
                
                valid_count = 0
                first_matching_row_index = -1
                for idx, row in enumerate(rows):
                    cells = row.locator("td").all()
                    if len(cells) >= len(headers) - 1:
                        cell_texts = []
                        for cell in cells:
                            txt = cell.inner_text().strip().replace("\n", " ")
                            cell_texts.append(txt)
                        # Pad cells if necessary
                        while len(cell_texts) < len(headers):
                            cell_texts.append("-")
                        
                        # Apply group filtering if specified (index 4 is "所属分组")
                        if self.groups:
                            group_val = cell_texts[4]
                            if not any(g in group_val for g in self.groups):
                                continue
                        
                        if first_matching_row_index == -1:
                            first_matching_row_index = idx
                                
                        md_output.append("| " + " | ".join(cell_texts) + " |")
                        valid_count += 1
                        
                print(f"[解析] 成功解析出 {valid_count} 条接口记录")
                print("\n".join(md_output) + "\n")
                
                # If headed mode, open the matching row details and keep browser open
                if not self.headless and first_matching_row_index != -1:
                    print("[交互] 检测到有界面模式运行，正在为您打开第一条匹配记录的详情弹窗...")
                    target_row = rows[first_matching_row_index]
                    detail_btn = target_row.locator("td").first.locator("span > span")
                    if detail_btn.count() > 0:
                        detail_btn.first.click()
                        page.wait_for_timeout(2000)
                        print("[交互] 详情弹窗已打开。浏览器将保持开启状态。")
                        print("[交互] 请在终端按 【回车键/Enter】 退出并关闭浏览器...")
                        try:
                            input()
                        except:
                            time.sleep(300)
                
            except Exception as e:
                print(f"❌ 运行中发生错误: {e}")
                traceback.print_exc()
            finally:
                browser.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="低延时接口查询自动化脚本")
    parser.add_argument("-k", "--keyword", required=True, help="接口关键字/接口号 (例如: 7300780)")
    parser.add_argument("-g", "--groups", help="过滤所属分组的关键字，多个用逗号分隔（例如: 低延时,集中交易）")
    parser.add_argument("-n", "--no-headless", action="store_true", help="是否显示浏览器界面运行")
    args = parser.parse_args()
    
    query = LowLatencyQuery(keyword=args.keyword, headless=not args.no_headless, groups=args.groups)
    query.run()
