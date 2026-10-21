# C 快速开始：基线、正确答案与评估

你负责补丁到 buggy 方法的标签、排除审核、评估、批量实验与报告。A 的小批量数据已可使用。

## 第一步：准备数据

从仓库根目录执行，Python 3.10+，无需 Docker 或第三方包：

```bash
python3 scripts/prepare_sample.py --profile C
```

读取 `.work/sample/C/index.json`。里面每个 bug 的路径都**相对于 `.work/sample/C/`**。
脚本先核对压缩包和逐文件 SHA-256，再核对完整排名及覆盖率；重复执行不会覆盖已修改的文件。
原始压缩包是 [`data/sample/person-a-lang-C.zip`](../data/sample/person-a-lang-C.zip)。

```python
import json
from pathlib import Path

root = Path(".work/sample/C")
index = json.loads((root / "index.json").read_text(encoding="utf-8"))
for bug in index["bugs"]:
    ranking = json.loads((root / bug["rankings"]["ochiai"]).read_text(encoding="utf-8"))
    print(bug["bug_id"], ranking["methods"][0]["method_id"])
```

## 你收到的材料

| 文件 / index 字段 | 内容 |
| --- | --- |
| `rankings` | 完整 Ochiai、DStar 排名，含 zero-score 方法与构造方法、并列范围；同目录有 CSV |
| `methods` | 共享 Java parser 产生的方法身份、源码、边界与哈希 |
| `coverage` | 每条测试的 PASS/FAIL 和覆盖列；原始 matrix / GZoltar 文件 losslessly gzip 归档 |
| `source_checkout` | 对应 buggy 版本全部已索引生产源码与失败测试文件 |
| `validation` | 源码映射、测试集合、原始列 Ochiai 与 GZoltar 的核对结果 |
| `model_inputs/` | 与 B 读取的 JSON 字节一致，便于核对候选集合 |
| `data/bugs.csv`、`successful_bugs.txt` | 成功处理的 cohort |
| `failures.jsonl` | 历史操作/采集/解析失败及其证据路径，包含已修复的尝试 |
| `data/excluded.csv` | 待 C 审核的排除表头；不是“已确认没有排除”的结论 |

`source_checkouts/` 是用于检查和标签映射的源码快照，未包含构建所需的完整仓库。
运行记录中的 `/workspace/...` 是历史容器路径。读取样本请使用 index 中的相对路径。

## 第二步：核对方法身份

在 x86_64 WSL/Linux 中安装 pinned parser，再重新解析快照：

```bash
python3 scripts/setup_python.py
PYTHONPATH="$PWD/.deps" python3 scripts/prepare_sample.py --profile C --check-source
```

依赖装在仓库根目录的 `.deps/`，位于数据 profile 之外。依赖安装后不需要网络、Docker 或原始工作 checkout。
请复用 `fl/java.py` 的 `SourceIndex` 做 buggy 源码的方法识别，避免 A/C 生成不同的 method ID。

## 第三步：标签与评估

1. 获取对应开发者补丁，先核对 patch 方向，使行号对应 buggy 版本。
2. 用 buggy 源码快照和共享 parser 映射修复涉及的方法；纯新增行按插入点的包含方法处理。
3. 如不存在可映射的 buggy 方法，明确记录排除原因；运行失败与方法级排除分别保存。
4. 明确并列排名的 Top-k/MRR 规则，保留 `rank_min` / `rank_max` / `tie_size`。
5. 比较 A 的完整 Ochiai/DStar 排名与 B 的重排/融合结果，并记录候选集合未命中等情况。

方法分数是方法内的最高物理行分数。DStar 指数为 2，JSON 的正无穷保存为字符串 `Infinity`。
目前没有已完成的补丁标签或 Top-k/MRR 结论。详细格式见[数据约定](person_a_data_contract.md)。

扩大采集时请按[环境和复现实验](reproducing_person_a.md)创建新的可执行 checkout。
共享 ZIP 中只放数据和证据；代码、依赖安装脚本和说明使用当前仓库版本。
