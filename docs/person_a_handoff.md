# Person A 简短交接报告

## 已完成

A 已固定 Defects4J / Java / GZoltar 环境，在 Lang-1、Lang-3、Lang-4 复现失败测试，
完成逐测试覆盖率、行级 Ochiai / DStar、方法内最大行分数排名，并提取候选源码、失败测试、错误和调用栈。
完整数量与验证结果见 [`results/shared_sample/summary.json`](../results/shared_sample/summary.json)。

## 交给 B

- 先读 [B 快速开始](person_a_handoff_b.md)，执行 `python3 scripts/prepare_sample.py --profile B`。
- 输入为 `data/sample/B/index.json` 和每个 bug 的 JSON；不需要重新采集覆盖率。
- 请原样使用 method ID，先接通一个 bug 的提示词和重排，再加入缓存、采样和融合。
- 输出需保留配置、种子、token、耗时、状态、费用及原始响应，交给 C 做统一评估。

## 交给 C

- 先读 [C 快速开始](person_a_handoff_c.md)，执行 `python3 scripts/prepare_sample.py --profile C`。
- 从 `.work/sample/C/index.json` 读取完整排名、覆盖率、buggy 源码快照、成功清单和失败记录。
- 请复用 `fl/java.py` 的 method ID，完成补丁标签与排除审核，再确定并列排名和 Top-k/MRR 的评估规则。
- 将 B 的输出与 Ochiai / DStar 比较；扩大批量前先完成同一个真实 bug 的全流程对接。

## 共同注意

- 接口以 [数据约定](person_a_data_contract.md)和 [JSON Schema](../configs/model_input.schema.json) 为准。
- 这是中期小样本交接；更广泛的 Lang/Math 等实验尚待开展。
- 模型输入不含修复补丁与标签；C 单独管理正确答案。
- 已修复的环境/采集失败保留为历史证据，不作为方法级 benchmark 排除。
- 本机 `AGENTS.md`、依赖、工作 checkout、个人临时文件及旧版交接包没有提交到 GitHub。

## 可直接发给队友的消息

> A 的小批量数据和代码已上传，包含 Lang-1 / Lang-3 / Lang-4。请先看仓库首页。
> B 从 `data/sample/B/index.json` 读取候选源码和失败测试信息；C 运行
> `python3 scripts/prepare_sample.py --profile C`，从 `.work/sample/C/index.json`
> 读取完整基线、覆盖率、源码快照和失败记录。method ID 和 JSON 接口已经统一。
> 我们先接通一个 bug 的 LLM→标签→评估流程，再扩大批量。
