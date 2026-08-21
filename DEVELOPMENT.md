# Debian 通用代理规则管理器：开发文档

## 1. 文档目的

本文档是项目的实施规格，供开发、测试和后续维护使用。它将需求拆分为可单独验收的小步，明确模块边界、数据结构、转换原则、安全约束和测试标准。

第一版目标不是“自动修改所有客户端的一切配置”，而是建立可靠的规则处理内核，并在明确能力边界的前提下输出：

- 通用规则源。
- Clash/Mihomo 规则与安全配置补丁。
- Loon 规则文件及可审阅片段。
- dae/daed 路由片段。
- 通用域名列表。
- 兼容性、冲突和变更报告。

## 2. 已确认需求

| 项目 | 已确认选择 |
| --- | --- |
| 操作系统 | Debian 11–13 |
| 架构 | Bash 菜单 + Python 规则引擎 |
| 权限 | root 与 sudo 用户 |
| 配置来源 | 本地固定配置文件 |
| 客户端 | Clash、Mihomo、ShellCrash、FlClash、Loon、dae/daed |
| 规则输入 | 域名、关键词、完整网址、GeoSite、Rule-Set、逻辑组合 |
| 不兼容处理 | 优先自动等价转换；不能等价时生成报告并停止该项 |
| 排序 | 按优先级自动排序 |
| 输出 | 一份通用规则源，多种客户端产物 |
| 策略 | 可选择现有组，或创建含 DIRECT/现有故障转移组等成员的新组 |
| 策略组类型 | 每次创建时询问 |
| 上游 | Loyalsoldier/clash-rules |
| 发布 | 同时支持本地使用与 GitHub 发布目录 |
| GitHub 操作 | 只生成文件，由用户手动推送 |
| 写入后行为 | 备份、校验，不自动重载 |

## 3. 设计原则

### 3.1 语义优先

规则转换必须保持匹配语义。不能证明等价时，不得为了“成功生成”而静默扩大或缩小匹配范围。

### 3.2 默认非破坏

- 默认执行预览而不是写入。
- 修改目标必须是用户明确选择的文件。
- 修改前必须备份。
- 校验成功后才允许原子替换。
- 不自动重载服务。

### 3.3 规则数据与客户端配置分离

通用规则源保存“匹配什么”和“期望动作引用”，客户端编译器决定“如何表达”。策略组补丁属于目标配置层，不混入纯域名列表。

### 3.4 确定性输出

相同输入、相同配置和相同编译选项应产生字节级稳定的主要输出，便于 Git diff、复现与测试。

### 3.5 可追踪

每条规则应尽量记录：

- 原始输入。
- 规范化结果。
- 来源。
- 创建时间。
- 目标策略。
- 转换记录。
- 警告或失败原因。

### 3.6 保守兼容

客户端能力来自明确的目标配置、内核探测或用户选择。不能确认时按保守能力集处理，不能仅凭文件名猜测全部特性。

## 4. 总体架构

```text
Bash 入口与中文菜单
        │
        ▼
Python 应用服务层
├── 输入解析
├── 规则规范化
├── 冲突与覆盖分析
├── 策略组建模
├── 客户端能力判定
├── 多目标编译
├── 配置补丁
└── 报告与清单
        │
        ▼
文件与网络适配层
├── 本地 YAML/文本
├── 备份与原子写入
├── 上游下载与缓存
└── Git-ready 发布目录
```

### 4.1 Bash 层职责

- 检测 Debian 版本、Python、sudo 和基础命令。
- 提供中文编号菜单。
- 收集路径与选项。
- 根据需要使用 sudo 执行受控的文件操作。
- 调用 Python CLI，并直接透传退出码。
- 不自行解析 YAML，不用 `sed` 修改结构化配置。

### 4.2 Python 层职责

- 所有业务逻辑。
- YAML 的保序读写。
- 规则解析与规范化。
- 策略组图分析。
- 编译各客户端输出。
- 生成 diff、报告和 manifest。
- 实施备份、校验与原子替换事务。

