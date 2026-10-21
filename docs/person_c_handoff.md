# Person C 交接：标签与评估

已完成 Lang-1/3/4 的补丁映射验证、方法级标签、A 数据转换与 baseline 评分，代码和证据在 [evaluation/person_c](../evaluation/person_c/README.md)。

- Ochiai、DStar：Top-1/3/5 均为 3/3，MRR@20 与完整 MRR 均为 1.0。
- 三例全部登记为 dev 联调；不存在正式 held-out 结论或 LLM 提升结论。
- 标签的补丁、源码、blob、哈希与共享 parser 校验已完成，组员人工复核仍为 pending。
- Lang-4 保留构造方法和 translate 两个标签，第 31 行字段修改单独记录。
- 未重跑 Java 测试或采集覆盖率；使用 A 的固定版本数据。

## B 下一步

继续读取 A 的 `data/sample/B/`，输出完整候选重排、配置、状态、实际用量与原始响应。[输出模板与评分命令](../evaluation/person_c/handoff_B/README.md)不包含标签。模型输入不得加入评估目录中的补丁、标签或修复信息。

B 已采用其他格式时，保留原始输出并交给 C 适配即可。

## C 下一步

接到 B 的真实输出后，用相同清单和标签比较。当前 baseline 已饱和，这三例主要验证接口、持平/退步及成本；下一批先固定 bug 范围，再采集并保留失败记录，不按 baseline 成绩筛选主评估集。

## 验证

- C 的 25 项测试全部通过。
- 原仓库 39 项测试中，32 项通过，7 项 WSL/Linux 专用测试在 macOS 上按原规则跳过。
- 原始 ZIP 重新导入并重解析源码，与提交数据逐字节一致。
- MRR@20、完整 MRR 与模拟演示均已重新生成，输入路径为相对路径。

入口：[真实结果与复现说明](../evaluation/person_c/real/README.md)。
