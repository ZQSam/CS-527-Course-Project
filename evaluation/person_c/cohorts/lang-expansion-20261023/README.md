# Lang 扩充批次：C 标签核验与 baseline

## 输入与划分

A 的数据来自 `person-a/lang-expansion-20261023`，提交 `fc9946d63bc26716dc621fcb1d4f7456ff98ebcf`。本次检查时该分支没有 PR，也未合入 main。B 原来的 PR #3 已合入 main；C 的 B 输出适配 PR #2 仍独立待合并。

A 在 `e19f54f` 单独预登记 Lang-5 至 Lang-14，采集后的登记文件与该提交字节一致。十例均 ready，没有运行失败或替换样本。C 于 2026-10-25 在查看新标签与命中排名前，把全部十例固定为 eval，并单独提交 [split_decision.json](split_decision.json)；原来 Lang-1/3/4 保留为 dev。冻结的 B 配置来自 `f97c09a`，后续不得根据这十例得分调模型、prompt、K 或融合权重。

这仍是同一项目上的小型评估集，不能称作跨项目泛化验证或已证明没有训练数据污染。

## A 数据核对

- C ZIP SHA-256：`fafe5bd9ee46996152c50bd6ea54043d7d9fee56823e0ec47f8c7ac59b2f23e1`；1920 个 manifest 文件的哈希/大小匹配。
- 992 份含方法的源码文件、23166 条方法记录重新解析匹配。
- 原始压缩覆盖率重新归一化，与发布的测试/statement 数据逐项一致；重算 Ochiai/DStar 全排名完全匹配。
- A 的 B 输入和 C 包中的 model_inputs 逐字节相同，候选均为固定 Ochiai top-20；模型输入验证通过。
- 没有重新运行 Java 测试或采集覆盖率。这里只验证已发布的证据及计算。

具体见 [audit.json](audit.json) 和 [原始覆盖率重放记录](raw_replay_audit.json)。

发现并修复一项可移植性问题：`fl.batch.collect_attempts` 的根路径未统一 resolve，macOS 临时目录 `/var` 与 `/private/var` 的别名导致 `relative_to` 报错。入口统一根路径后，原有失败重试保留测试通过。该问题不改变现有 Linux 采集数据。

## 标签与基线结果

官方补丁固定到 Defects4J v2.0.0 commit；十例均验证 fixed→buggy 两侧 blob、补丁上下文、错误版源码哈希和方法边界。标签定义仍是补丁触及的既有生产方法/显式构造函数，所有十例保留，无方法级排除。

**新增十例的补丁/源码核验已完成，人工确认仍为 pending。** 原来三例的人工确认没有复制到新标签。这里的 `status: reviewed` 表示已完成有证据的补丁映射检查，`human_review_status` 独立记录人工确认状态；不是独立人工二次复核。

| Bug | Ochiai/DStar 首个标签名次 | top-20 包含标签 | 特别说明 |
|---|---:|---|---|
| Lang-5 | 1 | 是 | toLocale |
| Lang-6 | 22 | **否** | 保留在分母；候选重排无法补回未入选方法 |
| Lang-7 | 1 | 是 | createNumber、createBigDecimal 两个标签 |
| Lang-8 | 3 | 是 | 构造函数、appendTo；字段行 1098 单列 |
| Lang-9 | 11 | 是 | init |
| Lang-10 | 19 | 是 | escapeRegex |
| Lang-11 | 1 | 是 | random 重载 |
| Lang-12 | 1 | 是 | random 重载 |
| Lang-13 | 2 | 是 | 构造函数、resolveClass；字段插入位置 238 单列 |
| Lang-14 | 1 | 是 | equals(CharSequence,CharSequence) |

两种 baseline 都是 **Top-1 5/10、Top-3 7/10、Top-5 7/10、MRR@20 0.597687、完整 MRR 0.602233、Recall@20 9/10**。因此固定 K=20 的 B 排名最多命中 9/10，不能通过移除 Lang-6 提高指标。

