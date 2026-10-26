# Person C 中期评估材料：数据核验、评分与结果分析

更新日期：2026-10-26。负责人：Alina Wu（Person C）。

本文汇总 C 已完成的工作，供团队撰写 midterm report、制作展示和复现实验使用。核心结果是：在预先固定的十个 Lang bug 上，Opus 重排的 Top-1 从 SBFL 的 5/10 提高到 9/10；固定融合为 7/10，低于纯 Opus 重排。本文是 C 的技术材料，不代表课程要求的整份报告已经提交。

## 1. 工作范围和固定版本

| 内容 | 范围或版本 |
|---|---|
| 数据集 | Defects4J v2.0.0，Apache Commons Lang |
| 开发集 | Lang-1、Lang-3、Lang-4；仅用于接口联调和配置开发 |
| 本次评估集 | Lang-5 至 Lang-14，共十例，全部保留 |
| A 的扩充数据 | `fc9946d63bc26716dc621fcb1d4f7456ff98ebcf` |
| C 的划分冻结 | `29ff672`，2026-10-25，在查看新标签与命中排名前记录 |
| B 的配置冻结依据 | `f97c09af89a14c32e9bbd93d573606ab80cc38f1` |
| B 的本次输出 | `f645e781833eb2c417b2c44e2597079dfd2e9ae2`，`person-b/lang-expansion` |
| 标签来源版本 | Defects4J `01f13c69425fb8a0db290d12b1d48da1641bf6a9` |
| 主配置 | Opus、prompt v2、Ochiai top-20、五次采样、固定 0.50 融合 |

C 负责标签、核验、适配、评分及分析。A 负责数据采集与 SBFL；B 负责模型运行及原始输出。本次 A/C 集成包括 C 对 B 固定输出的评分文件；B 的新原始响应分支由 B 自行合并。即使 B 尚未合入 main，也可通过固定 Git 提交复现评分。

原来三例 dev 的 baseline 已是 Top-1 3/3，其持平结果不证明 LLM 提升。本文的主表只使用新增十例 eval，不把两组混成 13 例主实验，也不根据新成绩重新调参。

## 2. 数据核验与标签复核

### 2.1 A 数据核验

- C ZIP 的 SHA-256 为 `fafe5bd9ee46996152c50bd6ea54043d7d9fee56823e0ec47f8c7ac59b2f23e1`；清单内 1920 个文件的大小与哈希匹配。
- 使用固定共享 parser 重新解析 992 份含方法源码文件、23166 条方法记录，结果匹配。这里是归档中的文件副本与记录数量，不是独立项目数。
- 对全部十例重新归一化原始覆盖率，重算 Ochiai、DStar 全量排名，与 A 发布结果匹配。
- B 输入与 C 包中的 model_inputs 逐字节相同，每例固定 20 个候选，方法 ID 与发布源码一致。
- A 的十例都采集成功；C 没有按命中情况剔除或替换任何一例。

这一步重放了发布数据的计算，没有重新运行 Java 测试或重新采集覆盖率。

### 2.2 标签与人工确认

标签定义为官方补丁触及的既有生产方法或显式构造函数。每例检查官方 fixed→buggy 补丁两侧 blob、补丁上下文、buggy 源码哈希及方法边界，共保留 13 个方法标签。

Lang-7、Lang-8、Lang-13 各有两个方法标签，评分取其中最先命中的位置。Lang-8 的字段行 1098 和 Lang-13 的字段插入位置 238 单独披露，不能把方法标签解释为覆盖所有因果根源。

Alina Wu（Person C）已于 **2026-10-26 明确确认新增十例的人工复核完成**。记录使用 `human_review_status: completed`、具名 reviewer、日期及 `human_review_basis: reviewer_confirmation`。这是本批单独确认，不是复制旧三例的确认，也不宣称有另一位独立复核人。

### 2.3 B 输出核验

三组实验分别是 Opus all-20、Haiku all-20、Opus nonzero，每组十例、每例五次采样。

