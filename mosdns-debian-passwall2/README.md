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
                       新加坡节点
```

mosdns 只负责 DNS。网站实际流量仍由 RouterOS 路由策略和 PassWall2 透明代理决定。

## 一、在 PassWall2 创建专用 SOCKS5

进入 OpenWrt：

1. 打开 `服务 -> PassWall2 -> 基本设置`。
2. 启用 `Socks 主开关`。
3. 在 `Socks 配置` 中添加一个实例。
4. 启用该实例，节点固定选择需要的境外节点，例如新加坡。
5. 监听端口可设置为 `1081`。
6. 取消 `Bind Local / 仅绑定本机`，否则 Debian 无法连接。
7. 保存并应用。

在 OpenWrt 检查监听：

```sh
ss -lntp | grep ':1081 '
```

应监听 OpenWrt 的局域网地址或 `0.0.0.0:1081`，不能只有 `127.0.0.1:1081`。

建议只允许 Debian DNS 服务器访问该端口。下面示例中的 Debian 地址是 `192.168.105.174`：

```sh
uci -q delete firewall.mosdns_socks
uci set firewall.mosdns_socks='rule'
uci set firewall.mosdns_socks.name='Allow-mosdns-SOCKS5'
uci set firewall.mosdns_socks.src='lan'
uci set firewall.mosdns_socks.src_ip='192.168.105.174'
uci set firewall.mosdns_socks.proto='tcp'
uci set firewall.mosdns_socks.dest_port='1081'
uci set firewall.mosdns_socks.target='ACCEPT'
uci commit firewall
/etc/init.d/firewall restart
```

如果 OpenWrt LAN 默认允许设备互访，上述规则可能不是必需的，但保留来源限制更安全。

## 二、在 Debian 测试 SOCKS5

把 `OPENWRT_IP` 替换成 OpenWrt 当前局域网地址：

```sh
curl -4 --socks5-hostname OPENWRT_IP:1081 https://api.ipify.org
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
OPENWRT_IP:1081
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
5) 状态检查与故障诊断
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

## 六、客户端与 RouterOS

RouterOS DHCP 应只向客户端下发 Debian DNS，例如：

```text
192.168.105.174
```

同时检查并关闭可能绕过 mosdns 的客户端功能：

- 浏览器内置安全 DNS。
- Android 私人 DNS。
- iCloud Private Relay。
- 客户端手动设置的 IPv6 DNS。

严格 SOCKS5 方案返回真实 IP，不需要 Fake-IP，也不需要在 RouterOS 添加 `198.18.0.0/15` 静态路由。

## 七、验证

在客户端测试：

```sh
nslookup baidu.com 192.168.105.174
nslookup cloudflare.com 192.168.105.174
```

在 Debian 检查：

```sh
systemctl status mosdns --no-pager
ss -lntup | grep ':53 '
journalctl -u mosdns -n 80 --no-pager
```

运行安装器菜单中的状态诊断，会同时测试 mosdns 查询和 PassWall2 SOCKS5 出口。

## 八、测试状态

v1.5.1 已完成以下测试：

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
