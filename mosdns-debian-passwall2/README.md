# mosdns Debian + PassWall2 DNS 分流安装器

用于 Debian 11–13 的交互式 mosdns v5 安装与管理脚本。适合 RouterOS 主路由、OpenWrt PassWall2 旁路由、Debian 独立 DNS 服务器的家庭网络。

## 功能

- 自动安装或更新官方 mosdns，并校验发布包 SHA-256。
- 国内、境外 DNS 多上游均可编辑。
- 国内默认使用阿里、腾讯、百度，可切换 UDP 或 DoH 优先。
- 境外默认使用 Google、Cloudflare DoH。
- 境外 DoH 可选择直连或严格通过 PassWall2 SOCKS5。
- 严格 SOCKS5 模式不会在代理故障时偷偷回退直连。
- 支持自定义直连和代理域名，代理规则优先。
- 缓存、定时更新规则、配置备份恢复、状态诊断和 Fake-IP 检测。
- 安装依赖、下载核心与规则时可选使用 HTTP 代理。
- 一键综合测试服务、监听、配置、SOCKS/HTTP 协议、DoH、UDP/TCP DNS、缓存、FakeDNS、AAAA 和关键日志。
- 自动修复 `/var/lib/mosdns/cache.dump` 所有权，避免配置校验后正式服务无法保存缓存。

## 推荐拓扑

```text
局域网客户端
    |
    | DNS -> Debian_IP:53
    v
Debian mosdns
    |-- 国内域名 --> 阿里 / 腾讯 / 百度（直连）
    |
    `-- 境外域名 --> Google / Cloudflare DoH
                            |
                            v
                  OpenWrt PassWall2 SOCKS5
                            |
                            v
                       境外节点
```

mosdns 只负责 DNS。网站实际流量仍由 OpenWrt 上的 PassWall2 透明代理和分流规则决定。

## 一、在 PassWall2 创建专用 SOCKS5

进入 OpenWrt：

1. 打开 `服务 -> PassWall2 -> 基本设置`。
2. 启用 `Socks 主开关`。
3. 在 `Socks 配置` 中添加一个实例。
4. 启用该实例，节点固定选择需要的境外节点，例如新加坡。
5. SOCKS 监听端口可设置为 `1082`，HTTP 下载代理可设置为 `1091`。
6. 取消 `Bind Local / 仅绑定本机`，否则 Debian 无法连接。
7. 保存并应用。

在 OpenWrt 检查监听：

```sh
netstat -lntp 2>/dev/null | grep -E ':(1082|1091) '
```

两个端口应各自只有一个监听者。若同一个端口出现两个 Xray PID，请检查并禁用独立的 `xray_core`，只保留 PassWall2 管理的实例。

建议只允许 Debian DNS 服务器访问该端口。先把占位符替换成实际地址：

```sh
uci -q delete firewall.mosdns_socks
uci set firewall.mosdns_socks='rule'
uci set firewall.mosdns_socks.name='Allow-mosdns-SOCKS5'
uci set firewall.mosdns_socks.src='lan'
uci set firewall.mosdns_socks.src_ip='DEBIAN_MOSDNS_IP'
uci set firewall.mosdns_socks.proto='tcp'
uci set firewall.mosdns_socks.dest_port='1082'
uci set firewall.mosdns_socks.target='ACCEPT'
uci commit firewall
/etc/init.d/firewall restart
```

如果 OpenWrt LAN 默认允许设备互访，上述规则可能不是必需的，但保留来源限制更安全。

## 二、在 Debian 测试 SOCKS5

把 `OPENWRT_IP` 替换成 OpenWrt 当前局域网地址：

```sh
curl -4 --socks5-hostname OPENWRT_IP:1082 https://api.ipify.org
echo
```

返回值应当是选定代理节点的公网 IPv4。若仍然是本地宽带出口，应检查 SOCKS 实例选中的节点，而不是继续配置 mosdns。

## 三、安装 mosdns

```sh
chmod +x mosdns-debian-installer.sh
sudo ./mosdns-debian-installer.sh
```

首次运行选择：

```text
1) 完整安装并配置（首次使用）
```

生成配置时选择：

```text
境外 DNS 出口模式：
  1) mosdns 直接访问境外 DoH
  2) 严格通过 PassWall2 SOCKS5（代理失败时不直连）
```

选择 `2`，然后输入：

```text
OPENWRT_IP:1082
```

不要填写 `socks5://`。mosdns v5 的 SOCKS5 上游目前不支持用户名密码认证。

安装器会尝试检测 SOCKS5 出口。自 v1.5.1 起，检测失败只显示提醒，不会阻止生成配置或强制返回菜单；可先完成安装，再修复 PassWall2 SOCKS5。该变化不引入直连回退。

## 四、严格模式行为

严格模式下，所有境外上游都会获得同一个 SOCKS5 配置。境外上游只允许：

- TCP DNS
- DNS over TLS
- DNS over HTTPS

UDP、DoQ、QUIC 和 HTTP/3 会被安装器拒绝，因为 mosdns 的 SOCKS5 拨号只适用于 TCP 类协议。

当 PassWall2 或节点故障时：

- 已缓存域名可以继续解析。
- 未缓存的境外域名会解析失败。
- 不会切换到直连 Google/Cloudflare，因此不会因为故障产生境外 DNS 直连回退。

## 五、后续修改

重新运行脚本，进入：

```text
7) 管理国内/境外 DNS 多上游
8) 修改境外 DNS 出口模式并重新生成配置
```

也可在主菜单使用：

```text
3) 生成/修改 DNS 分流配置
5) 一键综合测试与故障诊断
12) 部署架构与问题处理指南
```

主要文件：