### 4.3 推荐依赖

运行时建议：

- Python 3.9+，兼容 Debian 11 自带环境。
- `ruamel.yaml`：尽量保留 YAML 顺序、样式和注释。
- `platformdirs`：确定缓存与状态目录，可选。
- 标准库：`argparse`、`dataclasses`、`urllib`、`hashlib`、`tempfile`、`difflib`、`ipaddress`、`idna`。

测试依赖：

- `pytest`
- `pytest-cov`
- `hypothesis`，用于域名与 URL 解析性质测试，可作为开发依赖。

不建议第一版引入完整 TUI 框架；保持 Bash 菜单简单可审计。

## 5. 目录设计

```text
proxy-rule-manager/
├── bin/
│   └── proxy-rule-manager          # Bash 入口
├── src/rule_manager/
│   ├── __init__.py
│   ├── cli.py                      # Python CLI
│   ├── models.py                   # 中间数据模型
│   ├── parser.py                   # 输入解析
│   ├── normalize.py                # 规范化与去重
│   ├── ordering.py                 # 优先级排序
│   ├── analyzer.py                 # 冲突、覆盖、引用分析
│   ├── capabilities.py             # 客户端能力模型
│   ├── upstream.py                 # 下载、缓存、校验
│   ├── workspace.py                # 规则项目读写
│   ├── patcher.py                  # 配置补丁事务
│   ├── validators.py               # 语法与语义校验
│   ├── reports.py                  # 报告与 manifest
│   └── compilers/
│       ├── base.py
│       ├── clash.py
│       ├── loon.py
│       ├── dae.py
│       └── domain_list.py
├── config/
│   ├── defaults.yaml
│   ├── capabilities.yaml
│   └── upstreams.yaml
├── examples/
├── tests/
│   ├── fixtures/
│   ├── unit/
│   ├── integration/
│   └── golden/
├── README.md
└── DEVELOPMENT.md
```

## 6. 通用数据模型

### 6.1 RuleSource

表示规则来源：

```yaml
id: custom-finance
kind: manual
label: 手工输入：金融服务
location: null
retrieved_at: null
sha256: null
license: null
```

`kind` 候选值：

- `manual`
- `local-file`
- `remote-url`
- `loyalsoldier`
- `geosite`

### 6.2 Rule

建议的逻辑字段：

```yaml
id: rule_01J...
type: domain-suffix
value: example.com
policy: 金融服务
options: []
source_id: custom-finance
original: "*.Example.COM/path"
enabled: true
priority: 200
metadata:
  unicode_value: null
  created_at: "2026-08-21T11:00:00+08:00"
```

第一版 `type`：

- `domain`
- `domain-suffix`
- `domain-keyword`
- `geosite`
- `rule-set`
- `logic-and`
- `logic-or`
- `logic-not`

逻辑规则的 `value` 不应长期使用未解析字符串，内部应转换为抽象语法树。

### 6.3 LogicExpression

```yaml
operator: and
children:
  - type: domain-suffix
    value: example.com
  - type: network
    value: tcp
```

虽然第一版菜单不单独暴露所有底层匹配类型，但解析器必须能保留逻辑表达式中未知或客户端特有的叶子节点，避免错误丢失信息。

### 6.4 PolicyGroup

```yaml
name: 金融服务
type: select
members:
  - kind: group
    name: 故障转移
  - kind: builtin
    name: DIRECT
parameters: {}
```

`parameters` 用于保存 `url-test`、`fallback`、`load-balance` 的测试 URL、间隔、容差、策略等参数。

### 6.5 CapabilityProfile

```yaml
target: clash-meta
features:
  rule_set: true
  geosite: true
  logic_rule: true
  remote_provider: true
  policy_group_patch: true
limits:
  max_expanded_rules: 50000
evidence:
  mode: detected
  version: "1.x"
```

能力证据模式：

- `detected`：根据可执行文件及版本得到。
- `declared`：用户显式选择。
- `config-inferred`：从现有字段有限推断。
- `conservative`：无法确认，使用最低能力集。

