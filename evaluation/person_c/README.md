# Person C：方法级故障定位评估

本目录包含独立评估器、A 数据适配器、补丁标签证据、真实 baseline 和 B 输出接口。模型输入继续使用仓库的 `data/sample/B/`；本目录中的补丁与标签仅用于评估。

已接入 Lang-1、Lang-3、Lang-4，均登记为 dev 联调样本。Ochiai/DStar 的 Top-1 为 3/3，MRR@20 和完整 MRR 均为 1.0。当前样本已达到 baseline 上限，不能据此声称 LLM 有提升。Person C（Alina Wu）已于 2026-10-22 确认标签复核完成，已接入 B 固定提交的 9 个 run，108 个重排/融合配置在当前三例上均与 baseline 持平。

## 复现

从仓库根目录进入本目录，Python 3.10+ 标准库即可评分与测试：

```bash
cd evaluation/person_c
python3 -m unittest discover -s tests -v
python3 evaluate.py --manifest real/data/manifest.json --labels real/data/labels.json --predictions real/data/ochiai.json real/data/dstar.json --split dev --output-dir runs/baseline-mrr20
python3 evaluate.py --manifest real/data/manifest.json --labels real/data/labels.json --predictions real/data/ochiai.json real/data/dstar.json --split dev --rank-cutoff 0 --output-dir runs/baseline-full
```

输出目录必须不存在。默认 `eval` 会拒绝这份全部为 dev 的清单。结果中的输入路径相对于运行命令的当前目录，SHA-256 用于核对实际文件。

## 材料

- [Lang-5 至 Lang-14：新评估集、标签与 baseline](cohorts/lang-expansion-20261023/README.md)
- [真实结果、标签定义和复现细节](real/README.md)
- [标签及排除审核记录](real/review_decisions.json)
- [逐块补丁映射证据](real/data/mapping.json)
- [B 输出适配、异常规则与离线复现命令](PERSON_B.md)
- [B 评分汇总](real/results/person_b/report.md)
- [B 输出模板](handoff_B/README.md)
- [评估输入约定](DATA_CONTRACT.md)
- [标签核查流程](GROUND_TRUTH.md)
- [验证记录](VALIDATION.txt)

`demo/` 与 `demo_result/` 全部为人工构造的软件测试数据，不属于真实研究结果。`templates/` 为通用接口示例，不是正式样本清单。

`import_person_a.py` 锁定当前 A release，拒绝版本、哈希、候选集合或审阅证据不一致的数据。共享 Java parser 的固定版本保存在 `vendor/`，仅 `--reparse` 需要其依赖；普通评分不需要 Java、Docker 或模型 API。

下一步按预先固定的范围扩充样本，使用新清单和固定 B commit 重跑适配与评分。保留所有运行失败记录，不能按 baseline 表现挑选主评估样本。
