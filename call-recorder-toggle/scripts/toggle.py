#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
电话录音一键开关核心逻辑 (Call Recorder Toggle Core Script)
"""

import os
import sys
import subprocess
import time
from datetime import datetime

RECORD_DIR = "/Volumes/Macintosh HD_Data/WorkBuddy/电话纪要/recordings"
PID_FILE = "/tmp/manual_record.pid"
FILENAME_FILE = "/tmp/manual_record_filename.txt"
TRANSCRIBE_SCRIPT = "/Users/wujin/.workbuddy/skills/audio-to-minutes/scripts/transcribe.py"
TERMINAL_NOTIFIER = "/usr/local/bin/terminal-notifier"

def send_notification(title, message):
    """发送 macOS 系统通知"""
    try:
        if os.path.exists(TERMINAL_NOTIFIER):
            subprocess.run([TERMINAL_NOTIFIER, "-title", title, "-message", message], stderr=subprocess.DEVNULL)
        else:
            osascript_code = f'display notification "{message}" with title "{title}"'
            subprocess.run(["osascript", "-e", osascript_code], stderr=subprocess.DEVNULL)
    except Exception:
        pass

def is_recording():
    """判断当前是否正在录音"""
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE, "r") as f:
                pid = int(f.read().strip())
            # 检查 pid 是否活在进程表中
            res = subprocess.run(["kill", "-0", str(pid)], capture_output=True)
            if res.returncode == 0:
                return pid
        except Exception:
            pass
    return None

def start_recording():
    """启动电话录音"""
    os.makedirs(RECORD_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_wav = os.path.join(RECORD_DIR, f"call_{timestamp}.wav")
    
    with open(FILENAME_FILE, "w") as f:
        f.write(output_wav)
        
    cmd = [
        "/usr/local/bin/sox", "-t", "coreaudio", "default", output_wav
    ]
    # start_new_session=True => setsid 脱离父 shell 会话，避免父命令退出时被 SIGHUP/进程组清理杀掉
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True
    )
    
    with open(PID_FILE, "w") as f:
        f.write(str(proc.pid))
        
    send_notification("🔴 电话录音已开启", f"正在录音中... ({os.path.basename(output_wav)})")
    return {
        "status": "recording_started",
        "pid": proc.pid,
        "wav_path": output_wav,
        "message": f"🔴 电话录音已成功开启！正在实时录音中...\n保存文件目标: `{output_wav}`"
    }

def stop_recording():
    """停止电话录音并自动归档"""
    pid = is_recording()
    wav_path = ""
    if os.path.exists(FILENAME_FILE):
        with open(FILENAME_FILE, "r") as f:
            wav_path = f.read().strip()
            
    if pid:
        try:
            subprocess.run(["kill", "-SIGINT", str(pid)], stderr=subprocess.DEVNULL)
        except Exception:
            pass
            
    if os.path.exists(PID_FILE):
        try:
            os.remove(PID_FILE)
        except Exception:
            pass

    # 等待文件刷盘
    time.sleep(0.8)
    
    send_notification("🟢 电话录音已保存", f"录音已安全存盘: {os.path.basename(wav_path)}")
    
    # 自动异步调起 audio-to-minutes 转写引擎
    if wav_path and os.path.exists(wav_path):
        try:
            subprocess.Popen([
                "/usr/local/bin/python3",
                TRANSCRIBE_SCRIPT,
                wav_path
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass

    return {
        "status": "recording_stopped",
        "wav_path": wav_path,
        "message": f"🟢 **电话录音已成功停止并保存存盘！**\n\n- 📁 **原始 WAV 文件**：`{wav_path}`\n- 🚀 **下一步推荐**：您可以在对话框中直接发送或触发：\n  `/audio-to-minutes {wav_path}`\n  生成结构化 Obsidian 会议与电话纪要。"
    }

def toggle():
    """录音开关切换"""
    if is_recording():
        return stop_recording()
    else:
        return start_recording()

if __name__ == "__main__":
    action = sys.argv[1] if len(sys.argv) > 1 else "toggle"
    if action == "start":
        res = start_recording()
    elif action == "stop":
        res = stop_recording()
    elif action == "status":
        pid = is_recording()
        if pid:
            res = {"status": "recording", "pid": pid, "message": f"🔴 当前正在录音中 (PID: {pid})"}
        else:
            res = {"status": "idle", "message": "⚪ 当前未开启录音"}
    else:
        res = toggle()
        
    print(res["message"])