- 150 个最终样本均为 `ok`，共有 151 次尝试记录。
- Haiku 的 Lang-5、sample index 3 首次重复候选标签 C18，按原定最多两次规则重试后有效；原始错误和重试都保留。
- 对全部结果离线重放，匹配输入哈希、prompt/request hashes、响应解析、候选排列、重试选择、均值排序、融合、理由引用检查、降级记录、日志及费用汇总。
- B 代码哈希为 `8aca713913e872a45cac8c1755f4e215b6e5297e4a4ef1d5109183738da7da54`，与冻结实现一致。
- 所有排名都覆盖原始候选 ID。nonzero 配置省略的零分候选按原定规则追加到尾部，不把候选集合缺失伪装成完整模型判断。

离线重放使用冻结的 B 实现，核对的是输出记录与实现的一致性。它不等于供应商独立认证，也不等于模型理由的语义正确性已被证明。

## 3. 评分口径

- **单位和分母**：bug；N=10。多次采样、多个权重或不同模型不增加独立 bug 数。
- **Top-k**：前 k 个方法中包含任一标签，则该 bug 命中。主表同时报告 Top-1、Top-3、Top-5。
- **MRR@20**：首个正确方法位置为 r 且 r≤20 时记 1/r，否则记 0，再对全部十例平均。
- **候选召回率**：九例的标签进入固定 top-20，即 Recall@20=9/10。Lang-6 标签在全排名第 22，仍留在分母，因此这套候选下重排最多命中九例。
- **失败口径**：single 要求 sample 0 最终为 `ok`；mean 要求全部计划样本最终为 `ok`，不把修补填充或失败兜底作为有效 LLM 成绩。允许预先固定规则内的纠正重试，并计入其费用。
- **并列口径**：主结果沿用固定确定顺序，另报乐观/悲观敏感性；不看标签后调整 tie 顺序。
- **主次比较**：冻结的 Opus all-20 及 0.50 融合为主比较；Haiku、nonzero、其他权重为补充，不据此在 eval 上挑选“最优”主配置。

## 4. 结果对比

| 方法 | Top-1 | Top-3 | Top-5 | MRR@20 |
|---|---:|---:|---:|---:|
| Ochiai | 5/10 | 7/10 | 7/10 | 0.597687 |
| DStar | 5/10 | 7/10 | 7/10 | 0.597687 |
| Opus 单次，all-20 | 9/10 | 9/10 | 9/10 | 0.900000 |
| Opus 五次平均，all-20 | 9/10 | 9/10 | 9/10 | 0.900000 |
| Opus 五次平均 + 0.50 融合 | 7/10 | 7/10 | 8/10 | 0.730000 |
| Haiku 单次，all-20 | 7/10 | 8/10 | 8/10 | 0.764286 |
| Haiku 五次平均，all-20 | 8/10 | 8/10 | 9/10 | 0.825000 |
| Haiku 五次平均 + 0.50 融合 | 7/10 | 7/10 | 7/10 | 0.726667 |
| Opus 五次平均，nonzero | 9/10 | 9/10 | 9/10 | 0.900000 |

两种 baseline 的完整 MRR 均为 0.602233，与 MRR@20 的差别来自 Lang-6 在第 22 位的贡献。主表统一使用 MRR@20，不混用不同截断口径。

结果支持以下观察：

1. Opus 重排比固定顺序 SBFL 多命中四例，Top-1 从 50% 到 90%，增加 **40 个百分点**。
2. 固定融合从纯 Opus 的 9/10 降到 7/10；虽然仍高于 baseline，但不能宣称融合优于纯 LLM。
3. Opus 单次与五次平均的主表指标相同。本批数据没有显示其多次采样准确率收益。
4. Haiku 的五次平均 Top-1 从单次的 7/10 到 8/10；这是本批观察，不代表所有模型或数据集都受益。
5. nonzero 与 all-20 的 Opus 平均主指标相同，但其中 25 条响应复用，不能当作独立重复验证。