## 7. 输入解析规范

### 7.1 处理流水线

```text
原始行
→ 去除 BOM 与首尾空白
→ 跳过空行和整行注释
→ 识别显式规则语法
→ 否则尝试 URL
→ 否则尝试域名/通配域名
→ IDNA 转换
→ 语法校验
→ 生成中间 Rule
→ 去重与冲突分析
```

### 7.2 URL 处理

- 允许 `http://`、`https://` 和带端口 URL。
- 只提取 hostname，不保留用户名、密码、路径、查询或 fragment。
- 对无协议但明显含路径的输入，可显示建议，不应无提示猜测。
- URL 中出现 IP 时标记为“非域名输入”，由未来 IP 模块处理或本次跳过。

### 7.3 域名规范化

- 转小写。
- 移除末尾根点 `.`。
- 校验每个 label 长度及总长度。
- Unicode 使用 IDNA 编码。
- `*.` 与前导 `.` 转为 `domain-suffix`。
- 不允许中间任意通配符，例如 `api.*.example.com`，除非未来加入明确语法。

### 7.4 显式 Clash 风格规则

至少解析前三列：`TYPE,VALUE,POLICY`，其余作为 options。用户在交互中重新选择策略时，必须明确询问是保留原策略还是批量覆盖。

### 7.5 注释

手工输入支持：

```text
# 整行注释
example.com  # 行尾注释
```

行尾 `#` 只有在不属于 URL fragment 且处于可安全识别的位置时才视为注释。

## 8. 规范化、去重与冲突

### 8.1 去重键

普通规则的建议去重键：

```text
(type, normalized_value, normalized_options)
```

策略不是去重键的一部分，因为相同匹配指向不同策略属于冲突，不是两条独立的正常规则。

### 8.2 冲突类型

- **完全重复**：规则与策略均相同。
- **策略冲突**：匹配相同但策略不同。
- **包含覆盖**：`DOMAIN-SUFFIX,example.com` 覆盖 `DOMAIN,a.example.com`。
- **关键词过宽**：关键词可能覆盖多个已有域名；只警告，不自动删除。
- **兜底截断**：`MATCH` 或 `FINAL` 位于新增规则之前。
- **Provider 缺失**：规则引用未定义 provider。
- **策略缺失**：规则指向不存在的策略。
- **组循环**：A 引用 B，B 又引用 A。

### 8.3 自动处理边界

- 完全重复：默认跳过。
- 策略冲突：必须由用户选择保留、新策略或调整顺序。
- 包含覆盖：默认保留更具体规则，并给出其可能冗余的提示；不同策略时不得删除。
- 循环引用与缺失策略：阻止写入。

## 9. 排序算法

### 9.1 基础权重

| 规则类型 | 建议权重 |
| --- | ---: |
| domain | 100 |
| domain-suffix | 200 |
| domain-keyword | 300 |
| logic | 400 |
| custom rule-set | 500 |
| geosite | 600 |
| public broad rule-set | 700 |
| geoip | 800 |
| match/final | 900 |

数值越小越靠前。

### 9.2 稳定排序

同一权重内保持原始相对顺序；对新建的纯规则文件，可以按规范化值二次排序以获得确定性输出。两种模式必须区分：

- `patch`：保守，优先保留原配置顺序。
- `compile`：确定性，允许标准化排序。

### 9.3 托管区块

为避免重排完整用户配置，Clash/Mihomo 补丁器建议维护带注释标记的托管区块：

```yaml
rules:
  # rule-manager:begin finance
  - DOMAIN-SUFFIX,example.com,金融服务
  # rule-manager:end finance
  - MATCH,默认策略
```

如果 YAML 库不能稳定保留标记，必须改用结构化元数据文件记录插入项，不得依赖脆弱的字符串替换。

## 10. 客户端能力与编译策略

### 10.1 Clash/Mihomo

输出类型：

- Classical rule-provider payload。
- Domain payload（仅当匹配类型符合要求）。
- 配置中的 `rule-providers` 片段。
- `rules` 引用片段。
- `proxy-groups` 补丁。