Lang-13 首个标签处于第 1–2 名并列组。主结果沿用固定顺序；另报乐观并列口径 Top-1 6/10、MRR@20 0.647687。悲观口径与主结果相同。敏感性分析不修改 B 的候选集合，不能选择最有利口径作为主结果。

Lang-8/13 保留方法标签并明确记录字段改动，不宣称所有因果根源均能由方法级标签完整代表。

- [MRR@20 报告](results/mrr20/report.md) / [逐例 JSON](results/mrr20/summary.json)
- [完整 MRR 报告](results/full/report.md)
- [并列敏感性](derived/tie_sensitivity.json)
- [补丁映射证据](mapping.json) / [审核决定](review_decisions.json) / [官方来源](evidence/SOURCES.json)

## 从仓库根目录复现

使用包含 A 扩充数据的分支。先安装固定 parser 依赖（仅首次安装需网络）：

```bash
python3 scripts/setup_python.py
PYTHONPATH="$PWD/.deps" python3 scripts/prepare_sample.py --release data/batches/lang-expansion-20261023/release.json --profile C --check-source
PYTHONPATH="$PWD/.deps" python3 evaluation/person_c/verify_batch.py --profile .work/batches/lang-expansion-20261023/C --output evaluation/person_c/runs/expanded-raw-replay.json
PYTHONPATH="$PWD/.deps" python3 evaluation/person_c/import_person_a.py --archive data/batches/lang-expansion-20261023/person-a-lang-C.zip --cohort evaluation/person_c/cohorts/lang-expansion-20261023/import_contract.json --evidence-dir evaluation/person_c/cohorts/lang-expansion-20261023/evidence --reviews evaluation/person_c/cohorts/lang-expansion-20261023/review_decisions.json --reparse --output-dir evaluation/person_c/runs/expanded
python3 evaluation/person_c/evaluate.py --manifest evaluation/person_c/runs/expanded/manifest.json --labels evaluation/person_c/runs/expanded/labels.json --predictions evaluation/person_c/runs/expanded/ochiai.json evaluation/person_c/runs/expanded/dstar.json --output-dir evaluation/person_c/runs/expanded-mrr20
python3 evaluation/person_c/evaluate.py --manifest evaluation/person_c/runs/expanded/manifest.json --labels evaluation/person_c/runs/expanded/labels.json --predictions evaluation/person_c/runs/expanded/ochiai.json evaluation/person_c/runs/expanded/dstar.json --rank-cutoff 0 --output-dir evaluation/person_c/runs/expanded-full
python3 evaluation/person_c/summarize_cohort.py --data-dir evaluation/person_c/runs/expanded --output-dir evaluation/person_c/runs/expanded-derived
```

输出路径须不存在。完整排名和重复源码留在可再生的 `runs/`，不再提交另一套大型文件。这里保存标签、映射、审查记录、汇总和输入哈希；重跑时不同的相对输出路径会改变报告中的路径文字，但指标及输入内容哈希应一致。

## 给 B 的下一步

继续使用 A 的 `data/batches/lang-expansion-20261023/B/`，不要把本目录的标签、补丁、排名命中分析给模型。按已冻结配置运行十例，使用独立 run ID，例如：

```bash
python3 scripts/run_rerank.py --config configs/batches/lang-expansion-20261023/rerank.json --model opus --samples 5 --run-id opus-v2-k20-s5-lang-expansion-20261023
```

该命令会调用模型并产生费用，本次 C 工作没有执行。先跑主配置即可；任何失败保留，不替换 bug。交回 `summary.json`、逐 bug JSON、`calls.jsonl`，保留 input_dir 和输入哈希。

`derived/predictions_template.json` 是十例 `not_run` 模板，只含公共数据集身份、候选与空预测，不含标签。它不能作为真实 LLM 成绩。目前仓库尚无这一新批次的 B 输出，因此这里只报告 baseline，不制造 LLM 对比结果。
