# Attack on Memory / Attack on Agent

> **Memory governance for multi-agent systems**  
> 让正确的记忆，在正确的时间，以正确的粒度，影响正确的 Agent。

[![CI](https://github.com/MarcelLeon/attack-on-memory/actions/workflows/ci.yml/badge.svg)](https://github.com/MarcelLeon/attack-on-memory/actions/workflows/ci.yml)
[![Scorecard](https://github.com/MarcelLeon/attack-on-memory/actions/workflows/scorecard.yml/badge.svg)](https://github.com/MarcelLeon/attack-on-memory/actions/workflows/scorecard.yml)

## Why this matters now

大模型 Agent 从“单轮问答”走向“长期协作”后，真正的瓶颈已经不是参数规模，而是：
- 记忆如何 **可信**（可验证、可回溯）
- 记忆如何 **可控**（按角色披露、可撤回）
- 记忆如何 **可演化**（跨版本继承、可回滚）

Attack on Memory 不是另一个 RAG 包装器，而是面向多 Agent 的记忆协议层：
**Graph Retrieval + Time-window Retrieval + Governance + BranchWorldModel**。

## 3-minute quickstart

```bash
# 1) run unit tests
PYTHONPATH=src python3 -m unittest discover -s tests -v

# 2) validate scenario specs
PYTHONPATH=src python3 examples/validate_scenarios.py

# 3) run simulation demo
PYTHONPATH=src python3 examples/simulation_runner.py
```

## Without vs With (expected)

- **Without structured memory**：上下文断裂，重复犯错，越权披露难追踪。
- **With Attack on Memory**：记忆可寻址、可审计、可按角色投影，且能在分支决策中量化比较。

详见：`docs/experiments-and-value.md`

## 一、金字塔顶层结论
如果你理解《进击的巨人》里“道路、继承、记忆影响决策”的机制，你就已经理解了本项目的核心一半。  
另一半是把它从叙事机制变成工程机制：`可寻址`、`可引用`、`可继承`、`可撤回`、`可审计`。

## 二、第一性原理（项目成立的最小前提）
1. 世界是部分可观测的，任何 Agent 都只能看到局部事实。  
2. 决策质量不仅取决于模型参数，更取决于可用记忆的质量与时效。  
3. 多主体协作的瓶颈本质是记忆传递带宽，而不是单体智能上限。  
4. 记忆天然会出错，错误必须可隔离、可降权、可回滚。  
5. 协作系统要稳定，必须“局部自治 + 全局协调”，不能全局同质化。  
6. 安全不是附加项，记忆流动本身就必须内生权限与边界。

## 三、动漫原理到工程原理的映射（含 bad case）
| 动漫中的机制 | 框架中的映射 | 关键差异 | 为什么要这样改造 |
|---|---|---|---|
| 道路（Path）连接艾尔迪亚人 | `Memory Fabric` 连接多 Agent 与人类节点 | 我们是显式协议，不是隐式心灵连接 | 现实系统必须可审计、可治理 |
| 始祖巨人的统摄能力 | `Memory Governor` 治理策略与权限 | 不是“任意改写记忆”，而是策略执行与审计 | 防止单点滥权与记忆污染 |
| 进击的巨人跨代记忆影响 | `Lineage Transfer` 跨版本经验迁移 | 迁移的是证据化记忆原子，不是整段意识 | 保持可验证与可回滚 |
| 艾伦只透露部分记忆给格里沙 | `Selective Disclosure` 选择性披露 | 通过单向权限图与粒度控制实现 | 兼顾协作效率与隐私安全 |
| **艾伦最终态=进击+始祖能力叠加** | **权限融合攻击（Privilege Fusion）** | 动漫可“近乎全能”；工程上必须禁止 | 职责分离、爆炸半径限制、紧急熔断 |

**必须明确的超自然不映射项**：  
- 不存在无限带宽、零延迟、零失真的记忆互通。  
- 不存在无代价全局改写。  
- 不存在不可审计的“天启式正确答案”。  
- 不存在绝对宿命时间线；只有可更新的假设分支。

## 四、核心概念
### 1) Memory Atom（记忆原子）
定义：最小可验证记忆单元，不是“长文本印象”。  
结构：`claim + evidence + source + confidence + scope + time + ttl + branch_id`。  
例子：  
`claim`: 用户偏好把英语学习拆成早/中/晚  
`evidence`: 对话记录 #214  
`confidence`: 0.86  
`scope`: 学习规划任务有效  
这比“用户爱学英语”更可用，因为可验证、可更新、可失效。

### 2) Addressable / Referable / Inheritable
定义：  
`可寻址`：每个原子有稳定 ID。  
`可引用`：新结论必须引用旧证据链。  
`可继承`：新 Agent 能继承前代已验证经验。  
例子：新客服 Agent 接手时，可直接引用“同类工单决策链”，而非重学一遍。

### 3) Selective Disclosure（选择性披露）
定义：按角色、任务、时点、敏感度返回“部分记忆投影”。  
例子：策略 Agent 可向执行 Agent 透露“风险阈值”，但不透露原始客户隐私字段。  
与动漫差异：我们用权限与审计实现“单向影响”，不是超自然设定。

### 4) BranchWorldModel（分支世界模型）
定义：把“可能世界”显式建模为多个分支，用于反事实推演与决策比较。  
例子：  
分支 A：先降级服务再扩容。  
分支 B：先扩容再限流。  
系统比较两条分支的风险与成本，再把结论回注当前决策。  
与动漫差异：我们不假设宿命时间线，而是维护并行假设与可证伪路径。

### 5) 图遍历检索（Graph Retrieval）
定义：不仅按语义相似找文本，还沿“支持/反驳/因果/继承”边检索证据。  
例子：定位一次线上故障时，系统沿“同模块->同告警->同修复策略”图边找历史解法。

### 6) 时间窗检索（Time-window Retrieval）
定义：按事件发生时间与有效时间筛选记忆，防止过期经验误导当前。  
例子：去年促销期限流策略不一定适用于今天的架构版本，时间窗会自动降权或屏蔽。

### 7) Eval & Observability（评估与可观测层）
定义：持续回答“这套记忆系统到底有没有变好”。  
关键指标：命中率、冲突率、污染率、重复错误率、延迟、token 成本、任务成功率。  
意义：没有这一层，框架只有叙事，没有科学性。

## 五、分层架构（从知识到行动）
1. Capture/Extraction：从对话、行为、日志抽取候选记忆原子。  
2. Storage：短期记忆、长期记忆、共享记忆分层存储。  
3. Index/Retrieval：向量检索 + 图遍历 + 时间窗过滤。  
4. Governance：权限、披露、撤回、审计、污染隔离。  
5. BranchWorldModel：管理分支假设与反事实推演。  
6. Runtime Interaction：任务执行、上下文装配、结果回写。  
7. Eval & Observability：指标、告警、回归评测闭环。

## 六、这套框架解决什么现实问题
1. 减少组织失忆：经验不再随人员流动而消失。  
2. 降低重复犯错：历史错误可被检索并提前拦截。  
3. 提升交接效率：新 Agent/新人可继承高质量决策链。  
4. 控制记忆风险：敏感信息可按策略披露而非全量扩散。  
5. 支持长期任务：在目标变化中保持因果一致与可回滚。  
6. 让多 Agent 协作可追责：每个结论都能回到证据与责任主体。

## 七、哲学、生物学与人类分工的一致性
1. 哲学一致性：保留个体主体性，同时建立集体连续记忆。  
2. 认知科学一致性：对应情景记忆、语义记忆、程序记忆的分层协作。  
3. 生物学一致性：更像免疫记忆的“按需激活与错误隔离”，不是全脑广播。  
4. 组织学一致性：符合分工社会的核心规律，即“专业自治 + 低摩擦协作”。

## 八、边界与反模式（我们明确不做什么）
1. 不做“全量共享记忆乌托邦”。  
2. 不允许静默覆盖他人记忆原子。  
3. 不把向量相似度当作真实性证明。  
4. 不以单一高权限角色替代治理流程。  
5. 不用不可解释的黑盒规则处理跨 Agent 影响。

## 九、核心概念词典（定义 + 类比 + 例子）
| 概念 | 定义 | 动漫类比 | 现实例子 |
|---|---|---|---|
| `Memory Atom` | 最小可验证记忆单元 | 一段可被“看到”的关键记忆片段 | “用户把英语学习分早/中/晚，证据=会话#214，置信0.86，TTL=30天” |
| `Addressable` | 记忆有稳定 ID，可精确定位 | 指向某段特定记忆而非模糊印象 | 原子 `mem_9f2...` 被策略直接引用 |
| `Referable` | 新结论必须引用旧证据 | 格里沙被特定记忆触发决策 | 新计划引用历史成功策略与失败案例 |
| `Inheritable` | 经验可跨 Agent/版本迁移 | “继承者”得到前代影响 | 新客服 Agent 继承故障处置链 |
| `Selective Disclosure` | 只披露任务所需片段 | 艾伦只展示部分画面 | 执行 Agent 看到阈值，不看到敏感原文 |
| `Graph Retrieval` | 沿关系边检索证据 | 记忆之间存在可追踪联系 | 按 `supports/contradicts/derived_from` 找证据链 |
| `Time-window Retrieval` | 按时间窗过滤有效记忆 | 不同时间点的记忆有效性不同 | 只取当前架构版本后的运维经验 |
| `BranchWorldModel` | 显式管理反事实分支 | 多条可能历史/未来路径 | 比较“先扩容”与“先限流”两分支后回注决策 |
| `Ackerman Class Agent` | 不受“道路记忆注入”影响的独立节点，用于外部校验与抗污染 | 阿克曼血统不受始祖直接改写影响 | 安全审计器/红队/合规模块作为独立真值锚点 |
| `Eval & Observability` | 证明系统质量变化的指标层 | 非剧情概念 | 监控命中率、污染率、重复错误率 |

## 十、v0.1 已落地内容（文档优先）

### 1) 文档入口
- 架构与领域模型：`docs/architecture.md`
- OpenClaw 对接设计：`docs/openclaw-integration.md`
- 实验与价值验证：`docs/experiments-and-value.md`

### 2) 代码模块
- 领域模型：`src/attack_on_memory/domain/models.py`
- 捕获与检索：`src/attack_on_memory/application/services.py`
- 分支世界模型：`src/attack_on_memory/application/branch_world_model.py`
- 治理策略：`src/attack_on_memory/governance/policies.py`
- 运行时上下文：`src/attack_on_memory/runtime/context.py`
- OpenClaw 适配器：`src/attack_on_memory/runtime/openclaw_adapter.py`
- 指标观测：`src/attack_on_memory/evals/metrics.py`

### 3) 快速运行
```bash
PYTHONPATH=src python examples/openclaw_demo.py
PYTHONPATH=src python examples/validate_scenarios.py
PYTHONPATH=src python examples/simulation_runner.py
PYTHONPATH=src python -m unittest discover -s tests -v
```

### 4) 对 OpenClaw 的直接价值
- 在任务开始前，自动注入经过治理后的历史记忆。
- 在任务结束后，自动回写结果并更新指标闭环。
- 在分支决策中，能量化比较候选方案并回注主流程。
- 可把真实运行日志转为 scenario，持续做离线回放和回归验证。

## 十一、工程化与开源发布基线（新增）
- CI（多 Python 版本）: `.github/workflows/ci.yml`
- 供应链安全评分（Scorecard）: `.github/workflows/scorecard.yml`
- 自动依赖更新（Dependabot）: `.github/dependabot.yml`
- 贡献流程：`CONTRIBUTING.md`、`.github/pull_request_template.md`
- 社区治理：`CODE_OF_CONDUCT.md`、`SECURITY.md`、`.github/ISSUE_TEMPLATE/*`
- 企业级评审清单：`docs/ENTERPRISE_REVIEW_CHECKLIST.md`
- GitHub 爆款发布计划：`docs/GITHUB_LAUNCH_PLAN.md`
- 本地质量门禁：`make quality-gate`（`scripts/quality_gate.py`）
