# 评估端数据格式与规则

此格式是评估器的输入规范。你已发给组员的接口约定继续有效。若 A/B 字段名不同，写一层转换即可；不要让他们为评估器重新实现整条流水线。

所有 JSON 均使用 UTF-8。每个配置一个预测文件，每个 bug 一条记录。

## 共同头部

```json
{
  "schema_version": 1,
  "data_kind": "real",
  "dataset": {
    "name": "Defects4J",
    "version": "REPLACE_WITH_TEAM_VERSION",
    "revision": "REPLACE_WITH_DEFECTS4J_COMMIT"
  }
}
```

三个文件的 dataset 对象必须完全一致。真实运行前必须替换占位符。`revision` 是基准库的固定 Git commit；每个 bug 的错误/正确版本另在标签证据中登记。

`data_kind: synthetic` 仅用于软件测试，命令必须显式添加 `--demo`。这项检查依赖诚实标注，无法自动鉴定数据是否真实。

## 实验清单 manifest.json

在共同头部之后添加 `bugs` 数组。以下 ID 仅为结构示意，不代表已选定真实样本：

```json
{
  "bugs": [
    {
      "bug_id": "PROJECT-ID",
      "split": "eval",
      "included": true,
      "exclusion_reason": null
    }
  ]
}
```

- `split` 只能是 `dev` 或 `eval`。默认只评分 eval。
- included=false 必须有排除理由。先按技术条件筛选并冻结清单，再查看方法效果。
- 使用未登记 bug ID、重复 ID 会报错，避免意外混入其他实验。
- A 的覆盖率采集失败在冻结前作为基础设施状态记录；冻结后不能因 B 没有输出而改变分母。

## 参考标签 labels.json

共同头部之后添加：

```json
{
  "records": [
    {
      "bug_id": "PROJECT-ID",
      "status": "reviewed",
      "faulty_methods": ["org.example.Stats#average(int[])"],
      "source_note": "实际补丁路径/标识、错误版源码位置及人工核查记录"
    }
  ]
}
```

选入本次评分的每个 bug 都必须有 reviewed 标签、非空去重的方法列表及来源说明。未核查就保持 pending，评分器会拒绝评分；不能把不确定的标签临时当成正确答案。

method_id 以 A 的解析器规则为准。建议包含完整类名、方法名和参数类型；必须统一构造函数、内部类、数组、泛型和重载的表示。这里不做模糊匹配或只按方法名匹配。

## 预测 predictions.json

共同头部之后添加以下字段。所有名称均为结构示例：

```json
{
  "configuration_id": "llm_single",
  "ranking_scope": "candidates",
  "configuration": {
    "model": "实际模型及固定版本",
    "model_parameters": {},
    "prompt_version": "实际 prompt 版本或哈希",
    "sampling_count": 1,
    "shuffle_seed": 42,
    "fusion_weight": null,
    "code_revision": "实际代码 commit"
  },
  "records": [
    {
      "bug_id": "PROJECT-ID",
      "status": "ok",
      "candidate_method_ids": ["org.example.Stats#sum(int[])", "org.example.Stats#average(int[])"],
      "ranking": ["org.example.Stats#average(int[])", "org.example.Stats#sum(int[])"],
      "usage": {
        "input_tokens": null,
        "output_tokens": null,
        "cost_usd": null,
        "latency_seconds": null
      }
    }
  ]
}
```

示例只有两个方法便于阅读；正式 K=20 的实验应保留实际 20 个候选。方法总数不足或预算无法容纳时要预先约定规则并记录，不可悄悄删除候选。

- `ranking` 是已经排好序的 method_id 列表。候选模式下必须是候选集合的完整排列。
- `ranking_scope: full` 声明传入完整的方法排名。它是生产端承诺，评估器无法单靠 JSON 验证整个仓库的方法全集。
- 允许的 status：`ok`、`call_error`、`parse_error`、`timeout`、`not_run`。
- 候选重复、预测重复、遗漏候选或生成不存在的候选，标记 invalid 并计零分。
- 缺少整个 bug 的预测记录，标记 missing 并计零分。
- 出错时填 `error`，有候选和已消耗资源时仍保留，不要因为失败就清零费用。
- 未知费用写 null，不写 0。纯 SBFL 的 LLM token/API 费用可以明确填 0；运行耗时应实测。
- 多次采样的 usage 汇总该配置实际全部调用及重试消耗；仅改变融合权重复用回答时，标明复用关系，不将复用报告的逻辑成本相加当作实际账单。
- 必须记录具体模型、prompt、采样和融合配置；字段虽不全是评分器硬校验项，缺少它们会妨碍实验复现。

## 指标与公平比较

每个 bug 的参考方法集合为 G，有序预测为 R。找到 R 中第一个属于 G 的方法，其排名为 r。

- Top-k：r≤k 得 1，否则 0；全体 included eval bugs 取平均。
- 完整 MRR：r 存在时取 1/r，否则 0，再取平均。只在所有配置都提供完整排名时启用 `--rank-cutoff 0`。
- MRR@20：只在 R 前 20 项找命中，其余计 0。这是默认设置，便于比较只提供候选排名的早期版本。
- 同一个 bug 有多个参考方法时，按第一个命中评分，不要求一次找到全部根因。
- 候选命中率：参考集合与候选集合有交集就命中。只有全部样本候选已知、且候选数均为 20 时，直接称 Recall@20。候选不全时仅给 observed 命中率和覆盖数量，全数据集候选召回率显示 NA。
- 默认所有缺失、调用失败和无效输出计零分。若改为回退到 Ochiai，另建显式配置，并同时报告回退次数；不要修改现有预测来掩盖失败。
- 所有配置的 Top-k 和 MRR 使用同一个清单分母。候选集不一致会在配对报告中标记，此时不能把差异都归因于重排序。
- Ochiai 分数并列时，团队固定一种规则，例如按稳定 method_id 升序。不要看到标签后再挑有利顺序。
- 完整 MRR 如需 B 的全排名，可在事先约定后将重排候选置顶、其余方法保留 A 的原始顺序；这是新增的输出约定，必须记录。

## 模拟演示的手算答案

正式计分的模拟样本为 DEMO-001 至 DEMO-006。DEMO-007 是 dev，DEMO-008 是明确排除的示例。

| 配置 | N | Top-1 命中 | Top-3 命中 | MRR@20 |
|---|---:|---:|---:|---:|
| 模拟 Ochiai | 6 | 2 | 5 | 5/9 ≈ 0.5556 |
| 模拟单次 LLM | 6 | 1 | 2 | 0.25 |

单次 LLM 包含一个调用失败、一个重复候选导致的 invalid、一个缺失记录，它们都计入 N=6。模拟数据刻意包含退步案例，不代表真实方法优劣。
