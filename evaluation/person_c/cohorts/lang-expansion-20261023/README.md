# Lang 扩充批次：C 标签核验与 B 实验评估

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

**新增十例的补丁/源码核验已完成，Alina Wu（Person C）于 2026-10-26 明确确认人工复核完成。** `human_review_status: completed`、日期和 `reviewer_confirmation` 依据已独立记录；不是沿用原来三例的确认，也不宣称存在另一位独立复核人。

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

## B 新结果与中期可用结论

已核验 B 分支 `person-b/lang-expansion` 的固定提交 `f645e781833eb2c417b2c44e2597079dfd2e9ae2`。相对 A 扩充提交只增加实验记录与交接文档，B 代码内容哈希保持冻结版本。原始 B 输出保留在其分支；本 PR 保存 C 的评估，不重复提交模型响应。

三组均为十例、每例五次采样，共 150 个最终有效样本、151 次尝试记录；Haiku 的 Lang-5 sample 3 首次重复 C18，按已冻结的最多两次规则重试后成功。最终输出无修补填充或失败兜底。离线重放逐项匹配完整结果（prompt/request hashes、原始响应解析、重试选择、理由检查、降级记录、均值排序、融合、日志和费用）。这不等于模型解释已通过语义正确性人工评估。

| 配置 | Top-1 | Top-3 | Top-5 | MRR@20 |
|---|---:|---:|---:|---:|
| Ochiai / DStar | 5/10 | 7/10 | 7/10 | 0.597687 |
| Opus 单次，全部 20 候选 | 9/10 | 9/10 | 9/10 | 0.900000 |
| Opus 五次平均排序，全部 20 候选 | 9/10 | 9/10 | 9/10 | 0.900000 |
| Opus 五次平均 + 固定 0.50 融合 | 7/10 | 7/10 | 8/10 | 0.730000 |
| Haiku 单次，全部 20 候选 | 7/10 | 8/10 | 8/10 | 0.764286 |
| Haiku 五次平均排序，全部 20 候选 | 8/10 | 8/10 | 9/10 | 0.825000 |
| Haiku 五次平均 + 固定 0.50 融合 | 7/10 | 7/10 | 7/10 | 0.726667 |
| Opus 五次平均，仅非零候选 | 9/10 | 9/10 | 9/10 | 0.900000 |

主对照是冻结的 Opus / v2 / all-20 / 五次采样及固定 0.50 融合。Haiku、nonzero 和其他权重仅作为补充比较/敏感性分析，不能根据这些 eval 得分重新选最优配置再当作主实验。

- **重排提高命中，但融合不一定提高。** Opus 的 Top-1 从 5/10 到 9/10，增加 4 个命中、40 个百分点。固定融合退到 7/10，不能写成所有组件都有收益。
- **多次采样收益依模型而异。** Opus 单次与五次平均的这些指标相同；Haiku Top-1 从 7/10 到 8/10。不能声称 Opus 多次采样提高了本批准确率。
- **Lang-9/10 展示融合退步。** 基线首个标签分别在第 11/19 位，Opus 单次和平均都将其排第 1；0.50 平均融合后退到第 5/10。混入较差的 SBFL 次序会抵消 LLM 的提升，这是排名结果观察，未证明模型的解释或因果推理正确。
- **Lang-6 展示候选召回上限。** 标签在全排名第 22，固定 top-20 未包含，所有重排仍 miss。继续保留在分母 N=10，不能为提高分数删除。
- **Lang-13 有并列口径影响。** 基线固定次序第 2，Opus 第 1；按基线乐观 tie 口径原本已算 Top-1，因此这一个增益依赖既定 tie 口径。主表仍采用事前固定次序。
- **nonzero 不是独立重复。** Lang-6 至 Lang-10 的候选本来全部正分，与 all-20 共享 25 个请求/响应；不得把 150 个样本当作 150 个独立 bug。

主 Opus 记录费用 $2.125720，Haiku $0.061462，nonzero 本次新增约 $0.393140（含缓存的逻辑费用 $1.490040 不应再次相加）。按 126 个唯一请求去重后约 **$2.580324**。这些是按 B 配置单价核算的记录费用，不是供应商账单；C 的核验没有新增模型调用。

Lang-8/9/10 的上下文有重复测试/stack 内容，Lang-10 的 helper 因预算省略，原始降级记录保留。为保持预登记配置，此轮不回头调整 prompt。样本仅同一 Lang 项目的十个历史 bug，不支持跨项目或无训练污染的结论。

- [完整 36 种 B 排名与两种基线](results/person_b/report.md)
- [逐例得分、输入哈希、费用及人工确认](results/person_b/summary.json)
- [150 个样本的离线重放审计](results/person_b/audit.json)

### 复现 B 审计与 C 评分

先执行前面的 A 导入命令生成 `runs/expanded`。评分依赖 PR #2 中的 `import_person_b.py`（固定版本来自 `da1a1b9c16bc5547ae87228d3a231d8fc4a38aec`），与本 PR 可以无冲突合并。若 PR #2 尚未合入，可以把适配器及本分支的 `evaluate.py` 导出到忽略目录后直接运行：

```bash
git fetch origin person-b/lang-expansion person-c-b-output-evaluation
mkdir -p evaluation/person_c/runs/b-snapshot evaluation/person_c/runs/adapter
git archive f645e781833eb2c417b2c44e2597079dfd2e9ae2 | tar -x -C evaluation/person_c/runs/b-snapshot
python3 evaluation/person_c/audit_expanded_b.py --b-root evaluation/person_c/runs/b-snapshot --output evaluation/person_c/runs/b-replay-audit.json
git show da1a1b9c16bc5547ae87228d3a231d8fc4a38aec:evaluation/person_c/import_person_b.py > evaluation/person_c/runs/adapter/import_person_b.py
cp evaluation/person_c/evaluate.py evaluation/person_c/runs/adapter/evaluate.py
python3 evaluation/person_c/runs/adapter/import_person_b.py --b-ref f645e781833eb2c417b2c44e2597079dfd2e9ae2 --run langexp1023-opus-v2-k20-s5 --run langexp1023-haiku-v2-k20-s5 --run langexp1023-opus-v2-nz-s5 --manifest evaluation/person_c/runs/expanded/manifest.json --labels evaluation/person_c/runs/expanded/labels.json --baseline evaluation/person_c/runs/expanded/ochiai.json --baseline evaluation/person_c/runs/expanded/dstar.json --output-dir evaluation/person_c/runs/expanded-b
```

适配器生成的通用报告含一条只适用于 dev 的旧模板说明，本目录的归档报告已把它改为本批 eval 的冻结口径；不影响 JSON 或评分计算。`derived/predictions_template.json` 仍仅是 `not_run` 接口模板，真实成绩请使用上面的 `results/person_b/`。
