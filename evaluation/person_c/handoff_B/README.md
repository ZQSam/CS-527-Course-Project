# 给 B：模型输出接入 C

此目录可单独交给 B，包含输出模板和说明；没有补丁、标签或修复版代码。整份 C 评估包包含答案，不能作为模型上下文输入。

输入继续使用 A 的 `data/sample/B/`（release `person-a-lang-v1`，仓库 commit `99e7b385023f5d601f8cca01125c52ca02cba674`）。不需要为 C 重做覆盖率或改方法 ID。

`predictions_template.json` 已填入 Lang-1/3/4 的实际候选 ID。它是未运行模板，所有记录为 `not_run`，没有伪造 LLM 预测或费用。

每个配置输出一个 JSON：

1. 保留 dataset、bug_id 和完整 candidate_method_ids。
2. 成功时 status 改为 `ok`，ranking 填完整候选的有序排列，第一项最可疑；不得重复、遗漏或新增 ID。
3. 调用失败填写 `call_error`、`parse_error` 或 `timeout`，另加 error；保留已消耗用量。未调用保持 `not_run`。
4. usage 填实际 input_tokens、output_tokens、cost_usd、latency_seconds；未知为 null，重试消耗也计入。
5. configuration 填具体模型版本、prompt 哈希/版本、采样数、种子、融合权重（不用时 null）、代码 revision；原始响应与缓存另行保留。
6. 每种配置使用独立 configuration_id；融合复用已有调用时注明复用关系，避免总账重复计费。

若 B 已采用其他输出结构，交付原始 JSON 与字段说明即可，C 可补转换；这里不要求重写已完成代码。

C 收到真实输出后运行（在评估工具包根目录，最后一项替换为实际输出）：

```bash
python3 evaluate.py --manifest real/data/manifest.json --labels real/data/labels.json --predictions real/data/ochiai.json real/data/dstar.json /absolute/path/b-output.json --split dev --output-dir runs/with-B-001
```

这里对比共同的 MRR@20。候选重排不自动宣称提供完整 MRR；若团队要将候选置顶并把其余方法按 A 的原序接回，需明确记录这一策略。

目前这三例用于开发/联调，正式 eval 需要另行冻结。未收到 B 输出前，C 的真实 baseline 报告不会添加虚构的 LLM 数字。