## 5. 逐例结果与案例分析

表中是首个标签的方法名次；“未命中”表示前 20 内没有标签。

| Bug | SBFL 完整排名 | Opus 五次平均 | Opus 平均 + 0.50 融合 | Haiku 五次平均 |
|---|---:|---:|---:|---:|
| Lang-5 | 1 | 1 | 1 | 1 |
| Lang-6 | 22（候选外） | 未命中 | 未命中 | 未命中 |
| Lang-7 | 1 | 1 | 1 | 1 |
| Lang-8 | 3 | 1 | 1 | 1 |
| Lang-9 | 11 | 1 | 5 | 4 |
| Lang-10 | 19 | 1 | 10 | 1 |
| Lang-11 | 1 | 1 | 1 | 1 |
| Lang-12 | 1 | 1 | 1 | 1 |
| Lang-13 | 2 | 1 | 1 | 1 |
| Lang-14 | 1 | 1 | 1 | 1 |

### Lang-9 / Lang-10：重排改善，融合抵消部分改善

两个标签在 baseline 分别排第 11、19，Opus 单次及五次平均均排第 1。固定 0.50 平均融合后分别回退到第 5、10。这说明在这两个案例中，将较差的 SBFL 次序混入后会降低已取得的排名表现。该解释基于可观察排名，未把模型生成的理由当作已验证的因果解释。

### Lang-6：候选召回限制

标签在完整 baseline 的第 22 位，未进入 B 的 top-20 输入。无论重排质量如何，都无法选出未提供的方法。它应计为失败并留在 N=10 中。后续可在另一个预登记实验中研究候选召回，但不能为当前结果临时扩大 K 或删除该例。

### Lang-13：并列和标签粒度限制

首个标签在 baseline 第 1–2 名并列组中，固定顺序记第 2，Opus 排第 1。采用乐观 tie 口径时，baseline Top-1 已是 6/10、MRR@20 为 0.647687，因此四个新增 Top-1 中有一个依赖既定 tie 口径。主表保留事前固定次序，同时公开敏感性结果。该例另有方法外字段改动，两个方法标签不能完整描述所有补丁变化。

## 6. 费用、重试与运行限制

| 实验 | 最终样本 | 尝试记录 | 缓存命中 | 记录逻辑费用 | 本次新增记录费用 |
|---|---:|---:|---:|---:|---:|
| Opus all-20 | 50 | 50 | 0 | $2.125720 | $2.125720 |
| Haiku all-20 | 50 | 51 | 0 | $0.061462 | $0.061462 |
| Opus nonzero | 50 | 50 | 25 | $1.490040 | $0.393140 |

按 126 个唯一请求去重后，记录费用约 **$2.580324**；各 run 的六位小数已四舍五入，相加可能存在末位差异。nonzero 的逻辑费用含已发生的缓存响应费用，不能把三行逻辑费用直接相加当账单。单次、均值及多个融合权重也共用底层响应，不能累计为多份实际支出。

Lang-6 至 Lang-10 的候选本来均为非零分，对应 nonzero 与 all-20 复用 25 条响应。费用仅按 B 保存的 usage 和配置单价核算，未独立核验供应商账单。C 的评估没有新增模型调用。

## 7. 局限与后续工作

- **样本和项目范围小**：只有同一项目的十个历史 bug，未建立跨项目泛化或统计显著性结论。
- **训练数据污染未知**：公开历史数据可能出现在模型训练材料中，本实验没有证明不存在污染。
- **标签是补丁代理**：补丁触及的方法适合可复现评分，但不保证每个方法都独立构成根因；混合字段修改已披露。
- **上下文不完整**：Lang-8/9/10 有重复测试或 stack 内容；Lang-10 的 helper 因预算省略。保留降级记录，没有根据本轮得分回头优化 prompt。
- **采样不独立**：同一 bug 的多次请求、离线权重变体及缓存复用不是新增独立样本。
- **语义解释未评估**：引用行存在、响应格式正确、排名命中，均不等于解释语义正确或修复已验证。
- **复现范围有限**：C 重放固定数据和响应，没有重新采集覆盖率、验证新模型版本或调用 API。

