---
name: epic-create
description: 根据给定的需求编号或需求 URL，参考 PG202204-0269 等标准史诗，在国泰海通金融科技平台自动创建史诗并绑定需求。史诗名称由需求标题自动精炼提炼，计划周期默认为当日到 2 个月后，所属工程集、标签与部门自动继承参考史诗。
triggers:
  - 创建史诗
  - 自动创建史诗
  - 需求转史诗
  - 史诗创建
  - epic-create
  - create_epic
---

# 史诗自动创建技能 (epic-create)

根据需求编号 (R2604130077) 或需求详情页 URL，自动在国泰海通金融科技平台 (`fintech.gtht.com.cn`) 创建史诗 (Epic)，并自动完成需求关联与属性对齐。

## 功能特性
1. **智能标题精炼**：自动解析需求标题，清除 `【业务需求】`、`【两融清算】`、`集中营运` 等前缀修饰，提炼核心史诗名称。
2. **要素继承对齐**：参考 `PG202204-0269` 史诗（大新一代需求史诗集合、`CX-两融` 标签、`融资融券部` 等），确保史诗归类规范。
3. **计划周期自动化**：起始时间设为当日 (`YYYY-MM-DD`)，结束时间设为 2 个月后 (`YYYY-MM-DD`)。
4. **全自动关联**：史诗创建成功后，自动调用双层后端接口将需求列表即时绑定至该史诗。

## 使用方法

### 命令行调用
```bash
python3 /Users/wujin/.workbuddy/skills/epic-create/scripts/create_epic.py <需求编号/URL1> <需求编号/URL2> [options]
```

### 参数说明
- `demands`: 1 个或多个需求编号 (如 `R2604130077`) 或需求 URL 链接 (如 `https://fintech.gtht.com.cn/kjpt/DemandManage/details?demandId=R2604130077&flag=1`)
- `--reference`: 参考史诗编号 (默认: `PG202204-0269`)
- `--name`: 自定义史诗名称（如不提供则自动根据需求标题精炼）
- `--dry-run`: 试运行模式，仅进行参数解析与创建预览，不进行实际 API 提交

### 示例
```bash
# 单需求或多需求创建史诗
python3 /Users/wujin/.workbuddy/skills/epic-create/scripts/create_epic.py R2604130077 R2604090030

# 传入需求 URL
python3 /Users/wujin/.workbuddy/skills/epic-create/scripts/create_epic.py "https://fintech.gtht.com.cn/kjpt/DemandManage/details?demandId=R2604130077&flag=1" "https://fintech.gtht.com.cn/kjpt/DemandManage/details?demandId=R2604090030&flag=2"
```
