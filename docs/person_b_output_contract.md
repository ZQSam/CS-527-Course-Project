# Person B → C：模型结果接口（version 1.1）

B 读取 A 的 `data/sample/B/`，输出每个 bug 的 SBFL / 单次 LLM / 多次采样平均 / 融合排名，以及完整的成本和异常记录。
**所有排名都是输入 `candidates[].method_id` 的完整排列（20 个，原样 ID，不改名、不遗漏、不重复）**，
由 `rerank/runner.py::validate_result` 在写盘前强制检查。字段定义见
[`configs/rerank_output.schema.json`](../configs/rerank_output.schema.json)。

**1.1 相对 1.0 只做增量**：排名、融合、成本字段含义不变；新增 `degradations[]`、`evidence_summary`、
`samples[].top3_reasons[].evidence`、`samples[].filled_from_sbfl`、`config.effective_num_samples`、
`config.transport`。已提交的 1.0 结果文件（`results/rerank/*-v1-*`）保持原样，schema 同时接受两种版本。

## 目录

```
results/rerank/
  index.json / README.md          # 所有 run 的索引与概览（scripts/summarize_rerank.py 生成）
  <run_id>/
    <bug_id>.json                 # 每个 bug 一份完整结果（下文）
    summary.json                  # 本 run 的配置、逐 bug 状态与成本合计、累计花费
    calls.jsonl                   # 每次 API 尝试一行：cache_key、命中、token、费用、耗时、状态
    fusion_weighted_rank.json     # scripts/fuse.py 离线权重扫描（可选）
    fusion_rrf.json
```

模型原始请求与响应完整保存在本地缓存 `.work/llm_cache/`（不入库）；每个 sample 的
`attempts[].raw_response` 和 sample 0 的 `prompt_text` 已写入结果文件，足以复核。

## `<bug_id>.json` 关键字段

| 字段 | 含义 |
| --- | --- |
| `input_sha256` | 对应 A 的输入文件哈希；输入变化后旧结果失效 |
| `status` | `complete`（全部 sample 成功）/ `partial` / `failed` |
| `config` | provider、模型、effort、max_tokens、prompt 版本、采样数与种子、上下文与融合设置 |
| `context.shown` / `context.dropped` | 送入模型的候选（Ochiai > 0）与未送入的零分候选 |
| `rankings.sbfl` | A 的原始 Ochiai 顺序（基线，原样） |
| `rankings.single` | sample 0 的 LLM 排名（单次重排配置） |
| `rankings.mean` | 成功 sample 的平均名次排名，平局按 SBFL 顺序 |
| `mean_rank_stats` | 每个方法的平均名次 / 标准差，以及 sample 间 Kendall τ、top-1 一致率 |
| `fused.single[w]` / `fused.mean[w]` | 融合排名，`w` 为 LLM 权重（`"0.00"` = 纯 SBFL，`"1.00"` = 纯 LLM） |
| `samples[]` | 每次采样：种子、展示顺序、C01… 标签映射、状态、问题、完整排名、前三理由、每次尝试的 token/费用/耗时/原始响应 |
| `cost` | 调用次数、缓存命中、token、费用（`cost_usd` 为生成结果的原始成本，`paid_usd_this_run` 为本次实际新花费） |
| `config.prompt_version` | `v1`（1.0 结果使用）或 `v2`（要求理由引用行号，默认） |
| `config.effective_num_samples` | 实际计划的采样数；开启 `sampling.adaptive` 时可能小于 `num_samples` |
| `config.transport` | `messages`（逐条调用）/ `batch`（Message Batches，半价）/ `dry_run` |
| `degradations[]` | 本 bug 的所有降级事件（见下表），每条含 `kind`、`stage`，sample 相关事件含 `sample_index` |
| `samples[].top3_reasons[].evidence` | 理由证据门禁结果（见下文），**只做标注，不改变任何排名** |
| `samples[].filled_from_sbfl` | 模型漏排、按 SBFL 顺序补在末尾的展示候选 |
| `evidence_summary` | 成功 sample 的全部理由按门禁状态计数，以及 `grounded_rate`、`citation_rate` |

### `degradations[].kind`

| kind | stage | 含义 |
| --- | --- | --- |
| `zero_score_omitted` | context | `count` 个 Ochiai = 0 的候选未送入模型（附在排名末尾） |
| `zero_score_shown_for_minimum` | context | 非零候选不足 2 个，补入了 `count` 个零分候选 |
| `method_truncated` | context | 方法体超出预算被截断（`original_lines` → `kept_lines`，调用栈行优先保留） |
| `helpers_omitted_for_budget` | context | 测试 helper 方法因预算省略 |
| `test_source_omitted` | context | 超过 `context.max_full_tests` 的 `count` 个失败测试只给出调用栈 |
| `context_over_budget` | context | 截断下限（每候选 400 字符）仍超出 `token_budget` |
| `adaptive_single_sample` | sampling | 展示候选 ≤ `single_sample_max_shown`，只采样 1 次 |
| `budget_abort` | budget | 累计花费上限阻止了第 `sample_index` 个及之后的 `samples_skipped` 个 sample |
| `hit_max_tokens` / `model_refused` | model | 某次尝试因 `max_tokens` 截断 / 被模型拒答 |
| `sample_retried` | model | 该 sample 发起了纠错重试（`attempts` 次） |
| `sample_repaired` | model | 排名可用但有问题；`filled_from_sbfl` 个候选按 SBFL 顺序补齐 |
| `sample_failed` / `sample_error` | model | 不可用（解析失败 / API 或 batch 错误），该 sample 使用 SBFL 顺序兜底，不进入 `mean` |