中期核心实验与 C 的评估材料已完成。未来若继续研究，应先登记新数据及配置，再做更广泛评估、候选召回实验或解释正确性评估，不在当前十例上反复选参数。团队仍需将各部分整合成课程要求的最终提交材料。

## 8. 附件与复现入口

所有附件都是仓库内相对链接，可随本文一起在 main 中阅读。B 的原始模型输出固定在其提交，尚未合并时通过下表链接查看。

| 附件 | 用途 |
|---|---|
| [A 扩充交接](person_a_lang_expansion.md) | 数据来源、采集与交接范围 |
| [划分冻结记录](../evaluation/person_c/cohorts/lang-expansion-20261023/split_decision.json) | 十例 eval 的预先决定 |
| [导入约定](../evaluation/person_c/cohorts/lang-expansion-20261023/import_contract.json) | 固定 A 版本、归档和划分哈希 |
| [A 数据核验](../evaluation/person_c/cohorts/lang-expansion-20261023/audit.json) | 归档、源码和方法记录核验 |
| [原始覆盖率重放](../evaluation/person_c/cohorts/lang-expansion-20261023/raw_replay_audit.json) | 两种全量 baseline 重算证据 |
| [标签](../evaluation/person_c/cohorts/lang-expansion-20261023/labels.json) / [映射](../evaluation/person_c/cohorts/lang-expansion-20261023/mapping.json) | 十例标签及补丁映射 |
| [人工确认](../evaluation/person_c/cohorts/lang-expansion-20261023/review_decisions.json) / [官方证据来源](../evaluation/person_c/cohorts/lang-expansion-20261023/evidence/SOURCES.json) | 具名复核记录及官方补丁版本 |
| [baseline 报告](../evaluation/person_c/cohorts/lang-expansion-20261023/results/mrr20/report.md) / [完整 MRR](../evaluation/person_c/cohorts/lang-expansion-20261023/results/full/report.md) | baseline 指标及截断区别 |
| [并列敏感性](../evaluation/person_c/cohorts/lang-expansion-20261023/derived/tie_sensitivity.json) | 乐观、悲观与固定顺序对照 |
| [完整 B 评分表](../evaluation/person_c/cohorts/lang-expansion-20261023/results/person_b/report.md) | 36 个 B 排名变体及两种 baseline |
| [逐例分数与溯源](../evaluation/person_c/cohorts/lang-expansion-20261023/results/person_b/summary.json) | 名次、状态、费用、输入及实现哈希 |
| [B 离线审计](../evaluation/person_c/cohorts/lang-expansion-20261023/results/person_b/audit.json) | 150 个样本、重试、请求去重核验 |
| [B 固定原始输出](https://github.com/ZQSam/CS-527-Course-Project/tree/f645e781833eb2c417b2c44e2597079dfd2e9ae2/results/rerank) | 模型原始响应与调用日志；由 B 维护 |
| [完整复现命令](../evaluation/person_c/cohorts/lang-expansion-20261023/README.md) | A 导入、baseline、B 审计及评分步骤 |
| [B 格式适配说明](../evaluation/person_c/PERSON_B.md) | 接口、失败处理和用量口径 |
| [初始 dev 结果](../evaluation/person_c/real/README.md) | 三例联调历史，勿与本次 eval 混用 |

主要程序是 `evaluation/person_c/import_person_a.py`、`verify_batch.py`、`import_person_b.py`、`evaluate.py` 和 `audit_expanded_b.py`。大型重复源码及生成预测保留在可再生的忽略目录 `runs/`；本文链接的标签、证据和汇总已纳入版本管理。

集成验证：根测试套件 80 项通过、7 项因 WSL/Linux 环境要求跳过；C 测试套件 54 项通过。合计 134 项通过、7 项跳过。模型输出审计属于离线记录重放，不包含新增付费调用。
