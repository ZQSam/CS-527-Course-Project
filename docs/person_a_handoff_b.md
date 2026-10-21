# B 快速开始：使用 A 的模型输入

你负责上下文预算、提示词、LLM 重排、缓存、多次采样和融合。已采集的样本可以直接使用。

## 第一步：检查并读取数据

在仓库根目录执行；不需要 Docker、Java、模型服务或第三方 Python 包：

```bash
python3 scripts/prepare_sample.py --profile B
```

从 [`data/sample/B/index.json`](../data/sample/B/index.json) 遍历 `bugs`。
每个条目的 `path` 相对于 `data/sample/B/`，指向自包含的 `<bug_id>.json`。
例如 [Lang-1.json](../data/sample/B/Lang-1.json)。仓库首页提供了完整读取示例。

## 每份 JSON 中有什么？

| 字段 | 用途 |
| --- | --- |
| `bug_id`、`provenance` | bug、出错版本、源码 revision、覆盖率运行和工具版本 |
| `candidates` | Ochiai 顺序的候选方法，含 ID、源码、位置、分数和并列范围 |
| `failing_tests` | 失败测试源码、完整声明文件、错误、调用栈和原始报错 |
| `warnings` | 显式的数据警告 |

`candidates[].source` 是完整的方法声明和方法体。`failing_tests[].source` 是失败测试方法，
`source_file_text` 是其完整声明文件，可供读取 imports、fixtures 和 helpers。
`executed_class` / `declaring_class` 区分执行类与继承的声明类；`source_resolution` 记录定位方式。
源文件哈希使用原始文件字节；方法哈希使用 UTF-8 方法文本。

A 没有为了 token 限制截短方法。请保留原始 JSON，再在 B 的上下文构造阶段处理预算，
并保留失败测试和原始错误证据。完整测试文件可能较长，不要求全部塞进提示词。

## 输出接口

严格使用输入中的 `method_id`，每个候选恰好出现一次。建议 LLM 响应形状：

```json
{"ranking": ["<exact method_id>", "<next exact method_id>"], "top3_reasons": [{"method_id": "<exact method_id>", "reason": "one line"}]}
```

记录配置、随机种子、sample index、模型原始响应、token、耗时、状态和费用。
配置中的模型名、缓存、重复采样与融合由 B 负责。真实模型运行需具备缓存、dry-run 和金额上限。

`sbfl_rank` 是稳定显示顺序，`rank_min` / `rank_max` 才反映并列范围。
方法 ID 的规则见[数据约定](person_a_data_contract.md)，严格字段定义见
[JSON Schema](../configs/model_input.schema.json)。模型输入没有补丁标签或修复代码。
请先接通一个 bug，再使用完整共享样本与 C 对接评估。
