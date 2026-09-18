---
name: uat_accept
description: '进入 EOA 全连接平台的“我的草稿”列表，根据指定的“文种”进行过滤筛选（默认：UAT测试申请(需求)），遍历草稿项依次点击标题链接进入详情页，自动点击“提交”按钮，并在处理人弹窗中搜索指定的“审批人员”工号（默认：106881）进行选中并确认提交。极速运行，支持
  Session 复用与密码解密。

  触发词：uat_accept、UAT验收、提交UAT、UAT草稿提交。

  '
disable: false
---


# EOA UAT验收/草稿箱自动提交技能说明文档 (SKILL.md)

本目录是一个独立的自动化运维技能包，用于自动处理 EOA 系统中的 **“我的草稿”**，根据指定的 **文种** 进行过滤筛选，并自动执行提交。

---

## 1. 目录结构

此技能文件夹为独立包，包含以下文件：
* `SKILL.md`：本说明文档。
* `scripts/eoa_uat_accept.py`：核心 Python 自动化脚本。
* `scripts/config.json`：账号及平台配置文件。
* `scripts/.fintech_session.json`：（运行后自动生成）登录态 Session 缓存文件，用于免密快速二次运行。

---

## 2. 配置文件说明 (`config.json`)

请在运行脚本前确认 `config.json` 中的配置是否正确：

```json
{
    "platform": {
        "name": "全连接平台",
        "login_url": "https://www.gtht.com.cn/login.html?href=https%3A//www.gtht.com.cn/home.html",
        "home_url": "https://www.gtht.com.cn/home.html",
        "goto_timeout_ms": 15000
    },
    "account": {
        "username": "125360",
        "password": "ENC:gAAAAABqH4qJl-EAxY_sd1AbOQ_qcsfeF35ysPSVBrpzQh0YD8V9wgHh7srxeqU-rLeH3NqlVBaEIzwf5nSBTWxuNDSahEsrOg==",
        "username_placeholder": "工号|OA账号"
    },
    "browser": {
        "headless": true,
        "channel": "chrome",
        "slow_mo": 0,
        "viewport": {
            "width": 1440,
            "height": 900
        }
    }
}
```

> [!TIP]
> * `password` 可以直接填写**明文密码**（例如 `"your_password_here"`），也可以填写以 `ENC:` 开头的加密密文。
> * 如果使用密文，脚本会自动尝试读取本地的 `~/.workbuddy/.meeting_skill_key` 密钥进行解密。

---

## 3. 功能概述

通过 Playwright 驱动浏览器：
1. **自动登录**：优先读取本地 `.fintech_session.json` 尝试免密直接进入首页；如果 Session 失效或不存在，则读取 `config.json` 中的账号密码完成表单登录，并保存最新 Session。
2. **直达草稿箱**：自动进入 **我的草稿** 列表页面。
3. **文种过滤**：在文种过滤输入框中输入指定文种并按回车过滤（默认：`UAT测试申请(需求)`）。
4. **循环提交**：
   * 自动识别列表中的第一条草稿，点击标题链接跳转进入详情页新标签页。
   * 在详情页内自动定位并点击“提交”按钮。
   * 在弹出的处理人选择框中输入指定人员的工号（默认：`106881`）进行精确搜索。
   * 选中搜索出来的人员，点击提交确认按钮。
   * 自动关闭新标签页，并刷新主草稿列表。
   * 循环处理下一条，直至匹配的草稿全部处理完毕。

---

## 4. 运行环境准备

在首次运行前，请确保系统已安装 Python 3 环境，并安装了 `playwright` 及其浏览器依赖：

```bash
pip3 install playwright cryptography
playwright install chrome
```

---

## 5. 使用与运行指南

### 5.1 默认极速提交 (处理 UAT 验收单并提交给周尤珠 `106881`)
进入 `scripts/` 目录运行脚本，脚本会默认加载同目录下的 `config.json`：
```bash
cd scripts && /usr/local/bin/python3 eoa_uat_accept.py
```

### 5.2 通用参数化运行 (无需修改代码)
此脚本支持丰富的命令行参数，便于您根据不同流程切换文种、审批人或运行模式：
* **更换文种与接收人**：
  ```bash
  cd scripts && /usr/local/bin/python3 eoa_uat_accept.py --doc-type "升级单" --recipient "108728"
  ```
* **开启有界面调试运行 (可视排查)**：
  使用 `--no-headless` 可以显示浏览器界面，并使用 `--slow-mo` 设置每一步操作延迟（例如 500 毫秒），方便直观观察执行过程：
  ```bash
  cd scripts && /usr/local/bin/python3 eoa_uat_accept.py --no-headless --slow-mo 500
  ```
* **查看完整参数说明**：
  ```bash
  cd scripts && /usr/local/bin/python3 eoa_uat_accept.py --help
  ```
