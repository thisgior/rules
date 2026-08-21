# Debian 通用代理规则管理器

一个面向 Debian 11、12、13 的交互式规则管理项目，用于将批量域名、网址、GeoSite、Rule-Set 和逻辑规则整理为统一规则源，再生成适配 Clash/Mihomo、ShellCrash、FlClash、Loon 与 dae/daed 的规则文件或配置片段。

项目采用 **Bash 中文菜单 + Python 规则引擎**：Bash 负责环境检测和交互流程，Python 负责解析、规范化、转换、排序、冲突检测、配置补丁、备份及校验。

> 当前状态：步进 1 已完成，提供可运行的只读开发版；目前不会修改配置，也不会重载任何服务。

## 当前可用功能

- 检测 Debian 版本、Python 版本、root 身份和 sudo 可用性。
- 只读解析 Clash/Mihomo YAML。
- 列出节点名、策略组名与类型、成员数量、Rule Provider 名称和规则数量。
- 默认输出不包含节点服务器、端口、Provider URL、认证字段或完整配置。
- 支持中文文本与 JSON 输出。
- 提供 Bash 中文菜单和可独立测试的 Python CLI。

### 直接运行

Debian 11–13 安装基础依赖：

```bash
apt-get update
apt-get install -y python3 python3-yaml
```

检查运行环境：

```bash
./bin/proxy-rule-manager environment
```

只读检查配置：

```bash
./bin/proxy-rule-manager inspect-config /path/to/config.yaml
```

输出 JSON：

```bash
./bin/proxy-rule-manager inspect-config /path/to/config.yaml --format json
```

不带参数运行 Bash 入口会显示中文菜单：

```bash
./bin/proxy-rule-manager
```

## 1. 为什么需要这个项目

不同代理客户端的规则语法与能力并不一致：

- Clash/Mihomo 可以使用 `rule-providers`、`RULE-SET`、`GEOSITE` 等能力。
- ShellCrash 与 FlClash 通常消费 Clash/Mihomo YAML，但具体能力取决于实际内核版本。
- Loon 使用独立的规则及策略组格式。
- dae/daed 使用自己的路由语法，不能直接套用 Clash YAML。
- 部分客户端不支持远程规则集，只能使用展开后的普通域名规则。

本项目不会强行用一份客户端配置覆盖所有平台，而是采用：

```text
一份通用规则源
├── Clash/Mihomo 规则集与配置补丁
├── Loon Rule-Set 与配置片段
├── dae/daed 路由片段
└── 通用域名列表
```

## 2. 主要目标

- 支持 Debian 11–13。
- 支持 root 用户与具备 sudo 权限的普通用户。
- 读取本地固定配置文件。
- 支持一次粘贴多行规则并批量处理。
- 自动识别输入、规范化、去重和排序。
- 根据目标客户端能力自动选择原生规则或兼容转换。
- 可以使用现有策略组，也可以交互式创建新策略组。
- 新策略组可包含 `DIRECT`、`REJECT`、现有故障转移组、其他策略组或单个节点。
- 修改配置前自动备份，修改后进行语法与引用校验。
- 不自动重载或重启代理服务。
- 生成适合手动提交到 GitHub 的发布目录。

## 3. 支持的输入

### 3.1 域名与网址

```text
example.com
*.example.com
.example.com
https://example.com/path?q=1
DOMAIN,api.example.com
DOMAIN-SUFFIX,example.com
DOMAIN-KEYWORD,example
```

处理规则：

- 完整网址自动提取主机名。
- `*.example.com` 与 `.example.com` 规范化为域名后缀规则。
- Unicode 域名转换为 Punycode，同时在报告中保留原始输入。
- 自动清理首尾空白、重复协议、路径、注释和重复项。
- IP 地址不会被误判为普通域名；第一版不主动提供 IP/CIDR 编辑菜单。

### 3.2 高级规则

```text
GEOSITE,category-ads-all
RULE-SET,private
AND,((DOMAIN-SUFFIX,example.com),(NETWORK,TCP))
OR,((DOMAIN,a.example.com),(DOMAIN,b.example.com))
NOT,((DOMAIN-SUFFIX,example.com))
```

逻辑组合只在能够保持原始语义时转换。不能等价转换的规则不会被静默改写，而是进入兼容性报告。

## 4. 上游规则源