需要区别传统 Clash、Clash Premium、Mihomo 的能力，不应把 Mihomo 特性写入未知内核配置。

### 10.2 ShellCrash 与 FlClash

将其视为“运行或管理 Clash/Mihomo 配置的环境”，能力最终由实际核心决定。探测优先级：

1. 用户指定核心。
2. 可执行文件 `--version`。
3. 配置中特征字段。
4. 保守模式。

第一版不得依赖 ShellCrash 的内部临时目录作为唯一配置位置；路径必须由用户确认。

### 10.3 Loon

第一版输出：

- 独立 Rule-Set 文件。
- `[Rule]` 可粘贴片段。
- 策略引用检查报告。

完整策略组写回要等格式样本和回归测试充分后再开放。无法对应的逻辑规则进入报告。

### 10.4 dae/daed

第一版输出：

- 路由规则片段。
- 规则到目标出站/组名的映射清单。
- 无法等价表达项的报告。

dae/daed 不是 Clash YAML，必须使用独立编译器。第一版默认不直接覆盖完整 dae 配置。

### 10.5 通用域名列表

只包含能无损表达为域名的条目：

```text
example.com
.example.org
```

关键词、逻辑规则、GeoSite 和不能可靠展开的 Rule-Set 不应伪装成普通域名写入。

## 11. Rule-Set 与 GeoSite 展开

### 11.1 展开条件

必须同时满足：

- 目标客户端不支持原生引用，或用户明确要求展开。
- 数据源可验证、格式已识别。
- 展开后能保持匹配含义。
- 预计条目数未超过配置阈值。

### 11.2 安全阈值

默认建议：

- 单规则集最大展开条目：20,000。
- 单次任务最大展开条目：50,000。
- 超过阈值必须停止并要求用户改变输出方式。

阈值应可配置，但报告中始终记录实际数量。

### 11.3 下载与缓存

- 仅接受 HTTPS，除非用户明确允许本地可信 HTTP 源。
- 限制响应大小和下载超时。
- 不自动跟随到非 HTTP(S) 协议。
- 缓存以 URL 摘要和内容 SHA-256 标识。
- 支持离线复用已验证缓存。
- 记录 ETag/Last-Modified（若存在）。
- 网络失败时不得拿过期缓存冒充最新内容，必须标记缓存时间。

### 11.4 Loyalsoldier 适配器

上游适配器负责：

- 保存规则集名称到 URL 的映射。
- 识别其 YAML/text payload 类型。
- 记录上游分支与内容摘要。
- 将第三方规则转换为内部 `Rule`。
- 保留来源与许可说明。

上游仓库结构可能变化，映射应放在 `config/upstreams.yaml`，不要硬编码散落在业务代码中。

## 12. Clash/Mihomo 配置补丁事务

### 12.1 阶段

```text
选择目标文件
→ 权限与类型检查
→ 读取并解析
→ 建立配置模型
→ 生成候选修改
→ 内部校验
→ 显示摘要和 diff
→ 用户确认
→ 创建备份
→ 写入同目录临时文件
→ 重新解析临时文件
→ 可选内核校验
→ 原子替换
→ 输出报告
```

### 12.2 路径安全

- 使用真实路径解析符号链接，并显示最终目标。
- 拒绝目录、设备文件、FIFO 和 socket。
- 不允许空路径。
- 写入前再次比较 inode/mtime/size，避免确认后文件被外部更新。
- 对符号链接默认修改其目标，但必须明确显示；未来可提供替换链接本身的选项。

### 12.3 备份

命名建议：

```text
config.yaml.rule-manager-backup.20260821T110530+0800
```

备份应包含：

- 完整原始字节。
- 文件权限、所有者和时间信息清单。
- SHA-256。
- 任务 ID。

备份默认放在独立状态目录，避免被客户端扫描为额外配置；也允许用户指定目录。

### 12.4 原子写入

