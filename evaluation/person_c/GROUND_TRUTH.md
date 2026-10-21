# Person C：参考标签核查流程

本文件是标签核查流程。2026-10-21 已按此流程核查 Lang-1/3/4：真实标签、逐块证据和审阅理由位于 `real/`，已通过补丁映射核查及自动校验，组员人工复核仍为 pending。不要把模拟 labels.json 当成真实标签。

## 开始前取得的最小信息

- 团队固定的 Defects4J 版本和基准库 commit。
- 一个真实 bug ID，以及 A 使用的错误版源码/commit。
- 对应开发者生产代码修复补丁。
- A 的 method_id 命名规则及方法边界数据。若暂时没有解析器，先人工核查一个案例，记录位置，之后补精确 ID。

你可以先负责查补丁与标签，不必安装或运行整个覆盖率工具链。具体 bug 标签不能在版本和源码不一致时凭名称猜测。

## 每个 bug 的处理步骤

1. 登记 bug_id、基准版本、错误版和修复版的来源，保留原始补丁。确认这些材料对应 A 实际分析的版本。
2. 分开生产代码与测试修改。测试变动用于理解行为，不纳入生产方法的参考标签。
3. 看每个生产代码 diff hunk，在错误版源码中找所属方法；删除/替换行通常能直接定位。
4. 对只增加代码的 hunk，判断是否插入到一个已有方法内部。如果是，映射到错误版的该方法；不要把所有“新增行”都误判为“新增方法”。
5. 新增方法、字段修改、重命名、构造函数、内部类或解析歧义单独登记。对超出方法级评价范围的案例，按事先约定规则排除并保留理由；不能因为模型没找到才排除。
6. 去重得到 faulty_methods。与 A 候选/全方法清单的 ID 做精确匹配，检查是否存在方法名相同但参数不同的重载。
7. 标记 reviewed，并填写 source_note、核查人和证据位置。其他组员可以抽查一部分映射。

## 在 bug_tracker.json 中登记

建议每条 bug 记录包含：

```json
{
  "bug_id": "待团队确认的真实ID",
  "split": "dev",
  "environment_status": "pending",
  "coverage_status": "pending",
  "label_status": "pending",
  "buggy_revision": null,
  "fixed_revision": null,
  "patch_reference": null,
  "method_mapping_evidence": [],
  "validation_method": null,
  "exclusion_reason": null
}
```

tracker 是工作记录；评分器读取 manifest.json 与 labels.json。状态未确认时不要把它们写成已完成。

## 标签隔离

- 原始补丁、修复版代码和 labels.json 留在评估端。只向 B 提供错误版代码、候选和允许的测试上下文。
- C 可以访问评估标签来评分，但不要根据 eval 标签或模型在 eval 上的表现改 prompt、融合权重或筛选案例。
- prompt 调整和融合权重选择只使用 dev；调整完成后固定配置，再运行 eval。
- 这些是流程约定，不是此目录内的访问权限隔离；共享仓库时用清晰目录和输入白名单落实。

## 报告中使用的准确说法

“We derive method-level reference labels from developer patches, manually check ambiguous mappings, and document exclusions.”

这些标签是可复现的评估参照。补丁可能含配套修改，不能直接宣称每个被修改的方法都必然是根因，也不能据此宣称完全不需要人工核查。