默认上游使用 [Loyalsoldier/clash-rules](https://github.com/Loyalsoldier/clash-rules)。

第一版计划支持：

- 从预设清单选择常用规则集。
- 填写远程规则链接。
- 导入本地规则文件。
- 优先使用 GitHub Raw 地址。
- 可配置备用 CDN 地址。
- 缓存下载内容并记录来源、更新时间与校验摘要。

上游文件只作为数据源。项目会按目标客户端重新编译，不能保证所有上游格式都能被每个客户端直接引用。

## 5. 策略与策略组

添加一批规则时，可以选择：

1. 指向现有策略组。
2. 指向 `DIRECT`。
3. 指向 `REJECT`。
4. 创建一个新的策略组。

创建策略组时，每次询问类型：

- `select`
- `fallback`
- `url-test`
- `load-balance`

可从现有配置中选择成员：

- `DIRECT`
- `REJECT`
- 已存在的故障转移组
- 已存在的其他代理组
- 单个代理节点

Clash/Mihomo 示例：

```yaml
proxy-groups:
  - name: 金融服务
    type: select
    proxies:
      - 故障转移
      - DIRECT
```

创建前会检查重名、空成员、循环引用、不可用节点和目标客户端是否支持该组类型。

## 6. 自动排序原则

默认按“越具体越靠前，兜底规则越靠后”排序：

1. 精确域名 `DOMAIN`
2. 域名后缀 `DOMAIN-SUFFIX`
3. 域名关键词 `DOMAIN-KEYWORD`
4. 逻辑组合规则
5. 自定义 `RULE-SET`
6. `GEOSITE`
7. 大范围公共 `RULE-SET`
8. `GEOIP`
9. `MATCH` / `FINAL`

排序不是简单地对整份配置重新洗牌。默认只整理本次管理的规则区块，尽量保留用户原有规则的相对顺序和注释。

## 7. 兼容转换

转换遵循三个层级：

| 情况 | 处理方式 |
| --- | --- |
| 目标客户端原生支持 | 生成原生规则 |
| 存在语义等价的兼容写法 | 自动转换并记录报告 |
| 无法保持原始语义 | 停止该项转换，要求用户处理 |

典型处理：

- 不支持 `RULE-SET`：在允许且来源可解析时展开为普通规则。
- 不支持 `GEOSITE`：读取指定 GeoSite 数据源后展开。
- 不支持逻辑组合：只有在可以严格等价展开时才转换。
- 不识别客户端能力：按保守模式输出普通规则，并提示人工检查。
- 展开规模超过阈值：停止展开并提示改用远程规则集或拆分文件。

## 8. 交互菜单草案

```text
1. 添加一批域名或网址
2. 添加 GeoSite / Rule-Set
3. 创建或修改策略组
4. 导入 Loyalsoldier 规则
5. 编译通用规则
6. 修改 Clash/Mihomo 配置
7. 生成 Loon 配置片段
8. 生成 dae/daed 路由片段
9. 检查重复、冲突和兼容性
10. 预览修改差异
11. 恢复历史备份
12. 生成 GitHub 发布目录
0. 退出
```

所有会写入文件的操作都必须先显示摘要；配置补丁操作还需要显示 diff 并二次确认。

## 9. 安全机制

- 修改前创建带时间戳的完整备份。
- 备份文件与原文件权限保持一致。
- 使用同目录临时文件和原子替换，避免写入中断损坏配置。
- 写入前后验证 YAML 或目标格式语法。
- 检查规则引用的策略组是否存在。
- 检查 `rule-providers` 引用是否存在。
- 检查策略组循环引用。
- 检查 `MATCH` / `FINAL` 是否提前截断后续规则。
- 若发现可用的 Mihomo/Clash 内核，可选择执行配置测试。
- 校验失败时保留原配置和失败报告，不覆盖生效文件。
- 不自动重载 ShellCrash、Clash、Mihomo、dae 或其他服务。
- 不保存 GitHub Token，也不代替用户推送仓库。

## 10. 计划中的项目结构

```text
proxy-rule-manager/
├── bin/
│   └── proxy-rule-manager
├── src/
│   └── rule_manager/
├── config/
│   ├── defaults.yaml
│   └── upstreams.yaml
├── rules-project/
│   ├── sources/
│   ├── dist/
│   │   ├── clash/
│   │   ├── loon/
│   │   ├── dae/
│   │   └── domain-list/
│   ├── snippets/
│   ├── reports/
│   └── manifest.yaml
├── tests/
├── README.md
└── DEVELOPMENT.md
```

## 11. GitHub 发布目录

脚本只生成 Git-ready 内容，不进行认证或推送：

```text
rules-project/
├── sources/          # 通用规则源
├── dist/             # 各客户端编译结果
├── snippets/         # 配置引用示例
├── reports/          # 兼容性和校验报告
├── manifest.yaml     # 版本、来源和校验摘要
└── README.md         # 规则文件使用说明
```

建议在提交 GitHub 前人工检查 `reports/`，并避免提交含节点地址、密码、Token 或完整私人配置的文件。

## 12. 第一版明确不做

- 不自动重启或重载任何代理服务。
- 不自动提交或推送 GitHub。
- 不将完整节点、认证信息或订阅地址发布到规则仓库。
- 不保证任意逻辑规则都能跨客户端等价转换。
- 不在第一版提供图形界面。
- 不在第一版提供在线订阅管理。
- 不直接修改 Loon 或 dae 的完整配置；优先生成可审阅的片段。

## 13. 开发步进

项目按小步、可测试、可回退的方式推进：

1. 固化规则模型与示例数据。
2. 完成域名/网址解析、规范化和去重。
3. 完成通用规则源的保存与读取。
4. 完成 Clash/Mihomo 编译器。
5. 完成配置读取、策略组选择和安全补丁。
6. 完成备份、diff、校验与恢复。
7. 接入 Loyalsoldier 上游下载与缓存。
8. 完成 Loon 输出。
9. 完成 dae/daed 输出。
10. 完成 GitHub 发布目录和完整测试。

每一步都应先提供可运行结果和测试报告，再进入下一步。详见 [DEVELOPMENT.md](DEVELOPMENT.md)。

当前样例位于 [`examples/`](examples/)，可运行以下命令执行全部自动测试：

```bash
PYTHONPATH=src python3 -m unittest discover -v
```

## 14. 许可证与第三方数据

项目代码的许可证将在正式建仓时确定。第三方规则源继续受其各自许可证和使用条款约束；发布编译结果前需要保留来源说明，并确认再分发要求。
