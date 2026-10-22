# CS527：LLM-enhanced Fault Localization

本项目研究：在 Defects4J 的真实 Java bug 上，LLM 能否改善传统 Ochiai 的**方法级故障定位排名**。
设计以 [proposal](docs/CS527_Proposal_LLM_Fault_Localization.pdf) 为准。

**B、C 现在可以直接使用已采集的数据，无需先安装 Java、Docker 或重新运行覆盖率。**
首次使用需要 Git 和 Python 3.10+。Windows 上的实验与源码解析请在 WSL2 Ubuntu 中运行；B 读取 JSON 可以使用任意系统。

```bash
git clone https://github.com/ZQSam/CS-527-Course-Project.git cs527-llm-fl
cd cs527-llm-fl
```

已有仓库的队友请先保存自己的改动，再正常 `git pull`。

## 我应该从哪里开始？

| 角色 | 立即使用的材料 | 开始阅读 |
| --- | --- | --- |
| **B：上下文 / LLM 重排 / 缓存 / 采样 / 融合** | [`data/sample/B/index.json`](data/sample/B/index.json)，每个 bug 一份完整模型输入 | [B 快速开始](docs/person_a_handoff_b.md) |
| **C：补丁标签 / 评估 / 批量实验 / 报告** | [`data/sample/person-a-lang-C.zip`](data/sample/person-a-lang-C.zip)，含完整排名、覆盖率、源码快照与失败记录 | [C 快速开始](docs/person_a_handoff_c.md) |
| **C：使用 B 的 LLM 重排结果** | [`results/rerank/index.json`](results/rerank/index.json)，每个 run 每个 bug 一份排名与成本 | [B → C 接口](docs/person_b_output_contract.md) |
| **需要重新采集数据** | `docker/`、`fl/`、`scripts/`、`configs/` | [环境和复现实验](docs/reproducing_person_a.md) |

## B：直接读取模型输入

从仓库根目录执行；只使用 Python 标准库：

```bash
python3 scripts/prepare_sample.py --profile B
python3 - <<'PY'
import json
from pathlib import Path

root = Path("data/sample/B")
index = json.loads((root / "index.json").read_text(encoding="utf-8"))
for entry in index["bugs"]:
    bug = json.loads((root / entry["path"]).read_text(encoding="utf-8"))
    print(bug["bug_id"], len(bug["candidates"]), len(bug["failing_tests"]))
PY
```

每个 JSON 包含：候选方法的原样 `method_id`、完整方法源码、Ochiai 分数及排名，
失败测试方法及所在完整文件、原始错误、调用栈，以及 buggy 版本和工具版本。
B 输出排序时请**原样返回这些 method ID**。A 保留完整源码，由 B 决定提示词的 token 预算。

## C：解压并验证完整基线

```bash
python3 scripts/prepare_sample.py --profile C
```

它会检查 ZIP 哈希、文件清单、完整排名和测试结果，再解压到 **`.work/sample/C/`**。
重复执行会校验已有数据；不会覆盖修改过的目录。

从 `.work/sample/C/index.json` 读取每个 bug 的路径：

| 字段 / 文件 | 用途 |
| --- | --- |
| `rankings.ochiai` / `rankings.dstar` | 全部方法的 JSON 排名；同目录也有 CSV |
| `coverage` | 逐测试覆盖率与 PASS / FAIL 结果；同目录保存原始采集文件 |
| `methods` | 解析后的方法 ID、位置、源码和内容哈希 |
| `source_checkout` | 对应 buggy 版本的生产源码和失败测试文件快照 |
| `validation` | 覆盖率、映射和 GZoltar 参考值核对记录 |
| `successful_bugs.txt` / `failures.jsonl` | 成功清单 / 历史运行或采集失败记录 |

如需验证源码能重新解析出相同的方法 ID，在 WSL/Linux 中执行：

```bash
python3 scripts/setup_python.py
PYTHONPATH="$PWD/.deps" python3 scripts/prepare_sample.py --profile C --check-source
```

只在首次安装解析依赖时需要网络。验证样本不需要 Docker、模型 API 或原机器的 checkout。
快照用于检查与补丁映射；创建可编译的完整 checkout 请使用[复现步骤](docs/reproducing_person_a.md)。

## 本次已验证的样本

以下数字来自 [`results/shared_sample/summary.json`](results/shared_sample/summary.json)。

| Bug | 通过测试 | 失败测试 | 完整排名中的方法/构造方法 | B 候选数 |
| --- | ---: | ---: | ---: | ---: |
| Lang-1 | 2290 | 1 | 2403 | 20 |
| Lang-3 | 2285 | 1 | 2396 | 20 |
| Lang-4 | 2284 | 1 | 2393 | 20 |

这是一批中期流程样本。C 的补丁标签、排除审核和 Top-k/MRR 评估尚待完成；LLM 重排由 B 接续。
同分方法的字母顺序只是稳定显示顺序，请保留 `rank_min` / `rank_max` / `tie_size`。

## 共同约定与验证

- [数据接口与 method ID 规则](docs/person_a_data_contract.md)
- [模型输入 JSON Schema](configs/model_input.schema.json)
- [给 B、C 的简短交接报告](docs/person_a_handoff.md)
- [共享样本的验证记录](results/shared_sample/validation.json)
- [离线单元测试记录](results/shared_sample/unit-tests.log)
- [样本版本与文件 SHA-256](data/sample/release.json)

方法分数取**方法内部最高的行级分数**。B 的模型输入不包含修复补丁或正确答案；C 单独建立评估标签。
历史环境/采集失败与方法级基准排除分开记录。`data/excluded.csv` 的空表头表示 C 尚未完成排除审核。

仓库提交了复现代码、接口说明、可直接读取的 B 输入，以及压缩后的 C 数据。
本机依赖、真实工作 checkout、旧交接包、个人自动化说明和临时文件保留在本地。
