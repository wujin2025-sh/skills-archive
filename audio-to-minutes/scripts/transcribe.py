#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
音频转写辅助工具脚本 (极致加速版)
Audio Transcription Helper Script using Native C++ whisper-cli / FFmpeg resample
"""

import sys
import os
import subprocess
import argparse
import json
import time

WHISPER_CPP_BIN = "/usr/local/bin/whisper-cli"
WHISPER_PY_BIN = "/usr/local/bin/whisper"
FFMPEG_BIN = "/usr/local/bin/ffmpeg"
CACHE_DIR = os.path.expanduser("~/.cache/whisper")
TRANSCRIPT_TMP = "/tmp/audio_to_minutes_tmp"

def get_best_model():
    """检测本地已有模型，零网络延迟优先加载"""
    os.makedirs(CACHE_DIR, exist_ok=True)
    
    # 优先找 ggml C++ 格式模型
    ggml_models = ["ggml-large-v3-turbo.bin", "ggml-base.bin", "ggml-tiny.bin", "ggml-small.bin"]
    for m in ggml_models:
        p = os.path.join(CACHE_DIR, m)
        if os.path.exists(p) and os.path.getsize(p) > 5 * 1024 * 1024:
            return ("cpp", p)
            
    # 备选 Python pt 模型
    pt_models = ["large-v3-turbo.pt", "base.pt", "tiny.pt", "small.pt"]
    for m in pt_models:
        p = os.path.join(CACHE_DIR, m)
        if os.path.exists(p) and os.path.getsize(p) > 5 * 1024 * 1024:
            return ("pt", m.replace(".pt", ""))
            
    return ("pt", "tiny")

def preprocess_audio(audio_path):
    """16kHz 单声道重采样，减少 70% 识别计算量"""
    os.makedirs(TRANSCRIPT_TMP, exist_ok=True)
    base_name = os.path.splitext(os.path.basename(audio_path))[0]
    opt_wav = os.path.join(TRANSCRIPT_TMP, f"{base_name}_16k.wav")
    
    cmd = [
        FFMPEG_BIN, "-y",
        "-i", audio_path,
        "-ac", "1", "-ar", "16000",
        opt_wav
    ]
    try:
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        if os.path.exists(opt_wav) and os.path.getsize(opt_wav) > 1000:
            return opt_wav
    except Exception:
        pass
    return audio_path

def find_today_audio(search_dir=None):
    """自动查找最新音频文件，优先扫描录音目录及当前工作目录"""
    search_dirs = []
    default_rec_dir = "/Volumes/Macintosh HD_Data/WorkBuddy/电话纪要/recordings"
    if os.path.exists(default_rec_dir):
        search_dirs.append(default_rec_dir)
    
    if search_dir:
        search_dirs.append(search_dir)
    else:
        search_dirs.append(os.getcwd())
    
    audio_extensions = {".m4a", ".mp3", ".wav", ".aac", ".flac", ".ogg", ".wma"}
    candidates = []
    for s_dir in search_dirs:
        for root, dirs, files in os.walk(s_dir):
            dirs[:] = [d for d in dirs if not d.startswith('.')]
            for f in files:
                ext = os.path.splitext(f)[1].lower()
                if ext in audio_extensions:
                    full_path = os.path.join(root, f)
                    if os.path.getsize(full_path) > 1000:
                        candidates.append((full_path, os.path.getmtime(full_path)))
    
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[1], reverse=True)
    return candidates[0][0]

def find_all_audio_files(search_dir=None):
    """自动查找同批次所有有效音频文件，按时间正序排列以便统一顺序合并转写"""
    search_dirs = []
    default_rec_dir = "/Volumes/Macintosh HD_Data/WorkBuddy/电话纪要/recordings"
    if os.path.exists(default_rec_dir):
        search_dirs.append(default_rec_dir)
    
    if search_dir:
        search_dirs.append(search_dir)
    else:
        search_dirs.append(os.getcwd())
    
    audio_extensions = {".m4a", ".mp3", ".wav", ".aac", ".flac", ".ogg", ".wma"}
    candidates = []
    seen = set()
    for s_dir in search_dirs:
        for root, dirs, files in os.walk(s_dir):
            dirs[:] = [d for d in dirs if not d.startswith('.')]
            for f in sorted(files):
                ext = os.path.splitext(f)[1].lower()
                if ext in audio_extensions:
                    full_path = os.path.join(root, f)
                    if os.path.getsize(full_path) > 1000 and full_path not in seen:
                        seen.add(full_path)
                        candidates.append((full_path, os.path.getmtime(full_path)))
    
    candidates.sort(key=lambda x: x[1])  # 时间正序，保障多段音频顺序
    return [c[0] for c in candidates]

def transcribe_audio(audio_path, model="auto", language="Chinese", output_dir=None):
    """极致极速转写引擎主入口"""
    start_time = time.time()
    
    if not audio_path or audio_path.lower() in ("auto", "today", "current", ""):
        auto_found = find_today_audio()
        if not auto_found:
            raise FileNotFoundError("未找到任何音频文件")
        audio_path = auto_found
        print(f"自动选用最新音频文件: {audio_path}")

    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"音频文件不存在: {audio_path}")

    if output_dir is None:
        output_dir = os.path.join(os.path.expanduser("~"), ".cache", "audio_transcripts")
    os.makedirs(output_dir, exist_ok=True)

    # 1. 音频重采样预处理提速
    opt_audio = preprocess_audio(audio_path)
    base_name = os.path.splitext(os.path.basename(opt_audio))[0]
    out_prefix = os.path.join(output_dir, base_name)
    txt_file = os.path.join(output_dir, f"{base_name}.txt")

    engine_type, model_target = get_best_model()

    # 优先尝试 C++ 8 线程硬件级加速
    if engine_type == "cpp" and os.path.exists(WHISPER_CPP_BIN):
        print(f"[⚡] 激活 C++ 原生硬件加速 (8 线程) 转写: {audio_path}...")
        cmd = [
            WHISPER_CPP_BIN,
            "-m", model_target,
            "-l", "zh",
            "-t", "8",
            "-f", opt_audio,
            "--output-txt",
            "--output-file", out_prefix
        ]
        res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if res.returncode == 0 and os.path.exists(txt_file):
            elapsed = time.time() - start_time
            print(f"[✓] C++ 极速转写完成！耗时: {elapsed:.2f} 秒")
            with open(txt_file, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read().strip()
            return {
                "audio_path": os.path.abspath(audio_path),
                "txt_file": txt_file,
                "content": content,
                "elapsed_seconds": round(elapsed, 2)
            }

    # 备选: Python 8 线程加速
    print(f"[*] 激活 Python 8 线程极速模式转写: {audio_path}...")
    py_cmd = [
        WHISPER_PY_BIN,
        opt_audio,
        "--model", "tiny",
        "--language", "Chinese",
        "--threads", "8",
        "--output_format", "txt",
        "--output_dir", output_dir
    ]
    env = os.environ.copy()
    env["HF_ENDPOINT"] = "https://hf-mirror.com"
    
    subprocess.run(py_cmd, check=True, env=env)
    elapsed = time.time() - start_time
    print(f"[✓] 转写完成！耗时: {elapsed:.2f} 秒")

    if not os.path.exists(txt_file):
        matching = [f for f in os.listdir(output_dir) if f.startswith(base_name) and f.endswith(".txt")]
        if matching:
            txt_file = os.path.join(output_dir, matching[0])
            
    with open(txt_file, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read().strip()

    return {
        "audio_path": os.path.abspath(audio_path),
        "txt_file": txt_file,
        "content": content,
        "elapsed_seconds": round(elapsed, 2)
    }

def main():
    parser = argparse.ArgumentParser(description="音频文件文本转写工具 (极速版)")
    parser.add_argument("audio_path", nargs="?", default="auto", help="目标音频文件路径")
    parser.add_argument("--model", default="auto", help="模型名称")
    parser.add_argument("--language", default="Chinese", help="语言")
    parser.add_argument("--output_dir", default=None, help="输出目录")
    parser.add_argument("--json", action="store_true", help="JSON 输出")

    args = parser.parse_args()

    try:
        res = transcribe_audio(
            audio_path=args.audio_path,
            model=args.model,
            language=args.language,
            output_dir=args.output_dir
        )
        if args.json:
            print(json.dumps(res, ensure_ascii=False, indent=2))
        else:
            print("--- 转写成功 ---")
            print(f"文件: {res['audio_path']}")
            print(f"耗时: {res['elapsed_seconds']} 秒")
            print(f"内容:\n{res['content']}")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
