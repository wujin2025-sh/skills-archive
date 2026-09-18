---
name: freedomain
description: DigitalPlat FreeDomain / Domain-OSS 免费域名与 DNS 自动化管理技能。支持通过 Agent 自然语言或命令行自动化管理域名注册、DNS解析记录增删改查（A、AAAA、CNAME、TXT、MX等）、ACME
  DNS-01 SSL证书验证、以及服务的启动、停止、重启与健康状态监控。
disable: false
---


# 🌐 FreeDomain 自动化管理与服务运维技能

本技能用于通过 Agent 自然语言对话或底层 CLI 脚本，全面自动化管理 **DigitalPlat FreeDomain / Domain-OSS** 域名、DNS 解析及**本地服务的启动、停止与重启**。

---

## 🎯 核心能力与操作矩阵

1. **服务生命周期运维 (Service Control)**：
   - 🚀 **启动服务 (`service start`)**：后台以守护进程模式启动 Domain-OSS Web 服务与个人驾驶舱（支持自定义端口与主机）。
   - 🛑 **停止服务 (`service stop`)**：优雅停止 Gunicorn 主进程及所有 Worker 子进程，自动清理 PID 文件。
   - 🔄 **重启服务 (`service restart`)**：平滑重启服务以热加载模板与配置。
   - 📊 **服务状态 (`service status`)**：查看服务在线状态 (ONLINE/OFFLINE)、PID 列表、访问端口与日志。
2. **域名管理 (Domains)**：
   - 查看名下拥有的二级域名列表与状态。
   - 申请注册新的免费二级域名（如 `neowu.dpdns.org`、`cockpit.dpdns.org` 等）。
   - 查看指定域名详情、注销/删除域名。
3. **DNS 解析记录管理 (Records)**：
   - 查看域名下的所有 DNS 解析记录（A, AAAA, CNAME, TXT, MX, SRV, CAA, NS）。
   - 添加或修改解析记录（支持 `@`、`www`、`api` 等子域，自定义 TTL 与权重优先级）。
   - 删除过期的 DNS 记录。
4. **SSL / ACME 挑战自动化 (ACME DNS-01)**：
   - 自动发布 `_acme-challenge` TXT 记录以配合 Let's Encrypt / ZeroSSL 申请免费证书，验证后一键清理。

---

## 🛠️ CLI 命令行速查参考

底层客户端脚本位于：`~/.workbuddy/skills/freedomain/scripts/freedomain_cli.py`

### 1. 本地服务启停与运维
```bash
# 启动服务 (默认端口 8080)
python3 ~/.workbuddy/skills/freedomain/scripts/freedomain_cli.py service start

# 自定义端口启动 (如端口 8090)
python3 ~/.workbuddy/skills/freedomain/scripts/freedomain_cli.py service start --port 8090

# 停止服务
python3 ~/.workbuddy/skills/freedomain/scripts/freedomain_cli.py service stop

# 重启服务
python3 ~/.workbuddy/skills/freedomain/scripts/freedomain_cli.py service restart

# 查看服务运行状态
python3 ~/.workbuddy/skills/freedomain/scripts/freedomain_cli.py service status
```

### 2. 域名操作
```bash
# 列出名下所有域名
python3 ~/.workbuddy/skills/freedomain/scripts/freedomain_cli.py domains list

# 申请注册新二级域名 (例如 neowu, zone_id 默认为 1)
python3 ~/.workbuddy/skills/freedomain/scripts/freedomain_cli.py domains create neowu --zone-id 1

# 查看域名详情
python3 ~/.workbuddy/skills/freedomain/scripts/freedomain_cli.py domains get 2

# 删除域名 (清空该域名下全部 DNS 记录)
python3 ~/.workbuddy/skills/freedomain/scripts/freedomain_cli.py domains delete 2
```

### 3. DNS 解析管理
```bash
# 列出指定域名 (ID: 2) 的全部解析记录
python3 ~/.workbuddy/skills/freedomain/scripts/freedomain_cli.py records list 2

# 添加 A 记录 (@ 根指向 127.0.0.1)
python3 ~/.workbuddy/skills/freedomain/scripts/freedomain_cli.py records add 2 --type A --name @ --content "127.0.0.1"

# 添加 CNAME 记录 (www 别名)
python3 ~/.workbuddy/skills/freedomain/scripts/freedomain_cli.py records add 2 --type CNAME --name www --content "neowu.dpdns.org"

# 删除解析记录
python3 ~/.workbuddy/skills/freedomain/scripts/freedomain_cli.py records delete 2 101
```

### 4. ACME 证书挑战
```bash
# 自动发布 ACME TXT 挑战
python3 ~/.workbuddy/skills/freedomain/scripts/freedomain_cli.py acme add 2 --value "kX9Z...挑战值"

# 清理 ACME 挑战
python3 ~/.workbuddy/skills/freedomain/scripts/freedomain_cli.py acme delete 2 <token>
```

---

## 🤖 Agent 典型自然语言触发

* 🗣️ **“启动 FreeDomain 服务”** / **“把域名服务开一下”** 👉 Agent 执行 `service start`。
* 🗣️ **“停止 FreeDomain 服务”** / **“关掉域名面板”** 👉 Agent 执行 `service stop`。
* 🗣️ **“重启 FreeDomain 服务”** 👉 Agent 执行 `service restart`。
* 🗣️ **“查看 FreeDomain 服务状态”** 👉 Agent 执行 `service status` 并汇报 PID 与端口。
* 🗣️ **“帮我申请域名并加解析”** 👉 Agent 调用 API 全自动完成。
