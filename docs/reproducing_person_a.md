# 重新采集 Person A 数据

读取现成数据请直接按[仓库首页](../README.md)操作。下面的步骤用于重建环境、重新运行真实 bug。

## 环境

Windows 使用 WSL2 Ubuntu，Docker Desktop 开启 Ubuntu 的 WSL integration，并切换到 Linux engine。
仓库放在 WSL 的 Linux 文件系统，例如 `~/cs527-llm-fl`，避免放在 `/mnt/c` 或 `/mnt/e`。

在 x86_64 WSL/Linux 的仓库根目录执行：

```bash
python3 scripts/setup_python.py
bash scripts/build_environment.sh
bash scripts/test.sh
bash scripts/run.sh python3 scripts/smoke_defects4j.py
bash scripts/run.sh python3 scripts/report_milestone1.py
bash scripts/run.sh python3 scripts/run_milestone2.py
bash scripts/run.sh python3 scripts/build_handoff.py
```

第一次 Docker 构建和依赖安装需要网络，可能耗时较长。运行 A 的流程不需要模型 API key。
`build_environment.sh` 将当前 Linux UID/GID 传入容器，以便输出由当前用户拥有。
容器有真实的 `researcher` 用户及 home 目录；请勿只指定无 passwd 记录的数值 UID，
否则部分 Lang 测试可能因 Java `user.home` 异常而出现无关失败。

## 固定版本

- Defects4J `v2.0.0`，commit `01f13c69425fb8a0db290d12b1d48da1641bf6a9`。
- Temurin JDK 8：固定 Docker 基础镜像 digest，已记录的运行版本为 `8u504`。
- GZoltar CLI / agent `1.7.3`，构建时核对 Maven artifact checksum。
- `tree-sitter==0.25.2`、`tree-sitter-java==0.23.5`，安装时核对 wheel hash。
- 实验 timezone 为 `America/Los_Angeles`，按 Defects4J 要求设置。

Java 8 要求见 [Defects4J v2.0.0 README](https://github.com/rjust/defects4j/blob/v2.0.0/README.md)。
实际工具版本与镜像记录由脚本写入 `results/environment/`，不依赖开发者机器的系统 Java。

## 配置与输出

- `configs/person_a.json`：项目、bug IDs、checkout 路径、超时。先完成完整测试及逐个触发测试复现。
- `configs/coverage.json`：使用哪个成功 baseline、覆盖率和排名路径、候选数。
- `configs/handoff.json`：从成功覆盖率 cohort 构建 B/C 交接包。

扩大 cohort 时同步修改前两个配置。Milestone 2 要求对应 bug 先有成功的 Milestone 1 记录。
同一台机器已有保留 checkout 时，可只运行需要的阶段；新机器必须先重新完成 Milestone 1。

```text
.work/defects4j/<run_id>/        可执行的真实 buggy checkout
results/environment/           构建、版本、镜像证据
results/milestone1/             编译、完整测试、触发测试与失败详情
results/milestone2/             覆盖率、源码映射、分数校验与阶段状态
data/coverage/<run_id>/         normalized coverage 与 lossless raw archives
data/sbfl/<run_id>/             完整排名、源码索引、行分数与候选预览
data/handoff/<run_id>/          生成的 B/C profiles
output/handoff/                本地 ZIP 与传输 checksum
```

这些运行输出默认留在本地；仓库只跟踪 `data/sample/` 中发布的共享样本和
`results/shared_sample/` 中的交接证据。保留每次失败记录，避免将环境失败自动当作 benchmark 排除。

## 代码入口

| 文件 | 功能 |
| --- | --- |
| `fl/d4j.py` | checkout、compile、export、test，超时和原始失败证据 |
| `fl/coverage.py` | GZoltar 逐测试采集、原始格式校验、zero-hit reconciliation |
| `fl/java.py` | 共享 Java 方法 ID、源码边界、overload/nested class 映射 |
| `fl/sbfl.py` | 物理行 OR、Ochiai/DStar、方法内最大值、稳定排名和并列范围 |
| `fl/handoff.py` | 失败测试源码提取、严格字段/哈希检查、profile 和 ZIP 校验 |
| `scripts/prepare_sample.py` | 使用 GitHub 已发布样本，不运行 benchmark |

单元测试在安装 parser 后无需 Docker、网络或 LLM。正确答案与 Top-k/MRR 由 C 接续实现。