- 临时文件必须创建在目标文件同一文件系统。
- 写入后 `flush` 与 `fsync`。
- 设置与原文件一致的权限和所有者。
- 校验临时文件。
- 使用原子替换。
- 对包含目录项更新的重要场景，对父目录执行 `fsync`。

### 12.5 并发修改保护

从读取到替换期间保存原文件的 SHA-256、mtime、size 和 inode。若写入前不同，终止操作并重新生成 diff。

### 12.6 恢复

恢复同样是事务：

- 列出备份时间、摘要和原路径。
- 展示当前文件与备份差异。
- 备份当前版本作为“恢复前备份”。
- 校验待恢复文件。
- 原子替换。
- 不自动重载。

## 13. 策略组图分析

### 13.1 名称空间

Clash/Mihomo 中需要同时识别：

- 内置动作：`DIRECT`、`REJECT` 等。
- `proxies` 中的单个节点名。
- `proxy-groups` 中的组名。
- provider 产生的节点集合。

### 13.2 循环检查

把策略组视为有向图。组 A 引用组 B 时添加边 `A → B`，使用深度优先搜索或 Tarjan 算法检测环。

阻止示例：

```text
金融服务 → 故障转移 → 金融服务
```

### 13.3 类型参数

- `select`：至少一个成员。
- `fallback`：成员之外通常需要测试 URL 与 interval。
- `url-test`：需要测试 URL、interval，可选 tolerance。
- `load-balance`：需要目标内核支持，并校验 strategy。

菜单创建组时按类型逐项询问必填参数，不使用隐藏默认值。

## 14. 校验体系

### 14.1 语法校验

- YAML 可解析。
- 必要顶层键类型正确。
- `rules`、`proxy-groups`、`rule-providers` 的结构正确。
- 生成文本满足目标格式的行语法。

### 14.2 语义校验

- 所有策略引用存在。
- 所有 RULE-SET provider 存在。
- 组成员存在。
- 无策略组循环。
- 无多个提前终止的兜底规则。
- 规则选项适用于对应类型。
- 远程 provider URL 与 behavior 合理。

### 14.3 外部内核校验

如果检测到兼容内核，先展示将执行的只读测试命令，再运行配置测试。外部校验失败时不得写入正式配置。

由于不同内核命令行参数可能变化，命令模板必须按核心类型和版本映射，不应拼接未经验证的参数。

## 15. 报告设计

每次任务产生人类可读 Markdown 与机器可读 JSON/YAML 摘要。

### 15.1 变更报告

- 任务 ID 和时间。
- 输入文件及摘要。
- 新增、跳过、转换、冲突和失败数量。
- 新增策略组。
- 备份路径。
- 输出路径。
- 是否执行外部内核校验。
- 明确说明“未自动重载”。

### 15.2 兼容性报告

每条非原生规则记录：

```yaml
rule_id: rule_01J...
target: loon
status: converted
from: rule-set
to: expanded-domain-rules
expanded_count: 842
semantic_equivalence: exact
warnings: []
```

状态：

- `native`
- `converted`
- `skipped`
- `blocked`
- `needs-review`

### 15.3 manifest.yaml

建议字段：

```yaml
schema_version: 1
project_version: 0.1.0
generated_at: "2026-08-21T11:00:00+08:00"
sources: []
targets: []
files:
  - path: dist/clash/finance.yaml
    sha256: "..."
    rule_count: 120
warnings: []
```

为保证可复现构建，可提供 `--reproducible` 模式：不把动态时间写入主要编译文件，只在单独报告中记录运行时间。

## 16. Bash 菜单与 Python CLI 接口

### 16.1 原则

Bash 只负责交互，不负责业务逻辑。所有菜单动作都映射为可单独测试的 Python 子命令。

### 16.2 计划子命令

```text
rule-manager inspect-config PATH
rule-manager add-rules --project DIR --input FILE --policy NAME
rule-manager import-upstream --name NAME --project DIR
rule-manager create-group --config PATH --spec FILE --dry-run
rule-manager compile --project DIR --target clash|loon|dae|domain-list
rule-manager patch-clash --config PATH --project DIR --dry-run
rule-manager validate --config PATH --target TARGET
rule-manager diff --config PATH --candidate PATH
rule-manager backups list --config PATH
rule-manager backups restore --backup ID --dry-run
rule-manager publish-dir --project DIR --output DIR
```

