# Person C：真实 Lang 小样本 baseline（2026-10-21）

已经完成 A → C 的真实数据对接、补丁标签核对和 baseline 评分。**三个案例的 Ochiai/DStar 都在第 1 名命中，Top-1=3/3，MRR=1.0；这批样本没有展示重排提升的空间。**

这是 `dev` 联调批次，不是正式 held-out 评估。三个 bug 全部保留；没有按定位效果挑选或排除。B 的模型结果尚未接入。

## 结果

| 配置 | N | Top-1 | Top-3 | Top-5 | MRR@20 | 完整 MRR | Ochiai 候选命中 |
|---|---:|---:|---:|---:|---:|---:|---:|
| Ochiai | 3 | 3/3 | 3/3 | 3/3 | 1.0000 | 1.0000 | 3/3 |
| DStar（指数 2） | 3 | 3/3 | 3/3 | 3/3 | 1.0000 | 1.0000 | 3/3 |
| LLM 重排 / 融合 | 未运行 | — | — | — | — | — | — |

这里的候选集统一指 B 收到的 Ochiai 前 20 方法。每个 bug 任意一个标签被命中即可计分，不表示所有被修改的方法都已找到。纯 SBFL 的模型 API 花费为 0；未知计算耗时保留 null。

| Bug | 补丁涉及的已有方法 | 第一个命中排名 | 其他修改 |
|---|---|---:|---|
| Lang-1 | `NumberUtils#createNumber(String)`，错误版 450–614 行 | 1 | 无方法外修改 |
| Lang-3 | `NumberUtils#createNumber(String)`，错误版 450–610 行 | 1 | 修复纯增加方法内语句，按插入点映射 |
| Lang-4 | `LookupTranslator#<init>(CharSequence[][])`，45–63 行；`translate(CharSequence,int,Writer)`，68–84 行 | 1（构造方法为 2） | 第 31 行字段类型修改单独记录 |

完整 ID（包含源文件路径、全限定类名、参数类型）在 [labels.json](data/labels.json)，逐块证据在 [mapping.json](data/mapping.json)，审阅理由在 [review_decisions.json](review_decisions.json)。标签已逐块核对补丁与源码，并通过自动校验；**Person C（Alina Wu）已于 2026-10-22 确认复核完成**。`status: reviewed` 表示补丁映射核查完成，`human_review_status: completed` 及 reviewer/date/basis 字段记录本次复核确认。

## 核查依据

- A 仓库固定为 `99e7b385023f5d601f8cca01125c52ca02cba674`。
- Defects4J 为 `v2.0.0`，commit `01f13c69425fb8a0db290d12b1d48da1641bf6a9`。
- 原始 C ZIP 的 SHA-256 和清单内 764 个文件的哈希、大小一致。
- 使用 A 原版 `fl/java.py`，依赖版本 `tree-sitter==0.25.2`、`tree-sitter-java==0.23.5`。重解析 303 份已索引生产源码，7,192 个方法/构造方法记录与 A 完全一致。
- 对每份补丁验证方向为 fixed → buggy：buggy 文件的 Git blob 对上补丁右侧，按精确上下文重建 fixed 文件后，Git blob 对上左侧。原始 buggy revision 与固定版本的 `active-bugs.csv` 一致。
- Lang-4 属于混合字段/方法修改：保留两个已有方法标签，明确字段不属于方法级标签范围。没有把它标记为“仅新增方法”或静默排除。
- 排名按分数降序、完整 `method_id` 升序打破并列；保留全部 `rank_min/rank_max/tie_size`。三个最早命中均是独立第 1 名，乐观/悲观并列规则在这批数据上不改变结果，见 [tie_sensitivity.json](results/tie_sensitivity.json)。
- 七条历史环境/采集失败均在 A 的记录中标记为已解决；不是七个被排除的 bug。

以上验证复用 A 的数据，没有重新运行 Java 测试或采集覆盖率。补丁标签代表被修复修改的方法，不等于已证明每个方法都是独立根因。

来源 URL、固定 revision 与本地 SHA-256 见 [SOURCES.json](evidence/SOURCES.json)。验证详情见 [audit.json](data/audit.json)。

## 重跑评分

在评估工具包根目录运行；Python 3.10+ 标准库即可。输出目录必须不存在。

```bash
python3 -m unittest discover -s tests -v
python3 evaluate.py --manifest real/data/manifest.json --labels real/data/labels.json --predictions real/data/ochiai.json real/data/dstar.json --split dev --output-dir runs/lang-pilot-mrr20
python3 evaluate.py --manifest real/data/manifest.json --labels real/data/labels.json --predictions real/data/ochiai.json real/data/dstar.json --split dev --rank-cutoff 0 --output-dir runs/lang-pilot-full
```

已生成的报告在 [MRR@20 报告](results/mrr20/report.md) 和 [完整 MRR 报告](results/full/report.md)。默认 `eval` 会拒绝这份全部为 dev 的清单，防止误称正式评估。

## 从原始 A ZIP 重新导入

先按 `evidence/SOURCES.json` 下载固定版本 ZIP，保留其原始字节。`import_person_a.py` 会拒绝哈希不符的包。无需解压或重建 A 的 Java 环境。

```bash
python3 import_person_a.py --archive /absolute/path/person-a-lang-C.zip --reviews real/review_decisions.json --output-dir runs/reimport
```

在仓库中，原始 ZIP 位于 `../../data/sample/person-a-lang-C.zip`（相对于评估目录）。

省略 `--reviews` 时输出 pending 标签，评分器拒绝评分。审阅文件绑定补丁和源码哈希，不能直接沿用到新版本。此适配器仅支持本次固定三例及单文件补丁；扩批时需审阅新格式和标签，不能直接放宽检查。

若要重做独立源码解析，在项目内安装依赖后加 `--reparse`：

```bash
python3 -m pip install --target .deps tree-sitter==0.25.2 tree-sitter-java==0.23.5
PYTHONPATH=.deps python3 import_person_a.py --archive /absolute/path/person-a-lang-C.zip --reviews real/review_decisions.json --output-dir runs/reimport-with-parser --reparse
```

共享 parser 原版副本与来源在 `vendor/`。当前环境为 macOS，解析记录与 A 的结果一致；不是对 A 的 WSL/Java 执行环境做了重跑。

## 下一步

1. B 先用当前三例完成一次重排输出，检查 method ID、候选集合、状态与用量；C 的 [B 输出模板](../handoff_B/README.md) 已准备。
2. C 接到真实 B 输出后直接跑同一套标签和清单，报告持平/退步及成本，不预设会提升。
3. A 扩充样本时，先固定 bug 范围和技术筛选规则，保留采集失败记录；不能只挑 Ochiai 排名较差的案例作为主评估集。
4. 后续正式 eval 单独冻结；当前三例保留为 dev。Lang-4 的混合修改标签规则已随本次 Person C 复核确认。

可用于中期汇报：我们完成了三例真实 Defects4J 数据的 baseline 与标签评估对接，发现小样本 baseline 已饱和，因此下一阶段扩大预先确定的样本范围并接入 LLM 对照。当前不能宣称 LLM 有效或完整端到端模型实验已完成。
