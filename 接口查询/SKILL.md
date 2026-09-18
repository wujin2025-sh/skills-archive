---
name: 接口查询
description: '低延时接口查询。在金融科技服务治理平台 (http://sg.gtht.com.cn/fwzl/interfaceManage/interfaceManage.html)
  中查询指定接口号或接口关键字的配置信息。

  触发词：低延时接口查询、接口查询、查询接口、interface-query、low-latency-query、7300780、7300780接口、interfaceManage。

  '
agent_created: true
disable: false
---

# 低延时接口查询 (SKILL.md)

本目录是一个独立的自动化运维技能包，用于在金融科技服务治理平台的 **“接口管理”** 中，查询指定的接口关键字（如接口号 `7300780` 等），并将查询结果以 Markdown 表格的形式输出。

---

## 1. 目录结构

此技能文件夹包含以下文件：
* `SKILL.md`：本说明文档。
* `scripts/low_latency_query.py`：核心 Python 自动化查询脚本。
* `scripts/config.json`：账号及平台配置文件。
* `scripts/.fintech_session.json`：（运行后自动生成）登录态 Session 缓存文件。

---

## 2. 配置文件说明 (`config.json`)

配置文件位于 `scripts/config.json`。该脚本默认会复用 `uat_accept` 技能的 `config.json`（如果该文件存在且包含正确的凭据），否则加载本地的 `config.json`：

```json
{
    "platform": {
        "name": "服务治理平台",
        "login_url": "https://www.gtht.com.cn/login.html?href=http://sg.gtht.com.cn/SSOVerify",
        "target_url": "http://sg.gtht.com.cn/fwzl/interfaceManage/interfaceManage.html",
        "goto_timeout_ms": 30000
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

---

## 3. 使用与运行指南

### 3.1 默认查询接口 (如 7300780)
```bash
/Users/wujin/.workbuddy/binaries/python/envs/default/bin/python /Users/wujin/.workbuddy/skills/接口查询/scripts/low_latency_query.py --keyword 7300780
```

### 3.2 参数化运行
* **指定关键字**：使用 `--keyword` 或 `-k` 传入需要查询的接口关键字。
* **过滤所属分组**：使用 `--groups` 或 `-g` 传入过滤的分组关键字，支持逗号分隔（如: `低延时,集中交易`）。
* **有界面运行（自动展开详情）**：添加 `--no-headless` 或 `-n` 参数，脚本在有界面模式下会自动点击匹配的第一条记录，弹窗展示接口详细信息，并保持浏览器开启状态，方便人工查看与操作。
* **查看帮助**：
  ```bash
  /Users/wujin/.workbuddy/binaries/python/envs/default/bin/python /Users/wujin/.workbuddy/skills/接口查询/scripts/low_latency_query.py --help
  ```
