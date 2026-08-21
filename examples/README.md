# 步进 0：匿名样例说明

本目录冻结第一版解析器与编译器使用的输入边界。样例只使用保留域名、文档地址和本机回环地址，不包含真实节点、订阅、密码或 Token。

## 文件

- `inputs/manual-rules.txt`：应被接受并规范化的普通输入。
- `inputs/invalid-rules.txt`：应被精确拒绝并报告行号的输入。
- `inputs/logic-rules.txt`：逻辑规则与未知叶子保留样例。
- `clash/mihomo.yaml`：Clash/Mihomo 匿名配置；也用于 ShellCrash、FlClash 的只读检查测试。
- `clash/policy-cycle.yaml`：策略组循环引用的阻止样例。
- `loon/loon.conf`：Loon 匿名完整配置骨架。
- `dae/route.dae`：dae/daed 匿名配置，节点仅指向本机 SOCKS 测试端口。

## 安全约束

- 样例中的 `.example`、`.invalid` 域名不会指向真实服务。
- `127.0.0.1:1080` 仅用于结构测试，不代表可用代理。
- 边界样例不得被安装脚本复制为用户的生产配置。
- 后续测试可以读取这些文件，但不得原地修改。

## 本步验收

运行：

```bash
python3 -m unittest -v tests.test_samples
```

通过表示样例文件存在、YAML 可解析、敏感字段未泄露、策略循环样例仍可被测试稳定识别。客户端内核级配置测试将在相应编译器步进加入。
