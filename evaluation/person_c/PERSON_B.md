# B 输出适配与评分

`import_person_b.py` 读取 B 提交中的 JSON，转换为 C 的标准预测，再复用 `evaluate.py` 评分。仅需 Git 和 Python 3.10+ 标准库；不导入 B 的程序、不调用模型、不需要 API key。B 分支尚未合入 main 时也可运行。

## 重现当前结果

从仓库根目录执行：

```bash
git fetch origin person-b/llm-rerank-mid
python3 evaluation/person_c/import_person_b.py \
  --b-ref c753909d4582c46a9899bd99e893d2b412d662b5 \
  --manifest evaluation/person_c/real/data/manifest.json \
  --labels evaluation/person_c/real/data/labels.json \
  --baseline evaluation/person_c/real/data/ochiai.json \
  --baseline evaluation/person_c/real/data/dstar.json \
  --split dev \
  --output-dir evaluation/person_c/runs/b-pilot
```

输出目录必须不存在。默认 split 是 `eval`，当前全 dev 清单会拒绝默认运行。`--b-ref` 必填，可给已拉取的分支名，但结果始终记录解析后的完整 commit；正式复现使用上述固定 commit。分支将来变化时，先确保该历史 commit 仍可获取。`--b-repo` 可指定另一个本地仓库，默认当前目录。

默认读取该提交中 `results/rerank/*/summary.json` 对应的所有 run。可重复添加 `--run haiku-v1-s5 --run opus-v2-s5` 来选择事先确定的配置。不会读取工作区未提交的 B 文件。

生成：

- `predictions/<run>/<variant>.json`：每个配置一个 C 格式文件，保留 B 配置、展示/省略数量、降级记录、实际采样状态与用量。
- `scores.json`：完整评分器输出，包括配置、每例得分和配对候选集比较。
- `summary.json`：全部配置汇总、每例排名/得分/用量、输入哈希、B commit、实现哈希和异常说明。
- `report.md`：便于阅读的得分表。

大型预测文件留在忽略目录 `runs/`，可以离线重建。当前提交仅保存 [汇总报告](real/results/person_b/report.md) 和 [汇总 JSON](real/results/person_b/summary.json)，原始请求与响应仍以 B 的固定提交为准。

## 适配规则

支持 B `rerank_result` schema `1.0` / `1.1`、当前 Anthropic provider 和 `weighted_rank` / `rrf` 融合。新增 provider/schema 需显式扩展并测试。会核对 A 输入 SHA-256、benchmark release/commit、bug/run ID、候选分区、SBFL 顺序、配置一致性；独立重算平均名次与已保存融合权重。输入身份错误、未知 schema 或候选来源错误时停止，不写出结果。

这是**文件接口与评分校验**。它不重新构造提示词、不重新解析原始响应、不认证 API 请求是否确实由供应商执行，也不验证理由的因果正确性。脚本不会运行输入中的代码。可选 `fusion_*.json` 离线扫描不作为评分输入，本次只评每个结果 `config.fusion.weights` 声明的配置。

| 情况 | C 主评分处理 |
|---|---|
| single | sample 0 必须为 `ok`，且保存排名是完整候选排列并与 sample 一致 |
| mean | 所有实际计划的 sample 都必须为 `ok`，保存排名必须与平均名次重算一致 |
| 自适应采样 | 采用 `effective_num_samples`；旧 schema 缺少该字段时采用 `num_samples` |
| repaired / 补排候选 | `parse_error`，计零分；不当作无异常的模型排序 |
| failed / API error / timeout | 映射到 `parse_error` / `call_error` / `timeout`，计零分 |
| 预算中止、缺少计划 sample | 对受影响配置记 `not_run`；single 若已成功可正常计分 |
| 缺整个 bug 文件 | 保留在 manifest 分母，评分器记 `missing` |
| 排列重复、遗漏候选、保存聚合/融合不一致 | 受影响配置记 `parse_error`，计零分 |
| dry run / fake provider | 拒绝导入真实评分 |

所有融合配置继承对应 single/mean 的成功要求，包括权重 0 的配置；独立 SBFL baseline 始终由 C baseline 文件评分。此严格口径比 B 的“成功 sample 子集均值、repaired 可用”保守，避免隐式混入兜底。当前 119 个 sample 全部 `ok`，因此两种口径在当前批次没有差异。后续若要评估 repaired 或 SBFL fallback，新增明确命名的配置，并单独报告异常数量。

同分继续沿用 C 已固定的稳定顺序，mean 平局按输入 SBFL 顺序，fusion 按 B 定义的候选内 SBFL 平均名次计算、同分按 SBFL 展示顺序打破。未展示的零分候选属于确定性附加尾部，不属于模型判断；本适配器不按标签改用有利的并列位置。下一批需另做预先约定的 tie sensitivity 分析。

## 用量与延迟

- single 统计 sample 0 的全部尝试；mean 统计该 bug 全部尝试，包括重试与失败。融合复用相应来源的用量，不产生新调用。
- token、费用、耗时任一尝试未知，相应总量为 `null`，不改写为零。无尝试证据时也不推断零费用。
- 使用 attempt 级数据；B 当前 batch 样本的未知耗时曾在上游合计为 0，C 会记录警告并恢复为 `null`。这没有修改 B 的程序。
- 耗时是记录中的请求耗时之和，不等于缓存重放或异步 batch 的端到端耗时。
- `request_costs` 按 `cache_key` 去重，检查重复 key 的响应/成本一致性。其范围是选定 runs 的全部已记录 attempts，可能包含不属于本次评分 split 的已登记 bug。不可把各评分配置的费用相加当作账单。
- 费用来自 B 保存的估算，未核对供应商价目或账单；本次离线评分没有新模型调用。

## 当前可报告的结果

固定 B commit 中有 9 个 run、27 份 bug 输出、119 个 sample/attempt 记录、102 个唯一请求 key。每个 run 生成 single、mean 及各自 5 个融合权重，共 108 个 B 配置；另加 Ochiai、DStar 两种 baseline。

所有配置在 Lang-1/3/4 上 Top-1/3/5 均为 3/3，MRR@20 为 1.0。它们只有 **3 个 dev bug**，不是 108 个独立实验样本，不能声称 LLM 改善了定位效果。两组 `allcand` run 对每例展示 20 个候选；其余 run 分别展示 3/4/2 个。Lang-4 构造函数和 translate 都是参考标签，命中其中一个就得分。

按唯一 key 汇总的记录费用为 $1.450983；它是这些结果对应的记录费用，不是本次评分花费或实际账单。batch run 的延迟保留未知。基于这些数据可在中期报告中展示接口已贯通、指标可复现、费用/异常可追踪；改善效果需要事先冻结的新样本。

## 下一批接入

适配器按每个 run 的 `summary.json.input_dir` 读取同一固定提交里的 A 输入，支持 `data/batches/lang-expansion-20261023/B` 等新批次目录；旧记录未声明时使用 `data/sample/B`。输入身份与哈希仍必须一致。新批次评分请显式使用 `--run` 选择对应的新 run，避免将旧三例的历史 run 混入新十例 manifest。

先冻结 manifest 的 bug 范围与 dev/eval 划分，再由 A/B 产出数据、C 独立准备标签和对应 baseline。使用新的 `--b-ref`、manifest、labels、baseline 和输出目录。缺失 B 结果不删除 bug；整个 run 无结果时停止，因为无法推断其配置。主模型、prompt、样本数、候选展示策略和融合权重只用 dev 确定，eval 用于冻结后的比较。

标签与补丁只交给 C 评分端。B 模型输入仍来自 A 的 `data/sample/B/`。
