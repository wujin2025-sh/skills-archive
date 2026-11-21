# ba-to-dev 外部配置与偏好管理（外置参考）

> **原则：配置永远放在外部持久目录，升级 Skill 本体不丢用户偏好、不重问旧字段。**
> 默认不初始化也不影响 `ba-to-dev` 正常运行（未初始化时按默认全开处理，不报错）；仅当用户命中 `CONFIG_MANAGEMENT` 意图时加载本参考。

- **配置路径（固定）**：`~/.workbuddy/skill-data/ba-to-dev/config.json`（与技能安装目录分离；`.chat`↔`.workbuddy` 共享用户主目录，改一处即生效）。
- **绝不写入 Skill 安装目录**（`SKILL.md` / `scripts/` 下不落任何用户配置）。
- **当前 `config_version = 1`**，默认键：

| 键 | 类型 | 含义 |
| :-- | :-- | :-- |
| `search.business_rule` | bool | openviking 业务规则域开关（默认 true） |
| `search.code_lookup` | bool | CBM 代码图谱域开关（默认 true） |
| `search.data_verify` | bool | dbq 数据库域开关（默认 true） |
| `system_list` | str | 权威系统清单 CSV 路径 |
| `template` | obj | 预留模板偏好（当前空） |

- **命令**：`python3 ~/.workbuddy/skills/ba-to-dev/scripts/config_manager.py --init / --status / --get <key> / --set <key> <val>`。
- **升级迁移**：探测到 `config_version` 旧时自动 `.bak_v旧版本` 备份并迁移（**旧字段保留，仅补新字段默认值，绝不重问已存在字段**）；普通用户只需对话提供偏好，无需手改 JSON。