默认 `patch` 与 `restore` 应为 dry-run，只有显式 `--apply` 才写入。

### 16.3 退出码

| 退出码 | 含义 |
| ---: | --- |
| 0 | 成功 |
| 1 | 用户输入或参数错误 |
| 2 | 解析失败 |
| 3 | 校验失败 |
| 4 | 兼容转换被阻止 |
| 5 | 文件权限或 I/O 失败 |
| 6 | 上游下载失败 |
| 7 | 并发修改冲突 |
| 8 | 用户取消 |
| 10+ | 未预期内部错误 |

## 17. 状态与权限

### 17.1 用户模式

普通用户默认目录：

```text
~/.config/proxy-rule-manager/
~/.cache/proxy-rule-manager/
~/.local/state/proxy-rule-manager/
```

### 17.2 root 模式

系统级目录建议：

```text
/etc/proxy-rule-manager/
/var/cache/proxy-rule-manager/
/var/lib/proxy-rule-manager/
```

### 17.3 sudo 边界

- 解析、编译和报告不需要 sudo。
- 只有读取受限配置、创建备份、写入目标等必要步骤使用 sudo。
- 不以 root 身份在普通用户工作目录创建全部产物，避免所有权混乱。
- Bash 入口应记录原始调用用户，并在需要时恢复产物所有权。

## 18. 日志与隐私

- 默认日志不输出代理节点服务器、用户名、密码、Token 或完整订阅 URL。
- diff 展示前对已知敏感字段做遮盖，可提供“本机完整查看”选项。
- 报告默认只记录规则和策略名称，不复制完整私人配置。
- GitHub 发布目录采用白名单生成，只包含规则、片段、manifest 和公开说明。
- 检测到 `proxies`、认证字段、私钥或 Token 时，发布检查必须阻止提交并提示。

## 19. 测试策略

### 19.1 单元测试

- 域名、通配域名、URL、IDNA 解析。
- 显式规则行解析。
- 去重键与策略冲突。
- 稳定排序。
- 逻辑 AST 解析与等价转换判断。
- 策略组循环检测。
- capability profile 选择。
- manifest 摘要。

### 19.2 Golden tests

对固定输入保存期望输出：

- Clash classical payload。
- Clash domain payload。
- Loon Rule-Set。
- dae 路由片段。
- 通用域名列表。
- 配置补丁前后 YAML。

### 19.3 集成测试

- 在临时目录执行完整导入、编译、预览、应用、恢复。
- 模拟无写权限文件。
- 模拟写入前文件被外部修改。
- 模拟上游超时、内容过大、格式变化与缓存回退。
- 模拟 YAML 锚点、注释、复杂策略组和已有 MATCH。

### 19.4 Debian 测试矩阵

建议使用容器或虚拟机：

| 系统 | Python 基线 | 必测内容 |
| --- | --- | --- |
| Debian 11 | 3.9 | 安装、解析、补丁、恢复 |
| Debian 12 | 3.11 | 全部测试 |
| Debian 13 | 系统版本 | 全部测试及依赖兼容 |

### 19.5 故障注入

- 备份后磁盘空间不足。
- 临时文件写入中断。
- 校验器超时。
- 原配置在确认后发生变化。
- 目标文件是符号链接。
- 上游返回 HTML 而非规则文件。

所有故障场景都必须证明原配置未损坏。

## 20. 开发小步进与验收标准

以下顺序是项目的默认推进方式。每一步都需要：实现、自动测试、示例运行结果、已知限制说明，然后才进入下一步。

### 步进 0：文档与样例冻结

交付：

- `README.md`
- `DEVELOPMENT.md`
- 最小输入样例
- 各客户端匿名化配置样例

验收：

