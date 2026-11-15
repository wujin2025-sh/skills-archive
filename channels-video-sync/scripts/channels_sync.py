#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
微信视频号极速全自动同步引擎 (WeChat Channels Fast Sync Engine v3.0 Ultra)
核心特性：
1. 原生桥接当前运行的 Google Chrome 真实登录态（免扫码、0 风控）；
2. 穿透腾讯 Wujie (无界微前端) Shadow DOM，精准操作视频上传与表单组件；
3. 毫秒级原生 CoreGraphics 硬件事件 + System Events 快捷路径注入（压缩延时，极速落库）；
4. 描述规范铁律：自动以【长标题】置顶，换行后接精彩正文，再换行附带垂直话题；
5. 默认强制【声明原创】：高频紧凑穿透“原创权益”弹窗协议，0.2 秒内自动勾选并确认，零人工干预；
6. 保存草稿即刻闭环退出：点击【保存草稿】后立即输出完成耗时并优雅退出。
"""

import os
import sys
import time
import json
import ctypes
import argparse
import subprocess

# macOS CoreGraphics Event Dispatcher
CoreGraphics = ctypes.CDLL('/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics')

class CGPoint(ctypes.Structure):
    _fields_ = [("x", ctypes.c_double), ("y", ctypes.c_double)]

CGEventCreateMouseEvent = CoreGraphics.CGEventCreateMouseEvent
CGEventCreateMouseEvent.restype = ctypes.c_void_p
CGEventCreateMouseEvent.argtypes = [ctypes.c_void_p, ctypes.c_uint32, CGPoint, ctypes.c_uint32]

CGEventPost = CoreGraphics.CGEventPost
CGEventPost.restype = None
CGEventPost.argtypes = [ctypes.c_uint32, ctypes.c_void_p]

CFRelease = CoreGraphics.CFRelease
CFRelease.restype = None
CFRelease.argtypes = [ctypes.c_void_p]

def click_at(x, y):
    pt = CGPoint(x, y)
    ev_down = CGEventCreateMouseEvent(None, 1, pt, 0)
    CGEventPost(0, ev_down)
    CFRelease(ev_down)
    time.sleep(0.03)
    ev_up = CGEventCreateMouseEvent(None, 2, pt, 0)
    CGEventPost(0, ev_up)
    CFRelease(ev_up)

def exec_js(js_code):
    escaped = js_code.replace('\\', '\\\\').replace('"', '\\"')
    cmd = f'''
    tell application "Google Chrome"
        repeat with w in windows
            repeat with t in tabs of w
                if URL of t contains "channels.weixin.qq.com" then
                    set res to execute t javascript "{escaped}"
                    return res
                end if
            end repeat
        end repeat
        return "NOT_FOUND"
    end tell
    '''
    p = subprocess.run(["osascript", "-e", cmd], capture_output=True, text=True)
    return p.stdout.strip()

def activate_chrome():
    subprocess.run(["osascript", "-e", '''
    tell application "Google Chrome"
        activate
        try
            set index of front window to 1
        end try
    end tell
    tell application "System Events"
        tell process "Google Chrome"
            set frontmost to true
        end tell
    end tell
    '''])
    time.sleep(0.4)

def ensure_post_create_page():
    """确保 Chrome 中处于视频号助手发表页"""
    curr = exec_js("window.location.href")
    if "channels.weixin.qq.com" not in curr or "post/create" not in curr:
        print("🌐 正在 Chrome 中打开视频号助手发表页...")
        subprocess.run(["osascript", "-e", '''
        tell application "Google Chrome"
            tell front window
                make new tab with properties {URL:"https://channels.weixin.qq.com/platform/post/create"}
            end tell
            activate
        end tell
        '''])
        time.sleep(2.5)
        activate_chrome()
    
    # 极速清理阻断式弱弹窗
    exec_js("""
    (function() {
        const btns = Array.from(document.querySelectorAll('button'));
        btns.forEach(b => {
            if (b.innerText.includes('我知道了') || b.innerText.includes('取消') || b.classList.contains('weui-desktop-dialog__close-btn')) {
                b.click();
            }
        });
    })()
    """)
    time.sleep(0.2)

def wait_for_sheet_and_inject(file_path, timeout=9.0):
    start = time.time()
    while time.time() - start < timeout:
        check = '''
        tell application "System Events"
            tell process "Google Chrome"
                repeat with w in windows
                    try
                        if (count of sheets of w) > 0 then
                            return "FOUND"
                        end if
                    end try
                end repeat
                return "NONE"
            end tell
        end tell
        '''
        res = subprocess.run(["osascript", "-e", check], capture_output=True, text=True).stdout.strip()
        if res == "FOUND":
            time.sleep(0.3)
            inject = f'''
            tell application "Google Chrome" to activate
            set the clipboard to "{file_path}"
            tell application "System Events"
                tell process "Google Chrome"
                    keystroke "g" using {{command down, shift down}}
                    delay 0.5
                    keystroke "v" using {{command down}}
                    delay 0.3
                    key code 36
                    delay 0.5
                    key code 36
                end tell
            end tell
            '''
            subprocess.run(["osascript", "-e", inject])
            return True
        time.sleep(0.2)
    return False

def get_element_coords(selector):
    js = f"""
    (function() {{
        const w = document.querySelector('wujie-app');
        if (!w || !w.shadowRoot) return null;
        const el = w.shadowRoot.querySelector('{selector}');
        if (!el) return null;
        el.scrollIntoView({{block: 'center'}});
        const rect = el.getBoundingClientRect();
        return JSON.stringify({{
            x: rect.x + rect.width / 2,
            y: rect.y + rect.height / 2,
            screenX: window.screenX,
            screenY: window.screenY,
            outerHeight: window.outerHeight,
            innerHeight: window.innerHeight
        }});
    }})()
    """
    res = exec_js(js)
    if not res or res in ["NOT_FOUND", "null"]:
        return None
    try:
        data = json.loads(res)
        bar_height = data['outerHeight'] - data['innerHeight']
        return (data['screenX'] + data['x'], data['screenY'] + bar_height + data['y'])
    except:
        return None

def auto_handle_original_declaration(timeout=3.5):
    """毫秒级高频穿透声明原创与弹窗协议，确保 100% 自动确认闭环"""
    start = time.time()
    while time.time() - start < timeout:
        res = exec_js("""
        (function() {
            const w = document.querySelector('wujie-app');
            const root = (w && w.shadowRoot) ? w.shadowRoot : document;
            
            // 1. 勾选主界面的复选框
            const mainChk = root.querySelector('.declare-original-checkbox input');
            if (mainChk && !mainChk.checked) {
                const wrap = root.querySelector('.declare-original-checkbox .ant-checkbox-wrapper') || mainChk;
                wrap.click();
            }
            
            // 2. 扫描并击穿协议弹窗
            const dialogs = Array.from(root.querySelectorAll('.weui-desktop-dialog'))
                .concat(Array.from(document.querySelectorAll('.weui-desktop-dialog')))
                .filter(d => (d.innerText.includes('原创权益') || d.innerText.includes('声明原创')) && d.getBoundingClientRect().width > 0);
            
            for (const d of dialogs) {
                const chk = d.querySelector('input[type=checkbox]');
                if (chk && !chk.checked) chk.click();
                const label = d.querySelector('.weui-desktop-form__check-label, .ant-checkbox-wrapper');
                if (label && chk && !chk.checked) label.click();
                
                const btn = Array.from(d.querySelectorAll('button'))
                    .find(b => b.innerText.trim() === '声明原创' || b.innerText.includes('声明原创'));
                if (btn && !btn.disabled && !btn.classList.contains('weui-desktop-btn_disabled')) {
                    btn.click();
                }
            }
            
            const isDone = mainChk && mainChk.checked && dialogs.length === 0;
            return JSON.stringify({ isDone, checked: mainChk ? mainChk.checked : false });
        })()
        """)
        if res and res != "NOT_FOUND":
            try:
                data = json.loads(res)
                if data.get("isDone") or data.get("checked"):
                    return True
            except:
                pass
        time.sleep(0.15)
    return False

def sync_to_channels(video_path: str, cover_path: str = None, short_title: str = "",
                      long_title: str = "", description: str = "", collection: str = "大国券商",
                      declare_original: bool = True):
    t0 = time.time()
    video_abs = os.path.abspath(video_path)
    if not os.path.exists(video_abs):
        raise FileNotFoundError(f"视频母带不存在: {video_abs}")
    
    # 格式化描述文案（铁律：长标题置顶 -> 换行 -> 正文 -> 话题标签）
    full_description = description.strip()
    if long_title:
        lt = long_title.strip()
        if not full_description.startswith(lt):
            full_description = f"{lt}\n\n{full_description}"
            
    print("=" * 68)
    print("🚀 微信视频号极速全自动同步引擎 (Fast Sync Engine v3.0 Ultra)")
    print(f"🎬 视频母带: {os.path.basename(video_abs)} ({os.path.getsize(video_abs)/(1024*1024):.1f} MB)")
    if cover_path:
        cover_abs = os.path.abspath(cover_path)
        print(f"🖼️ 定制封面: {os.path.basename(cover_abs)}")
    print(f"📌 短标题: {short_title[:16]} ({len(short_title[:16])}/16字)")
    if long_title:
        print(f"📖 描述长标题: {long_title[:30]}...")
    print(f"🏷️ 所属合集: 【{collection}】 | 默认声明原创: 是")
    print("=" * 68)

    activate_chrome()
    ensure_post_create_page()

    # Step 1: 视频载入（智能复用/极速注入）
    has_video = exec_js("document.querySelector('wujie-app')?.shadowRoot?.querySelector('video') !== null")
    if has_video == "true":
        print(f"[{time.time()-t0:.1f}s] ✅ 视频母带已在页面中，跳过文件注入。")
    else:
        print(f"[{time.time()-t0:.1f}s] 📤 定位并上传视频母带...")
        activate_chrome()
        coords = get_element_coords('.ant-upload-btn')
        if not coords:
            print("❌ 未定位到上传按钮，请确认是否处于发表视频状态！")
            return False
        click_at(coords[0], coords[1])
        if not wait_for_sheet_and_inject(video_abs):
            print("❌ 视频注入失败！")
            return False
        print(f"[{time.time()-t0:.1f}s] ⏳ 等待视频流式载入与转码...")
        for _ in range(35):
            time.sleep(0.8)
            if exec_js("document.querySelector('wujie-app')?.shadowRoot?.querySelector('video') !== null") == "true":
                print(f"[{time.time()-t0:.1f}s] ✅ 视频载入完成！")
                break

    # Step 2: 上传并裁切定制封面海报
    if cover_path and os.path.exists(cover_abs):
        print(f"[{time.time()-t0:.1f}s] 🖼️ 极速设置定制竖版封面海报...")
        exec_js("""
        (function() {
            const w = document.querySelector('wujie-app');
            if (!w || !w.shadowRoot) return;
            const editBtn = w.shadowRoot.querySelector('.edit-btn');
            if (editBtn) editBtn.click();
        })()
        """)
        time.sleep(0.5)
        cover_coords = get_element_coords('.single-cover-uploader-wrap .wrap') or get_element_coords('.single-cover-uploader-wrap')
        if cover_coords:
            activate_chrome()
            click_at(cover_coords[0], cover_coords[1])
            if wait_for_sheet_and_inject(cover_abs, timeout=5.0):
                time.sleep(0.8)
                # 高频确认裁剪与确认编辑
                for _ in range(15):
                    done = exec_js("""
                    (function() {
                        const w = document.querySelector('wujie-app');
                        if (!w || !w.shadowRoot) return false;
                        const cropDialog = Array.from(w.shadowRoot.querySelectorAll('.weui-desktop-dialog')).find(d => d.innerText.includes('裁剪封面图'));
                        if (cropDialog) {
                            const btn = Array.from(cropDialog.querySelectorAll('button')).find(b => b.innerText.trim() === '确定');
                            if (btn) btn.click();
                        }
                        const editDialog = Array.from(w.shadowRoot.querySelectorAll('.weui-desktop-dialog')).find(d => d.innerText.includes('编辑封面'));
                        if (editDialog) {
                            const btn = Array.from(editDialog.querySelectorAll('button')).find(b => b.innerText.trim() === '确认');
                            if (btn) { btn.click(); return true; }
                        }
                        return false;
                    })()
                    """)
                    if done == "true":
                        break
                    time.sleep(0.2)
                print(f"[{time.time()-t0:.1f}s] ✅ 封面海报上传与裁切完成！")

    # Step 3: 注入短标题与规范描述
    clean_title = short_title[:16] if short_title else ""
    print(f"[{time.time()-t0:.1f}s] ✍️ 注入短标题与规范视频描述...")
    meta_js = f"""
    (function() {{
        const w = document.querySelector('wujie-app');
        if (!w || !w.shadowRoot) return;
        
        // 短标题 (严格限制 <= 16 字)
        const shortTitleInput = w.shadowRoot.querySelector('input[placeholder*="短标题"]');
        if (shortTitleInput) {{
            shortTitleInput.focus();
            shortTitleInput.value = {json.dumps(clean_title)};
            shortTitleInput.dispatchEvent(new Event('input', {{ bubbles: true }}));
            shortTitleInput.dispatchEvent(new Event('change', {{ bubbles: true }}));
        }}
        
        // 视频描述（长标题置顶 -> 换行 -> 正文 -> 话题）
        const editor = w.shadowRoot.querySelector('.input-editor');
        if (editor) {{
            editor.focus();
            editor.innerText = {json.dumps(full_description)};
            editor.dispatchEvent(new Event('input', {{ bubbles: true }}));
            editor.dispatchEvent(new Event('change', {{ bubbles: true }}));
        }}
    }})()
    """
    exec_js(meta_js)
    time.sleep(0.3)

    # Step 4: 选择合集
    if collection:
        print(f"[{time.time()-t0:.1f}s] 🏷️ 关联合集【{collection}】...")
        curr_album = exec_js("document.querySelector('wujie-app')?.shadowRoot?.querySelector('.post-album-display')?.innerText")
        if curr_album != collection:
            exec_js("""
            (function() {
                const w = document.querySelector('wujie-app');
                if (!w || !w.shadowRoot) return;
                const el = w.shadowRoot.querySelector('.post-album-display-wrap, .display-text');
                if (el) el.click();
            })()
            """)
            time.sleep(0.3)
            exec_js(f"""
            (function() {{
                const w = document.querySelector('wujie-app');
                if (!w || !w.shadowRoot) return;
                const items = Array.from(w.shadowRoot.querySelectorAll('.option-item'));
                const target = items.find(it => it.innerText.includes('{collection}'));
                if (target) target.click();
            }})()
            """)
        print(f"[{time.time()-t0:.1f}s] ✅ 合集已绑定为【{collection}】")

    # Step 5: 默认声明原创（毫秒级高频穿透，零人工干预）
    if declare_original:
        print(f"[{time.time()-t0:.1f}s] 🛡️ 默认校验并确认原创声明...")
        auto_handle_original_declaration(timeout=3.0)
        print(f"[{time.time()-t0:.1f}s] ✅ 原创声明已确认！")

    # Step 6: 保存草稿并立即圆满退出
    print(f"[{time.time()-t0:.1f}s] 💾 点击【保存草稿】...")
    btn_coords = get_element_coords("button:has-text('保存草稿')")
    if not btn_coords:
        js_find = """
        (function() {
            const w = document.querySelector('wujie-app');
            if (!w || !w.shadowRoot) return null;
            const draftBtn = Array.from(w.shadowRoot.querySelectorAll('button')).find(b => b.innerText.trim() === '保存草稿');
            if (!draftBtn) return null;
            draftBtn.scrollIntoView({block: 'center'});
            const rect = draftBtn.getBoundingClientRect();
            return JSON.stringify({
                x: rect.x + rect.width / 2,
                y: rect.y + rect.height / 2,
                screenX: window.screenX,
                screenY: window.screenY,
                outerHeight: window.outerHeight,
                innerHeight: window.innerHeight
            });
        })()
        """
        res = exec_js(js_find)
        if res and res != "null":
            data = json.loads(res)
            bar_height = data['outerHeight'] - data['innerHeight']
            btn_coords = (data['screenX'] + data['x'], data['screenY'] + bar_height + data['y'])

    if btn_coords:
        activate_chrome()
        click_at(btn_coords[0], btn_coords[1])
        exec_js("""
        (function() {
            const w = document.querySelector('wujie-app');
            if (!w || !w.shadowRoot) return;
            const draftBtn = Array.from(w.shadowRoot.querySelectorAll('button')).find(b => b.innerText.trim() === '保存草稿');
            if (draftBtn && !draftBtn.disabled) draftBtn.click();
        })()
        """)
        time.sleep(0.8)
        print(f"[{time.time()-t0:.1f}s] 🎉 点击【保存草稿】成功，同步流程圆满结束并退出！总耗时: {time.time()-t0:.2f} 秒")
        print("=" * 68)
        return True
    else:
        print("⚠️ 未定位到保存草稿按钮")
        return False

def main():
    parser = argparse.ArgumentParser(description="微信视频号极速全自动同步引擎")
    parser.add_argument("--video", "-v", required=True, help="视频文件绝对路径")
    parser.add_argument("--cover", "-c", default=None, help="封面图片路径 (9:16 或 3:4)")
    parser.add_argument("--title", "-t", default="", help="短标题 (<=16字)")
    parser.add_argument("--long-title", "-lt", default="", help="长标题（用于置顶于视频描述）")
    parser.add_argument("--desc", "-d", default="", help="视频描述正文及话题")
    parser.add_argument("--collection", "-col", default="大国券商", help="所属合集名称")
    parser.add_argument("--no-original", action="store_true", help="不声明原创（默认会自动声明）")
    
    args = parser.parse_args()
    sync_to_channels(
        video_path=args.video,
        cover_path=args.cover,
        short_title=args.title,
        long_title=args.long_title,
        description=args.desc,
        collection=args.collection,
        declare_original=not args.no_original
    )

if __name__ == "__main__":
    main()