```text
/etc/mosdns/config.yaml
/etc/mosdns/installer.conf
/etc/mosdns/upstreams/domestic.txt
/etc/mosdns/upstreams/overseas.txt
/etc/mosdns/rules/custom-direct.txt
/etc/mosdns/rules/custom-proxy.txt
```

## 六、客户端与 DHCP

实际 DHCP 服务器应只向客户端下发 Debian DNS：

```text
DEBIAN_MOSDNS_IP
```

同时检查并关闭可能绕过 mosdns 的客户端功能：

- 浏览器内置安全 DNS。
- Android 私人 DNS。
- iCloud Private Relay。
- 客户端手动设置的 IPv6 DNS。

严格 SOCKS5 方案返回真实 IP，不需要 Fake-IP，也不需要为 `198.18.0.0/15` 添加静态路由。

## 七、验证

在客户端测试：

```sh
nslookup baidu.com DEBIAN_MOSDNS_IP
nslookup cloudflare.com DEBIAN_MOSDNS_IP
```

在 Debian 检查：

```sh
systemctl status mosdns --no-pager
ss -lntup | grep ':53 '
journalctl -u mosdns -n 80 --no-pager
```

运行安装器菜单中的一键综合测试，会统一执行：

- mosdns 核心、systemd 服务、配置临时启动校验。
- UDP/TCP DNS 与 API 监听检查。
- 严格 SOCKS5 配置检查及连续三次出口握手。
- Cloudflare DoH 经 SOCKS5 查询。
- HTTP 下载代理协议测试。
- 国内/境外 A 查询和 TCP DNS 查询。
- FakeDNS 检测。
- 缓存权限自动修复及重启持久化测试。
- AAAA/IPv6 流量绕过提醒。
- 客户端默认 DNS 和关键日志检查。
- 输出浏览器安全 DNS、DHCPv6/RA、53/853 绕过与抓包复核提示。

也可以直接运行：

```sh
mosdns-debian-installer --test
mosdns-debian-installer --guide
```

## 八、PassWall2 DNS 建议

客户端 DNS 由 mosdns 负责时，PassWall2 建议设置：

- 直连 DNS：`223.5.5.5`，查询策略 `UseIPv4`。
- 远程 DNS：`1.1.1.1`，协议 TCP，出站使用远程/代理/默认节点。
- 不要把 PassWall2 远程 DNS 设置为 Debian mosdns 地址，避免循环依赖。
- DNS 重定向关闭，FakeDNS 关闭。
- DHCP 直接向客户端下发 Debian mosdns 地址。

若 mosdns 返回 AAAA，而 PassWall2 没有代理 IPv6，客户端可能通过 IPv6 直连网站；这属于实际流量绕过，不是 DNS 查询泄漏。

### FakeDNS 能否解决泄漏

不能把 FakeDNS 当作一个单独的“防泄漏开关”。FakeDNS 给客户端返回 `198.18.0.0/15` 虚拟地址，必须由 Xray/PassWall2 的透明代理接管这些地址并恢复域名。当前项目采用的是 mosdns 返回真实 IP、境外 DoH 严格通过 SOCKS5 的方案，因此应保持 FakeDNS 关闭；否则会把两种架构混在一起，PassWall2 停止时还可能出现缓存中的虚拟地址无法访问。

DNS 检测页显示的 Google/Cloudflare 递归服务器 IP 或机房与代理节点不同，不必然代表泄漏。应核对的是：

- 客户端 DNS 是否只发送到 Debian mosdns，或 OpenWrt dnsmasq 是否只转发到 Debian mosdns。
- mosdns 境外 DoH 是否严格绑定 PassWall2 SOCKS5，且没有直连回退。
- 浏览器安全 DNS、Android 私人 DNS、iCloud Private Relay 是否绕过系统 DNS。
- DHCPv6/RA 是否另外下发了 IPv6 DNS。
- 网关是否同时限制 IPv4/IPv6 客户端绕过 TCP/UDP 53 和 TCP 853；DoH 的 TCP 443 需要终端策略或单独规则处理。

实际复核时，在 Debian 执行：

```sh
tcpdump -ni any 'port 53'
```

同时在 OpenWrt 执行：

```sh
tcpdump -ni any '(udp port 53 or tcp port 53 or tcp port 853)'
```

只让一台客户端重新打开 DNS 检测页。若 OpenWrt WAN 侧出现访问其他公网 53/853 的查询，则确有旁路；若只看到客户端到 mosdns，且 mosdns 的境外 DoH 已通过 SOCKS5，则公共解析器机房不同通常只是递归 DNS 的基础设施位置差异。

## 九、测试状态

v1.6.1 已完成以下测试：

- POSIX Shell 语法及 ShellCheck。
- 官方 mosdns v5.3.4 配置启动。
- 国内/境外规则分流。
- 多上游故障切换。
- UDP/TCP 下游查询。
- 缓存与强制代理规则优先级。
- mosdns 通过真实 SOCKS5 协议连接境外测试上游。
- SOCKS5 中断后缓存继续工作。
- 严格模式下未缓存境外域名不发生直连回退。
- SOCKS5 安装前检测失败时仍保存严格模式配置并继续安装。
- 配置校验不再以 root 污染正式缓存文件。
- 缓存目录所有权自动修复及重启写入验证。
- 连续 SOCKS5 握手可识别重复 Xray 导致的间歇 reset。
- HTTP 代理与 SOCKS5 协议分别校验，避免端口类型混用。
- 关键日志精确匹配，不把正常关闭 UDP socket 误报为故障。
- 仓库示例不包含用户局域网地址、主机名、用户名或认证信息。
- 备份目录仅 root 可访问，HTTP 代理认证文件不再复制到备份。