### 理由证据门禁（`rerank/evidence.py`）

从理由文本中提取 `L684`、`L471-L474`、`line 129`、`lines 591-596`（范围只取两个端点），并与该候选
**实际展示的行号**（截断后被省略的行不算）比对：

| status | 含义 |
| --- | --- |
| `grounded` | 引用了该候选展示的行，且没有无法核实的行号 |
| `partial` | 引用了该候选展示的行，但也有无法核实的行号（`unverified`）。同一源文件中其他候选展示过的行（`sibling_candidate`，如解释被调方时引用调用方 C01 的行）视为已核实 |
| `test_only` | 只引用了失败测试源码、项目调用栈或同文件其他候选中出现的行号，没有引用该候选自身的行 |
| `ungrounded` | 没有引用该候选的行，且有无法核实的行号 |
| `no_citation` | 没有引用任何行号 |

`stack_marked` 列出被引用且带 `>>` 调用栈标记的行。测试行号只按数字比对、不区分文件，属于启发式判断。
v1 prompt 不要求引用，因此 v1 结果的 `citation_rate` 很低（重放 6 个 v1 run：≤ 13%）；这不代表理由错误。

## C 评估时需要注意

1. **零分尾部是并列组，不是模型判断。** `rankings.*` 中位于 `len(context.shown)` 之后的方法是
   Ochiai = 0 的并列候选（按字母序附在末尾）。真实缺陷若落在这里，应按 A 的 `rank_min`/`rank_max`
   并列规则计分，不要把字母序当作名次差异。
2. **融合的平局规则。** `weighted_rank` 分数相同时按 SBFL 顺序打破，因此 `w = 0.5` 时两个候选的对调
   会回落到 SBFL 顺序。报告时请说明这一点，或用 `scripts/fuse.py` 扫描更细的权重。
3. **调权重只用开发集。** 融合结果可随时离线重算（`scripts/fuse.py`），不需要再次调用模型；
   请用 C 划定的开发 bug 选权重，在其余 bug 上报告。
4. **失败 sample。** `status` 为 `failed`/`error` 的 sample 使用 SBFL 顺序兜底，不参与 `mean`；
   `repaired` 表示模型漏排的候选按 SBFL 顺序补在末尾。两者都计入异常统计。
5. **成本口径。** 每个 bug 的成本取 `cost.cost_usd`（含思考 token，按配置中的单价表计算）；
   `transport = batch` 的调用按 `batch.price_multiplier`（0.5）计价，`attempts[].batch_id` 记录所属 batch。
6. **降级与证据只用于分析。** 可按 `degradations` 过滤或分层（例如排除含 `method_truncated` 的 bug 做敏感性分析），
   `evidence` 可用于报告理由可信度；两者都不影响已给出的排名。

## 复现

```bash
python3 -m venv .venv   # 或 uv venv --python 3.11 .venv；需要 Python 3.10+
.venv/bin/pip install anthropic==0.125.0
# .env 中写入 ANTHROPIC_API_KEY=...（已在 .gitignore 中）
.venv/bin/python scripts/run_rerank.py --model haiku --samples 5 --dry-run          # 先估算成本
.venv/bin/python scripts/run_rerank.py --model haiku --samples 5 --run-id haiku-v2-s5      # v2 prompt（默认）
.venv/bin/python scripts/run_rerank.py --model haiku --samples 5 --batch --run-id haiku-v2-s5-batch  # 半价，异步
.venv/bin/python scripts/run_rerank.py --model haiku --samples 5 --prompt-version v1 --run-id haiku-v1-s5  # 从缓存重放 v1
.venv/bin/python scripts/fuse.py --run results/rerank/haiku-v1-s5 --weights 0,0.1,0.2,0.3,0.4,0.5,0.6,0.7,0.8,0.9,1
.venv/bin/python scripts/summarize_rerank.py
.venv/bin/python -m unittest tests.test_rerank   # 离线，不需要 API key
```

重复运行同一配置全部命中缓存，花费为 0。累计花费记录在 `.work/llm_cache/ledger.jsonl`，
超过 `configs/rerank.json` 的 `budget.max_cost_usd`（当前 $25）会在调用前停止。

### 配置（`configs/rerank.json`，schema 1.1）

- 原代码常量已移入配置，取值与 v1 相同：`context.max_full_tests = 3`、`context.per_candidate_overhead_chars = 40`、
  `budget.dry_run_output_tokens = 600`。
- `prompt_version`：`v2`（默认）；`--prompt-version v1` 生成与 v1 完全相同的请求，已有 v1 run 全部命中缓存。
- `sampling.adaptive = {"enabled": false, "single_sample_max_shown": 2}`：默认关闭以保持实验可复现；
  `--adaptive` 开启后，展示候选 ≤ 2 的 bug 只采样 1 次（记入 `degradations`）。
- `--batch`：未命中缓存的请求经 Message Batches API 提交（`batch.price_multiplier = 0.5`），结果写入同一缓存与账本。
  按轮次进行：每轮先跑完整管线、收集未缓存请求、提交一个 batch、等待并回填，再进入下一轮（例如校验失败后的纠错重试），
  直到某一轮不再产生新请求。提交前按最坏情况（`max_tokens` 输出 × 折扣）检查花费上限；batch 清单写在
  `batch.manifest_dir`，进程中断后重跑会先等待并回填未完成的 batch，不会重复付费。errored/expired 的请求
  记为 `sample_error`（SBFL 兜底），重跑时会重新提交。