- 已确认第一版范围与不做事项。
- 每类目标客户端至少有一份合法匿名样例。
- 策略组和逻辑规则至少各有一个边界样例。

### 步进 1：项目骨架与只读检查

交付：

- Bash 入口。
- Python 包与 CLI。
- `inspect-config` 子命令。
- Debian/Python/权限检测。

验收：

- 不修改任何文件。
- 能读取并列出 Clash/Mihomo 的策略组、节点名、规则数量、provider 名称。
- 敏感字段不会出现在默认输出。
- Debian 11–13 基础测试通过。

### 步进 2：普通输入解析

交付：

- 域名、通配域名、完整 URL、DOMAIN、DOMAIN-SUFFIX、DOMAIN-KEYWORD 解析。
- IDNA 规范化。
- 错误行报告。

验收：

- 同一输入重复执行结果一致。
- 错误输入精确定位到行号。
- 不把 IP、路径或空字符串误写成域名规则。
- 单元测试覆盖核心解析分支。

### 步进 3：通用规则项目

交付：

- `sources/` 数据格式。
- 规则新增、列出、删除、启用/禁用。
- 去重和策略冲突报告。

验收：

- 写入使用临时文件与原子替换。
- 来源信息可追踪。
- 完全重复自动跳过，策略冲突不会被自动覆盖。

### 步进 4：Clash/Mihomo 编译器

交付：

- classical payload。
- domain payload。
- rules 与 rule-providers 片段。
- 通用域名列表。

验收：

- Golden tests 稳定。
- 输出 YAML 可重新解析。
- 不可放入 domain payload 的规则会被正确拒绝或分流。

### 步进 5：策略组分析与创建规格

交付：

- 读取现有组和节点。
- `select`、`fallback`、`url-test`、`load-balance` 的创建规格。
- 循环和缺失成员检查。

验收：

- 可以创建含现有故障转移组与 DIRECT 的新组。
- 重名、空组、循环引用被阻止。
- 类型必填参数被验证。

### 步进 6：Clash/Mihomo 安全补丁

交付：

- dry-run。
- diff。
- 备份。
- 原子写入。
- 恢复。
- 内部语义校验。

验收：

- 默认不写入。
- 配置在确认后被外部修改时中止。
- 任意校验失败不覆盖原文件。
- 恢复前仍会备份当前版本。
- 不自动重载服务。

### 步进 7：上游规则与缓存

交付：

- Loyalsoldier 适配器。
- HTTPS 下载限制。
- 缓存、摘要和来源清单。
- Rule-Set 展开阈值。

验收：

- 能识别预设规则集并生成内部规则。
- HTML 错误页、超大响应和格式变化不会被当作合法规则。
- 离线缓存会明确显示时间，不冒充最新版本。

### 步进 8：GeoSite 与逻辑规则

交付：

- GeoSite 引用模型。
- 逻辑 AST。
- 等价转换判定器。
- 无法转换报告。

验收：

- 只自动执行可证明等价的转换。
- 扩展数量超过阈值时停止。
- 不支持叶子类型可完整保留并报告。

### 步进 9：Loon 编译器

交付：

- Loon Rule-Set。
- `[Rule]` 片段。
- 策略引用与兼容报告。

验收：

- Golden tests 覆盖域名、关键词和展开规则集。
- 不兼容逻辑不会被静默降级。
- 第一版默认不覆盖完整 Loon 配置。

### 步进 10：dae/daed 编译器

交付：

- 路由片段。
- 出站映射清单。
- 兼容性报告。

验收：

- 输出与 Clash 编译器完全解耦。
- 对每种内部规则给出 native/converted/blocked 状态。
- 第一版默认不覆盖完整 dae 配置。

### 步进 11：发布目录与隐私检查

交付：

- `publish-dir`。
- `manifest.yaml`。
- 自动生成的规则使用说明。
- 敏感字段扫描。

验收：

- 仅白名单文件进入输出目录。
- 检测到节点凭据、Token、私钥或完整订阅时阻止生成。
- 用户可直接查看并手动提交 GitHub。

### 步进 12：安装、升级与完整回归

