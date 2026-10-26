# Person A：预登记的 Lang 扩充批次

分支：`person-a/lang-expansion-20261023`。起点为最新 main `f17acd1`。

## 先定清单，再采集

本批次为 **Lang-5 至 Lang-14**。从固定 Defects4J 2.0.0 的 active 清单中，
排除原先已交付的 Lang-1/3/4，按数字编号选择接下来的十例。
运行前已将[清单](../configs/cohorts/lang-expansion-20261023.json)和
[预登记记录](../results/lang_expansion_20261023/preregistration.json)单独提交。

- 不按 Ochiai 排名、候选召回或 LLM 表现筛选。
- 保留 baseline 已排第一的案例，也保留非第一、失败和需要重试的案例。
- 运行失败不自动等于方法级 benchmark 排除；不以其他 bug 替换失败案例。
- C 后续决定标签、split、方法级排除及统一评估分母。A 不读取新案例标签，也不运行新 LLM 调用。

实际状态、成功与失败清单、版本及证据见
[批次报告](../results/lang_expansion_20261023/report.md)。原始三例 dev 数据保持原样。

## B 怎么接

```bash
python3 scripts/prepare_sample.py --release data/batches/lang-expansion-20261023/release.json --profile B
```

从 `data/batches/lang-expansion-20261023/B/index.json` 读取 ready 数据。
`requested_bugs` 是完整预登记清单；`failed_bugs` 和 `status.json` 说明未 ready 的案例。
所有 ready 文件保持原模型输入 schema 和 method ID 规则，保留全部 top-20 候选。

`configs/batches/lang-expansion-20261023/rerank.json` 只将队友冻结配置的 `input_dir`
改为新批次，其他参数保持一致。B 可以先估算，再按自己的预算运行：

```bash
python3 scripts/run_rerank.py --config configs/batches/lang-expansion-20261023/rerank.json --model opus --dry-run
```

## C 怎么接

```bash
python3 scripts/prepare_sample.py --release data/batches/lang-expansion-20261023/release.json --profile C
python3 scripts/setup_python.py
PYTHONPATH="$PWD/.deps" python3 scripts/prepare_sample.py --release data/batches/lang-expansion-20261023/release.json --profile C --check-source
```

从 `.work/batches/lang-expansion-20261023/C/index.json` 读取相对路径。
数据包包含完整 Ochiai/DStar 排名、逐测试覆盖率和原始文件、buggy 源码快照、
完整预登记状态、全部失败尝试及版本信息。`data/excluded.csv` 仅有待 C 审核的表头。

当前 `evaluation/person_c/import_person_a.py` 固定了旧三例和旧 ZIP 哈希，
不能直接用来导入新 cohort；请由 C 扩展适配器，复用 `fl/java.py` 和新的 index。
请保留原始完整 cohort，不因 B 缺少输出或 baseline 饱和而事后改变清单。

## 重新运行采集

先按[环境文档](reproducing_person_a.md)启动原固定镜像，然后在 WSL 的仓库根目录运行：

```bash
python3 scripts/check_batch_environment.py --cohort configs/cohorts/lang-expansion-20261023.json --results-root results/lang_expansion_20261023
bash scripts/run.sh python3 scripts/smoke_defects4j.py --config configs/batches/lang-expansion-20261023/reproduction.json
bash scripts/run.sh python3 scripts/run_milestone2.py --config configs/batches/lang-expansion-20261023/coverage.json
bash scripts/run.sh python3 scripts/build_batch_handoff.py --cohort configs/cohorts/lang-expansion-20261023.json --results-root results/lang_expansion_20261023 --destination data/batches/lang-expansion-20261023
```

交付目标已经存在时，打包程序会拒绝覆盖；保留已发布版本并另选目标目录。
重复采集产生新 run ID，历史失败尝试会一直保留。预登记文件和原始采集配置不应修改。
