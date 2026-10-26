# Person C 交接：标签与评估

**最新十例的完整交付请阅读 [Person C 中期评估材料](person_c_midterm_evaluation.md)。** 下文保留初始 Lang-1/3/4 的 dev 联调记录，任务状态与旧测试数量不代表扩充批次的当前状态。

已完成 Lang-1/3/4 的补丁映射验证、方法级标签、A 数据转换与 baseline 评分，代码和证据在 [evaluation/person_c](../evaluation/person_c/README.md)。

- Ochiai、DStar：Top-1/3/5 均为 3/3，MRR@20 与完整 MRR 均为 1.0。
- 三例全部登记为 dev 联调；不存在正式 held-out 结论或 LLM 提升结论。
- 标签的补丁、源码、blob、哈希与共享 parser 校验已完成，Person C（Alina Wu）已于 2026-10-22 确认标签复核完成。
- Lang-4 保留构造方法和 translate 两个标签，第 31 行字段修改单独记录。
- 未重跑 Java 测试或采集覆盖率；使用 A 的固定版本数据。

## B 下一步

继续读取 A 的 `data/sample/B/`，输出完整候选重排、配置、状态、实际用量与原始响应。[输出模板与评分命令](../evaluation/person_c/handoff_B/README.md)不包含标签。模型输入不得加入评估目录中的补丁、标签或修复信息。

B schema 1.0/1.1 已接入。C 可直接读取固定 B Git 提交，无需等待 B 合入 main，见 [适配与评分说明](../evaluation/person_c/PERSON_B.md)。

## C 下一步

已使用相同清单和标签完成 B 的 9 个 run、108 个配置评分，均与 baseline 持平；[汇总报告](../evaluation/person_c/real/results/person_b/report.md)及机器可读结果已保存。当前 baseline 已饱和，这三例主要验证接口、持平/退步及成本；下一批先固定 bug 范围，再采集并保留失败记录，不按 baseline 成绩筛选主评估集。

## 验证

- C 的 48 项测试全部通过（包含新增 22 项 B 适配异常/用量/固定提交测试）。
- 原仓库 84 项测试中，77 项通过，7 项 WSL/Linux 专用测试在 macOS 上按原规则跳过。
- 原始 ZIP 重新导入并重解析源码，与提交数据逐字节一致。
- MRR@20、完整 MRR 与模拟演示均已重新生成，输入路径为相对路径。

入口：[真实结果与复现说明](../evaluation/person_c/real/README.md)。