交付：

- 安装脚本或 Debian 友好安装说明。
- 版本迁移机制。
- 完整测试报告。
- v0.1.0 发布候选。

验收：

- Debian 11–13 全矩阵通过。
- 旧状态文件可安全迁移或明确拒绝。
- 安装和卸载不会删除用户规则项目及备份，除非用户明确选择。

## 21. 版本与数据迁移

- 通用规则源、manifest 和配置均包含 `schema_version`。
- 读取较新 schema 时拒绝写入，并提示升级程序。
- 数据迁移先备份，再生成新文件，不原地破坏旧 schema。
- 编译产物可重新生成，不作为唯一数据源。

## 22. 代码质量要求

- Python 类型标注覆盖公开接口。
- 核心模块不直接调用 `input()`，便于测试。
- 文件、网络和子进程通过适配器注入。
- 所有异常转换为稳定错误码和面向用户的中文信息。
- debug 日志可包含技术堆栈，但仍需遮盖敏感字段。
- 格式化和静态检查建议使用 Ruff；类型检查可使用 mypy 或 pyright。

## 23. 发布前检查清单

- [ ] README 与实际行为一致。
- [ ] DEVELOPMENT 中列出的第一版范围无暗中扩张。
- [ ] Debian 11、12、13 测试通过。
- [ ] 所有写入路径均有备份、校验和并发保护。
- [ ] 默认 dry-run。
- [ ] 不自动重载服务。
- [ ] 不保存或发布敏感字段。
- [ ] 上游来源、摘要与许可证信息可追踪。
- [ ] Loon 与 dae 输出已经独立验证。
- [ ] 恢复流程已进行故障注入测试。
- [ ] 发布目录能被人工检查并手动推送 GitHub。

## 24. 下一步

步进 0 与步进 1 已完成。下一开发动作只执行“步进 2”：普通输入解析、IDNA 规范化和逐行错误报告，不提前实现规则项目写入。

### 24.1 步进 0 实施记录（2026-08-21）

- [x] 普通域名、网址、显式规则、IDNA 与重复输入样例。
- [x] 非法 URL、中间通配符、IP、路径和缺失字段样例。
- [x] AND、OR、NOT 与未知逻辑叶子保留样例。
- [x] Clash/Mihomo 匿名配置；同时作为 ShellCrash、FlClash 的配置载体样例。
- [x] Loon 匿名配置样例。
- [x] dae/daed 匿名配置样例。
- [x] 策略组循环引用阻止样例。
- [x] 样例基础自动校验与敏感字段扫描。
- [ ] 使用实际 Mihomo、Loon、dae 内核或客户端进行外部语法校验。
- [x] 用户确认样例边界并继续推进。

外部内核校验不在本步伪造：本轮自动测试只验证静态结构、引用关系、边界覆盖与样例安全性。进入对应编译器步进时，再把官方内核校验命令加入回归测试。

### 24.2 步进 1 实施记录（2026-08-21）

- [x] 建立 `pyproject.toml` 与 `src/rule_manager/` Python 包骨架。
- [x] 建立 `bin/proxy-rule-manager` Bash 中文入口。
- [x] 实现 `environment` 子命令，检测 Debian、Python、root 与 sudo。
- [x] 实现只读 `inspect-config` 子命令。
- [x] 支持中文文本和 JSON 两种输出。
- [x] 列出节点名、策略组元数据、Rule Provider 名称与规则数量。
- [x] 默认输出不包含节点服务器、端口、远程 URL 或认证字段。
- [x] YAML 解析错误包含行列位置。
- [x] 文件访问、解析、结构校验使用稳定退出码 5、2、3。
- [x] Bash 语法检查通过。
- [x] Python 3.9 语法静态检查通过。
- [x] 全部 16 项自动测试通过。

当前运行环境为 Ubuntu 24.04 / Python 3.12，因此本轮只能完成 Debian 11–13 的版本逻辑测试和 Python 3.9 语法检查；真实 Debian 容器矩阵将在持续集成或完整回归步进中执行。
