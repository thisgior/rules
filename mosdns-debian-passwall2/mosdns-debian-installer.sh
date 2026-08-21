#!/bin/sh
# mosdns Debian interactive installer
# Architecture: LAN clients -> Debian mosdns -> domestic DNS / overseas DoH (direct or SOCKS5)
# Compatible with Debian 11, 12 and 13. Run as root.

SCRIPT_VERSION="1.5.0"
MOSDNS_DIR="/etc/mosdns"
RULE_DIR="$MOSDNS_DIR/rules"
UPSTREAM_DIR="$MOSDNS_DIR/upstreams"
DOMESTIC_UPSTREAMS="$UPSTREAM_DIR/domestic.txt"
OVERSEAS_UPSTREAMS="$UPSTREAM_DIR/overseas.txt"
BACKUP_DIR="$MOSDNS_DIR/backups"
STATE_DIR="/var/lib/mosdns"
CONF_FILE="$MOSDNS_DIR/config.yaml"
ENV_FILE="$MOSDNS_DIR/installer.conf"
PROXY_FILE="$MOSDNS_DIR/install-proxy.txt"
BIN_FILE="/usr/local/bin/mosdns"
SERVICE_FILE="/etc/systemd/system/mosdns.service"
UPDATER_FILE="/usr/local/sbin/mosdns-update-rules"
TIMER_FILE="/etc/systemd/system/mosdns-rules-update.timer"
UPDATE_SERVICE_FILE="/etc/systemd/system/mosdns-rules-update.service"

DEFAULT_VERSION="v5.3.4"
DEFAULT_PORT="53"
DEFAULT_CACHE_SIZE="8192"
GITHUB_API="https://api.github.com/repos/IrineSistiana/mosdns/releases/latest"
RELEASE_BASE="https://github.com/IrineSistiana/mosdns/releases/download"
DIRECT_LIST_URL="https://raw.githubusercontent.com/Loyalsoldier/v2ray-rules-dat/release/direct-list.txt"

C_RESET='\033[0m'
C_RED='\033[31m'
C_GREEN='\033[32m'
C_YELLOW='\033[33m'
C_BLUE='\033[36m'

say() { printf "%b%s%b\n" "$C_BLUE" "$*" "$C_RESET"; }
ok() { printf "%b[成功]%b %s\n" "$C_GREEN" "$C_RESET" "$*"; }
warn() { printf "%b[提醒]%b %s\n" "$C_YELLOW" "$C_RESET" "$*"; }
err() { printf "%b[错误]%b %s\n" "$C_RED" "$C_RESET" "$*" >&2; }
die() { err "$*"; exit 1; }

pause() {
    printf "\n按 Enter 返回菜单..."
    read -r _pause_value
}

ask() {
    _ask_prompt="$1"
    _ask_default="$2"
    if [ -n "$_ask_default" ]; then
        printf "%s [%s]: " "$_ask_prompt" "$_ask_default" >&2
    else
        printf "%s: " "$_ask_prompt" >&2
    fi
    read -r _ask_value
    [ -n "$_ask_value" ] || _ask_value="$_ask_default"
    printf "%s" "$_ask_value"
}

confirm() {
    _confirm_prompt="$1"
    _confirm_default="${2:-N}"
    if [ "$_confirm_default" = "Y" ]; then
        printf "%s [Y/n]: " "$_confirm_prompt"
    else
        printf "%s [y/N]: " "$_confirm_prompt"
    fi
    read -r _confirm_value
    [ -n "$_confirm_value" ] || _confirm_value="$_confirm_default"
    case "$_confirm_value" in
        y|Y|yes|YES|Yes) return 0 ;;
        *) return 1 ;;
    esac
}

mask_proxy_url() {
    printf '%s' "$1" | sed 's#//[^/@]*@#//***@#'
}

valid_http_proxy() {
    case "$1" in
        http://*|https://*) ;;
        *) return 1 ;;
    esac
    case "$1" in
        *[[:space:]]*) return 1 ;;
    esac
    return 0
}

load_install_proxy() {
    INSTALL_HTTP_PROXY="${INSTALL_HTTP_PROXY:-${https_proxy:-${http_proxy:-}}}"
    if [ -z "$INSTALL_HTTP_PROXY" ] && [ -s "$PROXY_FILE" ]; then
        IFS= read -r INSTALL_HTTP_PROXY <"$PROXY_FILE"
    fi
}

apply_install_proxy() {
    load_install_proxy
    if [ -n "$INSTALL_HTTP_PROXY" ]; then
        http_proxy="$INSTALL_HTTP_PROXY"
        https_proxy="$INSTALL_HTTP_PROXY"
        HTTP_PROXY="$INSTALL_HTTP_PROXY"
        HTTPS_PROXY="$INSTALL_HTTP_PROXY"
        export http_proxy https_proxy HTTP_PROXY HTTPS_PROXY
    fi
}

clear_install_proxy_env() {
    INSTALL_HTTP_PROXY=""
    unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY
}

test_install_proxy() {
    command -v curl >/dev/null 2>&1 || {
        warn "curl 尚未安装，将在依赖安装后使用该代理。"
        return 0
    }
    apply_install_proxy
    say "测试 HTTP 代理访问 GitHub API..."
    curl -fsS --connect-timeout 8 --max-time 15 \
        -o /dev/null "https://github.com/IrineSistiana/mosdns/releases/latest"
}

configure_install_proxy() {
    load_install_proxy
    _default="N"
    if [ -n "$INSTALL_HTTP_PROXY" ]; then
        say "当前安装下载代理：$(mask_proxy_url "$INSTALL_HTTP_PROXY")"
        _default="Y"
    fi
    if ! confirm "安装及规则下载是否使用 HTTP 代理？" "$_default"; then
        clear_install_proxy_env
        return 0
    fi

    _proxy_default="$INSTALL_HTTP_PROXY"
    _proxy_value="$(ask "HTTP 代理地址" "$_proxy_default")"
    [ -n "$_proxy_value" ] || {
        err "HTTP 代理地址不能为空。"
        return 1
    }
    valid_http_proxy "$_proxy_value" || {
        err "代理地址必须以 http:// 或 https:// 开头，并且不能包含空格。"
        return 1
    }
    INSTALL_HTTP_PROXY="$_proxy_value"
    apply_install_proxy

    if test_install_proxy; then
        ok "HTTP 代理连接测试通过。"
    else
        warn "HTTP 代理连接测试失败。"
        confirm "仍然继续使用该代理？" N || { clear_install_proxy_env; return 1; }
    fi

    if confirm "保存该代理，供以后更新核心和规则使用？" Y; then
        mkdir -p "$MOSDNS_DIR"
        printf '%s\n' "$INSTALL_HTTP_PROXY" >"$PROXY_FILE"
        chmod 0600 "$PROXY_FILE"
        ok "代理设置已保存（认证信息不会显示在菜单中）。"
    fi
}

disable_saved_proxy() {
    clear_install_proxy_env
    rm -f "$PROXY_FILE"
    ok "已关闭并删除保存的安装下载代理。"
}

valid_socks5_address() {
    _socks_addr="$1"
    case "$_socks_addr" in
        ''|*://*|*[[:space:]]*|*\'*|*\"*) return 1 ;;
    esac
    _socks_host="${_socks_addr%:*}"
    _socks_port="${_socks_addr##*:}"
    [ -n "$_socks_host" ] || return 1
    case "$_socks_port" in ''|*[!0-9]*) return 1 ;; esac
    [ "$_socks_port" -ge 1 ] && [ "$_socks_port" -le 65535 ]
}

test_overseas_socks5() {
    [ -n "${OVERSEAS_SOCKS5:-}" ] || return 1
    command -v curl >/dev/null 2>&1 || {
        warn "curl 尚未安装，暂时跳过 SOCKS5 出口测试。"
        return 0
    }
    say "测试 PassWall2 SOCKS5 及境外出口..."
    _socks_exit_ip="$(curl -4 -fsS --connect-timeout 8 --max-time 15 \
        --socks5-hostname "$OVERSEAS_SOCKS5" \
        "https://api.ipify.org" 2>/dev/null)" || return 1
    valid_ipv4 "$_socks_exit_ip" || return 1
    printf '%s\n' "SOCKS5 出口 IPv4：$_socks_exit_ip"
}

validate_socks_upstreams() {
    _file="$1"
    while IFS= read -r _upstream || [ -n "$_upstream" ]; do
        _upstream="$(printf '%s' "$_upstream" | sed 's/[[:space:]]*#.*$//; s/^[[:space:]]*//; s/[[:space:]]*$//')"
        [ -n "$_upstream" ] || continue
        _addr="${_upstream%%|*}"
        case "$_addr" in
            tcp://*|tls://*|https://*) ;;
            *)
                err "严格 SOCKS5 模式仅支持 TCP、DoT、DoH 上游：$_addr"
                err "不能使用 UDP、DoQ、QUIC 或 HTTP/3。"
                return 1
                ;;
        esac
    done <"$_file"
    return 0
}

configure_overseas_route() {
    printf '%s\n' "境外 DNS 出口模式："
    printf '%s\n' "  1) mosdns 直接访问境外 DoH"
    printf '%s\n' "  2) 严格通过 PassWall2 SOCKS5（代理失败时不直连）"
    _route_default="1"
    [ "${OVERSEAS_MODE:-direct}" = "socks5_strict" ] && _route_default="2"
    _route_choice="$(ask "请选择" "$_route_default")"
    case "$_route_choice" in
        1)
            OVERSEAS_MODE="direct"
            OVERSEAS_SOCKS5=""
            ;;
        2)
            OVERSEAS_MODE="socks5_strict"
            _socks_default="${OVERSEAS_SOCKS5:-}"
            OVERSEAS_SOCKS5="$(ask "PassWall2 SOCKS5（OpenWrt_IP:端口，不加协议）" "$_socks_default")"
            valid_socks5_address "$OVERSEAS_SOCKS5" || {
                err "SOCKS5 地址无效，示例：192.168.105.10:1081"
                return 1
            }
            validate_socks_upstreams "$OVERSEAS_UPSTREAMS" || return 1
            if test_overseas_socks5; then
                ok "PassWall2 SOCKS5 出口测试通过。"
            else
                err "无法通过 $OVERSEAS_SOCKS5 访问境外网络。"
                err "请检查 PassWall2 SOCKS 主开关、节点、监听地址和防火墙。"
                return 1
            fi
            ;;
        *) err "无效的境外 DNS 出口模式。"; return 1 ;;
    esac
    return 0
}

header() {
    clear 2>/dev/null || true
    printf "%b" "$C_BLUE"
    printf '%s\n' "===================================================="
    printf '%s\n' " mosdns Debian 本地 DNS 分流互动安装脚本"
    printf '%s\n' " 版本: $SCRIPT_VERSION"
    printf '%s\n' "===================================================="
    printf "%b" "$C_RESET"
}

require_debian() {
    [ "$(id -u)" = "0" ] || die "请使用 root 用户运行。"
    [ -f /etc/debian_version ] || die "未检测到 Debian。"
    command -v apt-get >/dev/null 2>&1 || die "未找到 apt-get。"
    command -v systemctl >/dev/null 2>&1 || die "未找到 systemd。"
    _debian_major="$(sed 's/[^0-9].*$//' /etc/debian_version)"
    case "$_debian_major" in
        11|12|13) ;;
        *) warn "当前 Debian 版本为 $(cat /etc/debian_version)，脚本主要验证范围是 Debian 11–13。" ;;
    esac
}

now_stamp() { date '+%Y%m%d-%H%M%S'; }

detect_lan_ip() {
    ip -4 -o addr show scope global 2>/dev/null \
        | awk '!/ docker| br-| veth| tun| tailscale| zerotier| zt/ {split($4,a,"/"); print a[1]; exit}'
}

detect_lan_cidr() {
    _target_ip="$1"
    ip -4 -o addr show scope global 2>/dev/null \
        | awk -v ip="$_target_ip" '{split($4,a,"/"); if (a[1] == ip) {print $4; exit}}'
}

valid_ipv4() {
    printf '%s\n' "$1" | awk -F. '
        BEGIN {valid=1}
        NF != 4 {valid=0}
        {
            for (i=1;i<=4;i++) {
                if ($i !~ /^[0-9]+$/ || $i < 0 || $i > 255) valid=0
            }
        }
        END {exit valid ? 0 : 1}
    '
}

make_backup() {
    _reason="${1:-manual}"
    _path="$BACKUP_DIR/$(now_stamp)-$_reason"
    mkdir -p "$_path" || return 1
    [ -f "$CONF_FILE" ] && cp -p "$CONF_FILE" "$_path/config.yaml"
    [ -f "$ENV_FILE" ] && cp -p "$ENV_FILE" "$_path/installer.conf"
    [ -f "$PROXY_FILE" ] && cp -p "$PROXY_FILE" "$_path/install-proxy.txt"
    [ -f "$SERVICE_FILE" ] && cp -p "$SERVICE_FILE" "$_path/mosdns.service"
    [ -f "$UPDATER_FILE" ] && cp -p "$UPDATER_FILE" "$_path/mosdns-update-rules"
    [ -f "$DOMESTIC_UPSTREAMS" ] && cp -p "$DOMESTIC_UPSTREAMS" "$_path/domestic-upstreams.txt"
    [ -f "$OVERSEAS_UPSTREAMS" ] && cp -p "$OVERSEAS_UPSTREAMS" "$_path/overseas-upstreams.txt"
    if [ -x "$BIN_FILE" ]; then
        "$BIN_FILE" version >"$_path/mosdns-version.txt" 2>&1 || true
    fi
    printf '%s\n' "reason=$_reason" >"$_path/backup.info"
    printf '%s\n' "created=$(date '+%Y-%m-%d %H:%M:%S %z')" >>"$_path/backup.info"
    printf '%s' "$_path"
}

install_dependencies() {
    say "安装依赖..."
    apply_install_proxy
    export DEBIAN_FRONTEND=noninteractive
    apt-get update || die "apt-get update 失败。"
    apt-get install -y ca-certificates curl unzip iproute2 dnsutils nano || \
        die "依赖安装失败。"
    ok "依赖安装完成。"
}

download_to() {
    _url="$1"
    _dest="$2"
    apply_install_proxy
    rm -f "$_dest"
    curl -fL --connect-timeout 15 --retry 2 -o "$_dest" "$_url"
}

fetch_text() {
    apply_install_proxy
    curl -fsL --connect-timeout 15 --retry 2 "$1"
}

detect_asset_arch() {
    case "$(uname -m)" in
        x86_64|amd64) printf '%s' "amd64" ;;
        aarch64|arm64) printf '%s' "arm64" ;;
        armv7*|armv8l) printf '%s' "arm-7" ;;
        armv6*) printf '%s' "arm-6" ;;
        armv5*) printf '%s' "arm-5" ;;
        mips64el|mips64le) printf '%s' "mips64le-hardfloat" ;;
        mipsel|mipsle) printf '%s' "mipsle-softfloat" ;;
        ppc64le) printf '%s' "ppc64le" ;;
        *) return 1 ;;
    esac
}

latest_version() {
    fetch_text "$GITHUB_API" 2>/dev/null \
        | sed -n 's/.*"tag_name":[[:space:]]*"\([^"]*\)".*/\1/p' \
        | head -n 1
}

release_digest() {
    _version="$1"
    _asset="$2"
    fetch_text "https://api.github.com/repos/IrineSistiana/mosdns/releases/tags/$_version" 2>/dev/null \
        | awk -v asset="$_asset" '
            index($0, "\"name\": \"" asset "\"") {wanted=1}
            wanted && index($0, "\"digest\": \"sha256:") {
                line=$0
                sub(/^.*sha256:/, "", line)
                sub(/\".*$/, "", line)
                print line
                exit
            }
        '
}

ensure_user() {
    if ! getent group mosdns >/dev/null 2>&1; then
        addgroup --system mosdns >/dev/null
    fi
    if ! getent passwd mosdns >/dev/null 2>&1; then
        adduser --system --ingroup mosdns --home "$STATE_DIR" --no-create-home \
            --disabled-login --disabled-password mosdns >/dev/null
    fi
    mkdir -p "$STATE_DIR"
    chown mosdns:mosdns "$STATE_DIR"
    chmod 0750 "$STATE_DIR"
}

install_service() {
    ensure_user
    cat >"$SERVICE_FILE" <<'EOF_SERVICE'
[Unit]
Description=mosdns DNS forwarder
Documentation=https://github.com/IrineSistiana/mosdns
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=mosdns
Group=mosdns
WorkingDirectory=/etc/mosdns
ExecStart=/usr/local/bin/mosdns start -d /etc/mosdns -c config.yaml
Restart=on-failure
RestartSec=3s
LimitNOFILE=65536
AmbientCapabilities=CAP_NET_BIND_SERVICE
CapabilityBoundingSet=CAP_NET_BIND_SERVICE
NoNewPrivileges=true
PrivateTmp=true
ProtectHome=true
ProtectSystem=strict
ReadWritePaths=/var/lib/mosdns

[Install]
WantedBy=multi-user.target
EOF_SERVICE
    chmod 0644 "$SERVICE_FILE"
    systemctl daemon-reload
    systemctl enable mosdns.service >/dev/null
}

install_core() {
    require_debian
    configure_install_proxy || return 1
    install_dependencies
    _arch="$(detect_asset_arch)" || die "不支持的 CPU 架构：$(uname -m)。"
    _latest="$(latest_version)"
    [ -n "$_latest" ] || _latest="$DEFAULT_VERSION"
    _version="$(ask "安装版本" "$_latest")"
    case "$_version" in v*) ;; *) _version="v$_version" ;; esac
    _asset="mosdns-linux-$_arch.zip"
    _url="$RELEASE_BASE/$_version/$_asset"
    _tmp="$(mktemp -d /tmp/mosdns-installer.XXXXXX)" || die "无法创建临时目录。"

    say "下载官方 mosdns $_version ($_arch)..."
    download_to "$_url" "$_tmp/$_asset" || { rm -rf "$_tmp"; die "下载失败：$_url"; }
    _expected="$(release_digest "$_version" "$_asset")"
    if [ -n "$_expected" ]; then
        _actual="$(sha256sum "$_tmp/$_asset" | awk '{print $1}')"
        [ "$_actual" = "$_expected" ] || { rm -rf "$_tmp"; die "SHA-256 校验失败。"; }
        ok "官方 SHA-256 校验通过。"
    else
        warn "未取得官方摘要，跳过摘要比对。"
    fi

    unzip -oq "$_tmp/$_asset" -d "$_tmp/unpacked" || { rm -rf "$_tmp"; die "解压失败。"; }
    _new_bin="$(find "$_tmp/unpacked" -type f -name mosdns | head -n 1)"
    [ -n "$_new_bin" ] || { rm -rf "$_tmp"; die "安装包内未找到 mosdns。"; }
    chmod 0755 "$_new_bin"
    "$_new_bin" version >/dev/null 2>&1 || { rm -rf "$_tmp"; die "二进制无法运行，可能架构不匹配。"; }

    mkdir -p "$MOSDNS_DIR" "$RULE_DIR" "$BACKUP_DIR"
    _backup="$(make_backup core-update)" || { rm -rf "$_tmp"; die "备份失败。"; }
    systemctl stop mosdns.service >/dev/null 2>&1 || true
    install -m 0755 "$_new_bin" "$BIN_FILE"
    install_service
    rm -rf "$_tmp"
    ok "已安装：$($BIN_FILE version 2>&1 | head -n 1)"
    say "备份位置：$_backup"
}

ensure_rule_files() {
    mkdir -p "$RULE_DIR" "$BACKUP_DIR"
    if [ ! -f "$RULE_DIR/custom-direct.txt" ]; then
        printf '%s\n' '# 每行一个强制直连域名；自动匹配其子域名' >"$RULE_DIR/custom-direct.txt"
        printf '%s\n' '# example.cn' >>"$RULE_DIR/custom-direct.txt"
    fi
    if [ ! -f "$RULE_DIR/custom-proxy.txt" ]; then
        printf '%s\n' '# 每行一个强制代理域名；优先级高于直连列表' >"$RULE_DIR/custom-proxy.txt"
        printf '%s\n' '# example.com' >>"$RULE_DIR/custom-proxy.txt"
    fi
    chmod 0644 "$RULE_DIR/custom-direct.txt" "$RULE_DIR/custom-proxy.txt"
}

write_domestic_udp_preset() {
    cat >"$DOMESTIC_UPSTREAMS" <<'EOF_DOMESTIC'
# 国内 DNS 上游；每行一个，至少保留两个
# 阿里 DNS
udp://223.5.5.5
# 腾讯 DNSPod
udp://119.29.29.29
# 百度 DNS
udp://180.76.76.76
EOF_DOMESTIC
    chmod 0644 "$DOMESTIC_UPSTREAMS"
}

write_domestic_doh_preset() {
    cat >"$DOMESTIC_UPSTREAMS" <<'EOF_DOMESTIC_DOH'
# 国内 DoH 优先预设；百度官方未提供可确认的 DoH，因此保留 UDP 第三出口
# 阿里 DNS over HTTPS
https://dns.alidns.com/dns-query|223.5.5.5
# 腾讯 DNSPod DNS over HTTPS
https://doh.pub/dns-query|1.12.12.12
# 百度传统 DNS
udp://180.76.76.76
EOF_DOMESTIC_DOH
    chmod 0644 "$DOMESTIC_UPSTREAMS"
}

write_overseas_default() {
    cat >"$OVERSEAS_UPSTREAMS" <<'EOF_OVERSEAS'
# 境外 DNS 上游；可由 mosdns 直连或严格通过 PassWall2 SOCKS5
# Google DNS
https://8.8.8.8/dns-query
# Cloudflare DNS
https://1.1.1.1/dns-query
EOF_OVERSEAS
    chmod 0644 "$OVERSEAS_UPSTREAMS"
}

write_default_upstreams() {
    mkdir -p "$UPSTREAM_DIR"
    write_domestic_udp_preset
    write_overseas_default
}

ensure_upstream_files() {
    mkdir -p "$UPSTREAM_DIR"
    [ -s "$DOMESTIC_UPSTREAMS" ] || write_domestic_udp_preset
    [ -s "$OVERSEAS_UPSTREAMS" ] || write_overseas_default
}

validate_upstream_file() {
    _file="$1"
    _label="$2"
    _count=0
    while IFS= read -r _upstream || [ -n "$_upstream" ]; do
        _upstream="$(printf '%s' "$_upstream" | sed 's/[[:space:]]*#.*$//; s/^[[:space:]]*//; s/[[:space:]]*$//')"
        [ -n "$_upstream" ] || continue
        _addr="${_upstream%%|*}"
        _dial=""
        case "$_upstream" in *'|'*) _dial="${_upstream#*|}" ;; esac
        case "$_addr" in
            udp://*|tcp://*|tls://*|https://*|quic://*) _count=$((_count + 1)) ;;
            *) err "$_label 上游格式无效：$_upstream"; return 1 ;;
        esac
        case "$_dial" in
            *'|'*|*[[:space:]]*|*/*) err "$_label 上游拨号地址无效：$_dial"; return 1 ;;
        esac
    done <"$_file"
    if [ "$_count" -lt 2 ]; then
        err "$_label 上游至少需要两个，当前只有 $_count 个。"
        return 1
    fi
    return 0
}

render_upstreams() {
    _file="$1"
    _prefix="$2"
    _index=0
    while IFS= read -r _upstream || [ -n "$_upstream" ]; do
        _upstream="$(printf '%s' "$_upstream" | sed 's/[[:space:]]*#.*$//; s/^[[:space:]]*//; s/[[:space:]]*$//')"
        [ -n "$_upstream" ] || continue
        _addr="${_upstream%%|*}"
        _dial=""
        case "$_upstream" in *'|'*) _dial="${_upstream#*|}" ;; esac
        _index=$((_index + 1))
        printf "        - tag: %s_%s\n" "$_prefix" "$_index"
        printf "          addr: '%s'\n" "$(yaml_escape "$_addr")"
        if [ -n "$_dial" ]; then
            printf "          dial_addr: '%s'\n" "$(yaml_escape "$_dial")"
        else
            printf "          bootstrap: '223.5.5.5'\n"
        fi
        if [ "$_prefix" = "overseas" ] && [ "${OVERSEAS_MODE:-direct}" = "socks5_strict" ]; then
            case "$_addr" in https://*) printf "          enable_http3: false\n" ;; esac
        fi
    done <"$_file"
}

update_rules() {
    require_debian
    apply_install_proxy
    command -v curl >/dev/null 2>&1 || install_dependencies
    ensure_rule_files
    _tmp_list="$(mktemp /tmp/mosdns-direct-list.XXXXXX)" || return 1
    say "下载国内常用直连域名列表..."
    download_to "$DIRECT_LIST_URL" "$_tmp_list" || {
        rm -f "$_tmp_list"
        err "规则下载失败，保留现有规则。"
        return 1
    }
    _lines="$(wc -l <"$_tmp_list" | tr -d ' ')"
    case "$_lines" in ''|*[!0-9]*) _lines=0 ;; esac
    if [ "$_lines" -lt 10000 ]; then
        rm -f "$_tmp_list"
        err "规则数量异常（$_lines 行），拒绝覆盖。"
        return 1
    fi
    [ -f "$RULE_DIR/direct-list.txt" ] && \
        cp -p "$RULE_DIR/direct-list.txt" "$BACKUP_DIR/direct-list.$(now_stamp).txt"
    mv "$_tmp_list" "$RULE_DIR/direct-list.txt"
    chmod 0644 "$RULE_DIR/direct-list.txt"
    ok "直连域名规则已更新，共 $_lines 行。"
    systemctl is-active --quiet mosdns.service && systemctl restart mosdns.service || true
}

load_settings() {
    LISTEN_IP="$(detect_lan_ip)"
    LISTEN_PORT="$DEFAULT_PORT"
    CACHE_SIZE="$DEFAULT_CACHE_SIZE"
    LAN_CIDR=""
    OVERSEAS_MODE="direct"
    OVERSEAS_SOCKS5=""
    # shellcheck disable=SC1090
    [ -f "$ENV_FILE" ] && . "$ENV_FILE"
    case "$OVERSEAS_MODE" in direct|socks5_strict) ;; *) OVERSEAS_MODE="direct" ;; esac
    if [ "$OVERSEAS_MODE" = "socks5_strict" ] && ! valid_socks5_address "$OVERSEAS_SOCKS5"; then
        warn "保存的境外 SOCKS5 地址无效，已恢复为境外 DNS 直连模式。"
        OVERSEAS_MODE="direct"
        OVERSEAS_SOCKS5=""
    fi
}

save_settings() {
    cat >"$ENV_FILE" <<EOF_ENV
LISTEN_IP='$LISTEN_IP'
LISTEN_PORT='$LISTEN_PORT'
CACHE_SIZE='$CACHE_SIZE'
LAN_CIDR='$LAN_CIDR'
OVERSEAS_MODE='$OVERSEAS_MODE'
OVERSEAS_SOCKS5='$OVERSEAS_SOCKS5'
EOF_ENV
    chmod 0600 "$ENV_FILE"
}

yaml_escape() {
    printf '%s' "$1" | sed "s/'/''/g"
}

check_port_conflict() {
    _ip="$1"
    _port="$2"
    systemctl stop mosdns.service >/dev/null 2>&1 || true
    _listeners="$(ss -H -lntu 2>/dev/null | awk '{print $5}')"
    _escaped_ip="$(printf '%s' "$_ip" | sed 's/\./\\./g')"
    printf '%s\n' "$_listeners" | grep -Eq "^$_escaped_ip:$_port$|^0\.0\.0\.0:$_port$|^\*:$_port$|^\[::\]:$_port$" && return 1
    return 0
}

generate_config() {
    require_debian
    [ -x "$BIN_FILE" ] || die "请先安装 mosdns 核心。"
    ensure_rule_files
    ensure_upstream_files
    [ -s "$RULE_DIR/direct-list.txt" ] || update_rules || die "直连域名规则不可用。"
    validate_upstream_file "$DOMESTIC_UPSTREAMS" "国内" || return 1
    validate_upstream_file "$OVERSEAS_UPSTREAMS" "境外" || return 1
    load_settings

    [ -n "$LISTEN_IP" ] || die "没有检测到局域网 IPv4 地址。"
    LISTEN_IP="$(ask "Debian 局域网 IPv4（mosdns 监听地址）" "$LISTEN_IP")"
    valid_ipv4 "$LISTEN_IP" || die "IPv4 地址无效。"
    LISTEN_PORT="$(ask "DNS 监听端口" "$LISTEN_PORT")"
    case "$LISTEN_PORT" in ''|*[!0-9]*) die "端口必须是整数。" ;; esac
    [ "$LISTEN_PORT" -ge 1 ] && [ "$LISTEN_PORT" -le 65535 ] || die "端口必须在 1–65535 之间。"
    LAN_CIDR="$(detect_lan_cidr "$LISTEN_IP")"
    say "国内 DNS 上游："
    sed '/^[[:space:]]*#/d; /^[[:space:]]*$/d' "$DOMESTIC_UPSTREAMS"
    say "境外 DNS 上游："
    sed '/^[[:space:]]*#/d; /^[[:space:]]*$/d' "$OVERSEAS_UPSTREAMS"
    say "两组上游均由 mosdns 分流并发处理。"
    configure_overseas_route || return 1
    if [ "$OVERSEAS_MODE" = "socks5_strict" ]; then
        say "境外 DoH 将严格通过 PassWall2 SOCKS5：$OVERSEAS_SOCKS5"
    else
        say "境外 DoH 将由 mosdns 直接访问。"
    fi
    CACHE_SIZE="$(ask "缓存条目数" "$CACHE_SIZE")"
    case "$CACHE_SIZE" in ''|*[!0-9]*) die "缓存条目数必须是整数。" ;; esac
    [ "$CACHE_SIZE" -ge 1 ] || die "缓存条目数必须大于 0。"

    if ! check_port_conflict "$LISTEN_IP" "$LISTEN_PORT"; then
        err "$LISTEN_IP:$LISTEN_PORT 已被其他服务占用："
        ss -lntup 2>/dev/null | grep ":$LISTEN_PORT " || true
        err "请停止冲突的 DNS 服务，或为 mosdns 选择其他地址/端口。"
        return 1
    fi

    _backup="$(make_backup config)" || die "备份失败。"
    _domestic_yaml="$(render_upstreams "$DOMESTIC_UPSTREAMS" domestic)"
    _overseas_yaml="$(render_upstreams "$OVERSEAS_UPSTREAMS" overseas)"
    _overseas_proxy_yaml=""
    if [ "$OVERSEAS_MODE" = "socks5_strict" ]; then
        _overseas_proxy_yaml="      socks5: '$(yaml_escape "$OVERSEAS_SOCKS5")'"
    fi
    cat >"$CONF_FILE.new" <<EOF_CONFIG
log:
  level: info

api:
  http: '127.0.0.1:9091'

plugins:
  - tag: cache_main
    type: cache
    args:
      size: $CACHE_SIZE
      lazy_cache_ttl: 86400
      dump_file: '$STATE_DIR/cache.dump'
      dump_interval: 600

  - tag: direct_domains
    type: domain_set
    args:
      exps:
        - 'cn'
      files:
        - '$RULE_DIR/direct-list.txt'
        - '$RULE_DIR/custom-direct.txt'

  - tag: proxy_domains
    type: domain_set
    args:
      files:
        - '$RULE_DIR/custom-proxy.txt'

  - tag: local_forward
    type: forward
    args:
      concurrent: 3
      upstreams:
$_domestic_yaml

  - tag: remote_forward
    type: forward
    args:
      concurrent: 3
$_overseas_proxy_yaml
      upstreams:
$_overseas_yaml

  - tag: main_sequence
    type: sequence
    args:
      - exec: '\$cache_main'
      - matches:
          - 'has_resp'
        exec: 'accept'
      - matches:
          - 'qname \$proxy_domains'
        exec: '\$remote_forward'
      - matches:
          - 'has_resp'
        exec: 'accept'
      - matches:
          - 'qname \$direct_domains'
        exec: '\$local_forward'
      - matches:
          - 'has_resp'
        exec: 'accept'
      - exec: '\$remote_forward'

  - tag: udp_server
    type: udp_server
    args:
      entry: main_sequence
      listen: '$LISTEN_IP:$LISTEN_PORT'

  - tag: tcp_server
    type: tcp_server
    args:
      entry: main_sequence
      listen: '$LISTEN_IP:$LISTEN_PORT'
EOF_CONFIG

    mv "$CONF_FILE.new" "$CONF_FILE"
    chmod 0644 "$CONF_FILE"
    save_settings
    chown -R root:mosdns "$MOSDNS_DIR"
    chmod 0750 "$MOSDNS_DIR" "$RULE_DIR" "$UPSTREAM_DIR"
    chmod 0640 "$CONF_FILE" "$RULE_DIR"/*.txt "$UPSTREAM_DIR"/*.txt

    if validate_config; then
        ok "配置语法与启动校验通过。"
    else
        err "配置校验失败；原配置备份位于 $_backup。"
        return 1
    fi

    systemctl daemon-reload
    systemctl enable --now mosdns.service >/dev/null 2>&1 || {
        err "mosdns 启动失败："
        journalctl -u mosdns.service -n 40 --no-pager
        return 1
    }
    sleep 1
    systemctl is-active --quiet mosdns.service || {
        err "mosdns 未保持运行："
        journalctl -u mosdns.service -n 40 --no-pager
        return 1
    }
    ok "mosdns 正在监听 $LISTEN_IP:$LISTEN_PORT。"
    say "备份位置：$_backup"

}

validate_config() {
    _test_conf="$(mktemp /tmp/mosdns-config-test.XXXXXX.yaml)" || return 1
    _test_log="$(mktemp /tmp/mosdns-config-test.XXXXXX.log)" || { rm -f "$_test_conf"; return 1; }
    sed \
        -e "s/listen: '$LISTEN_IP:$LISTEN_PORT'/listen: '127.0.0.1:15353'/g" \
        -e "s/http: '127.0.0.1:9091'/http: '127.0.0.1:19091'/" \
        "$CONF_FILE" >"$_test_conf"
    "$BIN_FILE" start -d "$MOSDNS_DIR" -c "$_test_conf" >"$_test_log" 2>&1 &
    _pid=$!
    sleep 2
    if kill -0 "$_pid" >/dev/null 2>&1; then
        kill "$_pid" >/dev/null 2>&1 || true
        wait "$_pid" 2>/dev/null || true
        rm -f "$_test_conf" "$_test_log"
        return 0
    fi
    wait "$_pid" 2>/dev/null || true
    sed -n '1,120p' "$_test_log" >&2
    rm -f "$_test_conf" "$_test_log"
    return 1
}

fake_ip_check() {
    _server="$1"
    _found=""
    for _domain in openwrt.org cloudflare.com; do
        _answer="$(dig +time=3 +tries=1 +short @"$_server" "$_domain" A 2>/dev/null)"
        printf '%s\n' "$_answer" | grep -q '^198\.18\.' && _found="$_found $_domain"
    done
    if [ -n "$_found" ]; then
        warn "检测到 198.18.x.x FakeDNS 结果：$_found"
        warn "上游返回了 FakeDNS 地址；请检查网络中是否仍有 FakeDNS 劫持。"
    else
        ok "未检测到 198.18.x.x FakeDNS。"
    fi
}

diagnose() {
    require_debian
    header
    # shellcheck disable=SC1091
    printf '%s\n' "系统：$(. /etc/os-release; printf '%s' "$PRETTY_NAME")"
    printf '%s\n' "架构：$(uname -m)"
    if [ -x "$BIN_FILE" ]; then
        printf '%s\n' "mosdns：$($BIN_FILE version 2>&1 | head -n 1)"
    else
        printf '%s\n' "mosdns：未安装"
    fi
    if systemctl is-active --quiet mosdns.service; then
        ok "服务正在运行。"
    else
        err "服务未运行。"
    fi
    printf '\n%s\n' "监听端口："
    ss -lntup 2>/dev/null | grep -E '(:53 |:53$|:5335|:9091)' || true

    load_settings
    printf '\n%s\n' "配置："
    printf '%s\n' "  Debian DNS：$LISTEN_IP:$LISTEN_PORT"
    ensure_upstream_files
    printf '%s\n' "  国内上游："
    sed '/^[[:space:]]*#/d; /^[[:space:]]*$/d; s/^/    - /' "$DOMESTIC_UPSTREAMS"
    printf '%s\n' "  境外上游："
    sed '/^[[:space:]]*#/d; /^[[:space:]]*$/d; s/^/    - /' "$OVERSEAS_UPSTREAMS"
    if [ "$OVERSEAS_MODE" = "socks5_strict" ]; then
        printf '%s\n' "  境外出口：严格通过 PassWall2 SOCKS5 $OVERSEAS_SOCKS5"
        if test_overseas_socks5; then
            ok "PassWall2 SOCKS5 出口可用。"
        else
            err "PassWall2 SOCKS5 出口不可用。"
        fi
    else
        printf '%s\n' "  境外出口：mosdns 直接访问加密 DoH"
    fi
    load_install_proxy
    if [ -n "$INSTALL_HTTP_PROXY" ]; then
        printf '%s\n' "  安装下载代理：$(mask_proxy_url "$INSTALL_HTTP_PROXY")"
    else
        printf '%s\n' "  安装下载代理：未启用"
    fi

    printf '\n%s\n' "查询测试："
    for _domain in baidu.com cloudflare.com; do
        printf '%s\n' "--- $_domain"
        dig +time=5 +tries=1 +short @"$LISTEN_IP" -p "$LISTEN_PORT" "$_domain" A 2>&1 | sed -n '1,12p'
    done
    [ "$LISTEN_PORT" = "53" ] && fake_ip_check "$LISTEN_IP"

    printf '\n%s\n' "最近日志："
    journalctl -u mosdns.service -n 40 --no-pager 2>/dev/null
}

custom_rules_menu() {
    require_debian
    ensure_rule_files
    while :; do
        header
        printf '%s\n' "自定义域名规则"
        printf '%s\n' "  1) 添加强制直连域名"
        printf '%s\n' "  2) 添加强制代理域名"
        printf '%s\n' "  3) 查看自定义规则"
        printf '%s\n' "  4) 编辑直连列表"
        printf '%s\n' "  5) 编辑代理列表"
        printf '%s\n' "  6) 重启 mosdns"
        printf '%s\n' "  0) 返回"
        _choice="$(ask "请选择" "0")"
        case "$_choice" in
            1|2)
                _domain="$(ask "域名（不要带协议和路径）" "")"
                _domain="$(printf '%s' "$_domain" | sed 's#^[a-zA-Z]*://##; s#/.*$##; s/^\.//; s/\.$//' | tr '[:upper:]' '[:lower:]')"
                case "$_domain" in
                    ''|*[!a-z0-9._-]*) err "域名格式无效。" ;;
                    *)
                        if [ "$_choice" = "1" ]; then _file="$RULE_DIR/custom-direct.txt"; else _file="$RULE_DIR/custom-proxy.txt"; fi
                        grep -Fxq "$_domain" "$_file" || printf '%s\n' "$_domain" >>"$_file"
                        chown root:mosdns "$_file"; chmod 0640 "$_file"
                        ok "已添加 $_domain"
                        ;;
                esac
                pause
                ;;
            3)
                say "强制直连："; sed -n '1,200p' "$RULE_DIR/custom-direct.txt"
                say "强制代理："; sed -n '1,200p' "$RULE_DIR/custom-proxy.txt"
                pause
                ;;
            4) "${EDITOR:-nano}" "$RULE_DIR/custom-direct.txt" ;;
            5) "${EDITOR:-nano}" "$RULE_DIR/custom-proxy.txt" ;;
            6) systemctl restart mosdns.service && ok "mosdns 已重启。"; pause ;;
            0) return 0 ;;
            *) err "无效选项。"; sleep 1 ;;
        esac
    done
}

upstream_menu() {
    require_debian
    ensure_upstream_files
    while :; do
        load_settings
        header
        printf '%s\n' "DNS 多上游管理"
        printf '%s\n' ""
        say "当前国内上游："
        sed '/^[[:space:]]*#/d; /^[[:space:]]*$/d' "$DOMESTIC_UPSTREAMS"
        say "当前境外上游："
        sed '/^[[:space:]]*#/d; /^[[:space:]]*$/d' "$OVERSEAS_UPSTREAMS"
        if [ "$OVERSEAS_MODE" = "socks5_strict" ]; then
            say "境外出口：严格通过 PassWall2 SOCKS5 $OVERSEAS_SOCKS5"
        else
            say "境外出口：mosdns 直连"
        fi
        printf '%s\n' ""
        printf '%s\n' "  1) 编辑国内 DNS 上游"
        printf '%s\n' "  2) 编辑境外 DNS 上游"
        printf '%s\n' "  3) 向国内上游添加地址"
        printf '%s\n' "  4) 向境外上游添加地址"
        printf '%s\n' "  5) 切换国内 UDP/DoH 预设"
        printf '%s\n' "  6) 恢复全部默认上游"
        printf '%s\n' "  7) 校验并应用上游配置"
        printf '%s\n' "  8) 修改境外 DNS 出口模式并重新生成配置"
        printf '%s\n' "  0) 返回"
        _choice="$(ask "请选择" "0")"
        case "$_choice" in
            1) "${EDITOR:-nano}" "$DOMESTIC_UPSTREAMS" ;;
            2) "${EDITOR:-nano}" "$OVERSEAS_UPSTREAMS" ;;
            3|4)
                _address="$(ask "DNS 地址（可用 URL|拨号IP，如 https://example/dns-query|1.2.3.4）" "")"
                _check_addr="${_address%%|*}"
                case "$_check_addr" in
                    udp://*|tcp://*|tls://*|https://*|quic://*)
                        if [ "$_choice" = "3" ]; then _file="$DOMESTIC_UPSTREAMS"; else _file="$OVERSEAS_UPSTREAMS"; fi
                        grep -Fxq "$_address" "$_file" || printf '%s\n' "$_address" >>"$_file"
                        chown root:mosdns "$_file" 2>/dev/null || true
                        chmod 0640 "$_file"
                        ok "上游已添加。"
                        ;;
                    *) err "地址必须以 udp://、tcp://、tls://、https:// 或 quic:// 开头。" ;;
                esac
                pause
                ;;
            5)
                printf '%s\n' "  1) 全 UDP：阿里 + 腾讯 + 百度"
                printf '%s\n' "  2) DoH 优先：阿里 DoH + 腾讯 DoH + 百度 UDP"
                printf '%s\n' "  3) 手动编辑国内上游"
                _preset="$(ask "请选择国内 DNS 协议" "2")"
                _backup="$(make_backup domestic-protocol)" || die "备份失败。"
                case "$_preset" in
                    1) write_domestic_udp_preset; ok "国内上游已切换为全 UDP。" ;;
                    2) write_domestic_doh_preset; ok "国内上游已切换为 DoH 优先。" ;;
                    3) "${EDITOR:-nano}" "$DOMESTIC_UPSTREAMS" ;;
                    *) err "无效选项。" ;;
                esac
                pause
                ;;
            6)
                confirm "恢复阿里/腾讯/百度及 Google/Cloudflare 默认组合？" N && {
                    _backup="$(make_backup upstream-reset)" || die "备份失败。"
                    write_default_upstreams
                    ok "默认上游已恢复；备份位于 $_backup。"
                }
                pause
                ;;
            7)
                if ! validate_upstream_file "$DOMESTIC_UPSTREAMS" "国内" || \
                   ! validate_upstream_file "$OVERSEAS_UPSTREAMS" "境外"; then
                    pause
                    continue
                fi
                if [ -x "$BIN_FILE" ] && [ -s "$RULE_DIR/direct-list.txt" ]; then
                    generate_config
                else
                    ok "上游文件校验通过；安装 mosdns 后会自动应用。"
                fi
                pause
                ;;
            8)
                if [ -x "$BIN_FILE" ] && [ -s "$RULE_DIR/direct-list.txt" ]; then
                    generate_config
                else
                    err "请先完成 mosdns 核心与规则安装。"
                fi
                pause
                ;;
            0) return 0 ;;
            *) err "无效选项。"; sleep 1 ;;
        esac
    done
}

install_proxy_menu() {
    require_debian
    while :; do
        header
        load_install_proxy
        printf '%s\n' "安装及规则下载 HTTP 代理"
        if [ -n "$INSTALL_HTTP_PROXY" ]; then
            printf '%s\n' "  当前：$(mask_proxy_url "$INSTALL_HTTP_PROXY")"
        else
            printf '%s\n' "  当前：未启用"
        fi
        printf '%s\n' ""
        printf '%s\n' "  1) 设置或修改代理"
        printf '%s\n' "  2) 测试当前代理"
        printf '%s\n' "  3) 关闭并删除保存的代理"
        printf '%s\n' "  0) 返回"
        _choice="$(ask "请选择" "0")"
        case "$_choice" in
            1) configure_install_proxy; pause ;;
            2)
                if [ -z "$INSTALL_HTTP_PROXY" ]; then
                    err "尚未设置 HTTP 代理。"
                elif test_install_proxy; then
                    ok "HTTP 代理连接测试通过。"
                else
                    err "HTTP 代理连接测试失败。"
                fi
                pause
                ;;
            3)
                confirm "确认关闭并删除保存的安装下载代理？" N && disable_saved_proxy
                pause
                ;;
            0) return 0 ;;
            *) err "无效选项。"; sleep 1 ;;
        esac
    done
}

install_rule_timer() {
    require_debian
    cat >"$UPDATER_FILE" <<EOF_UPDATER
#!/bin/sh
set -eu
url='$DIRECT_LIST_URL'
dest='$RULE_DIR/direct-list.txt'
proxy_file='$PROXY_FILE'
if [ -s "\$proxy_file" ]; then
    proxy="\$(sed -n '1p' "\$proxy_file")"
    case "\$proxy" in
        http://*|https://*)
            http_proxy="\$proxy"
            https_proxy="\$proxy"
            HTTP_PROXY="\$proxy"
            HTTPS_PROXY="\$proxy"
            export http_proxy https_proxy HTTP_PROXY HTTPS_PROXY
            ;;
    esac
fi
tmp="\$(mktemp /tmp/mosdns-direct-list.XXXXXX)"
trap 'rm -f "\$tmp"' EXIT
curl -fsSL --connect-timeout 15 --retry 2 -o "\$tmp" "\$url"
lines="\$(wc -l <"\$tmp" | tr -d ' ')"
[ "\$lines" -ge 10000 ]
install -o root -g mosdns -m 0640 "\$tmp" "\$dest"
/usr/local/bin/mosdns version >/dev/null
systemctl try-restart mosdns.service
EOF_UPDATER
    chmod 0755 "$UPDATER_FILE"
    cat >"$UPDATE_SERVICE_FILE" <<EOF_UPDATE_SERVICE
[Unit]
Description=Update mosdns direct-domain rules
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=$UPDATER_FILE
EOF_UPDATE_SERVICE
    cat >"$TIMER_FILE" <<'EOF_TIMER'
[Unit]
Description=Weekly mosdns rule update

[Timer]
OnCalendar=Sun *-*-* 04:15:00
RandomizedDelaySec=30m
Persistent=true

[Install]
WantedBy=timers.target
EOF_TIMER
    systemctl daemon-reload
    systemctl enable --now mosdns-rules-update.timer >/dev/null
    ok "已启用每周日自动更新规则。"
    systemctl list-timers mosdns-rules-update.timer --no-pager
}

restore_backup() {
    require_debian
    _latest="$(find "$BACKUP_DIR" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | sort | tail -n 1)"
    [ -n "$_latest" ] || die "没有可恢复的配置备份。"
    say "最新备份：$_latest"
    confirm "恢复该备份中的配置与服务文件？" N || { say "已取消。"; return 0; }
    systemctl stop mosdns.service >/dev/null 2>&1 || true
    mkdir -p "$UPSTREAM_DIR"
    [ -f "$_latest/config.yaml" ] && cp "$_latest/config.yaml" "$CONF_FILE"
    [ -f "$_latest/installer.conf" ] && cp "$_latest/installer.conf" "$ENV_FILE"
    [ -f "$_latest/install-proxy.txt" ] && cp "$_latest/install-proxy.txt" "$PROXY_FILE"
    [ -f "$_latest/mosdns.service" ] && cp "$_latest/mosdns.service" "$SERVICE_FILE"
    [ -f "$_latest/domestic-upstreams.txt" ] && cp "$_latest/domestic-upstreams.txt" "$DOMESTIC_UPSTREAMS"
    [ -f "$_latest/overseas-upstreams.txt" ] && cp "$_latest/overseas-upstreams.txt" "$OVERSEAS_UPSTREAMS"
    systemctl daemon-reload
    systemctl restart mosdns.service || { journalctl -u mosdns.service -n 30 --no-pager; return 1; }
    ok "最新配置备份已恢复。"
}

uninstall_mosdns() {
    require_debian
    warn "将停止并删除 mosdns 程序、systemd 服务和自动更新器。"
    warn "配置、规则与备份目录 $MOSDNS_DIR 默认保留。"
    confirm "确认卸载？" N || { say "已取消。"; return 0; }
    systemctl disable --now mosdns-rules-update.timer >/dev/null 2>&1 || true
    systemctl disable --now mosdns.service >/dev/null 2>&1 || true
    rm -f "$SERVICE_FILE" "$TIMER_FILE" "$UPDATE_SERVICE_FILE" "$UPDATER_FILE" "$BIN_FILE"
    systemctl daemon-reload
    systemctl reset-failed >/dev/null 2>&1 || true
    ok "mosdns 已卸载；配置和备份仍保留在 $MOSDNS_DIR。"
}

full_install() {
    require_debian
    install_core || return 1
    update_rules || return 1
    generate_config || return 1
    printf '\n'
    ok "完整安装完成。"
    load_settings
    printf '%s\n' "下一步：在 ROS DHCP 中，把需要使用该 DNS 的客户端 DNS 设置为 $LISTEN_IP。"
    printf '%s\n' "mosdns 只负责 DNS；客户端实际流量是否代理仍由其网关和 OpenWrt 策略决定。"
}

show_help() {
    cat <<EOF_HELP
用法：sh mosdns-debian-installer.sh

用于 Debian 11–13 的 mosdns v5 互动安装器。
目标架构：局域网设备 -> Debian mosdns -> 国内 DNS / 境外加密 DoH。
境外 DoH 可选择直连，或严格通过 PassWall2 SOCKS5；mosdns 不代理网站实际流量。
国内和境外 DNS 均支持多个可编辑上游，并发查询并自动使用可用响应。
安装核心、依赖和规则下载可选使用 HTTP 代理；DNS 查询本身不使用该代理。

参数：
  --help       显示帮助
  --version    显示脚本版本
EOF_HELP
}

main_menu() {
    require_debian
    while :; do
        header
        if systemctl is-active --quiet mosdns.service 2>/dev/null; then
            printf "%b状态：mosdns 运行中%b\n" "$C_GREEN" "$C_RESET"
        else
            printf "%b状态：mosdns 未运行%b\n" "$C_YELLOW" "$C_RESET"
        fi
        printf '\n%s\n' "  1) 完整安装并配置（首次使用）"
        printf '%s\n' "  2) 安装或更新 mosdns 核心"
        printf '%s\n' "  3) 生成/修改 DNS 分流配置"
        printf '%s\n' "  4) 更新国内直连域名规则"
        printf '%s\n' "  5) 状态检查与故障诊断"
        printf '%s\n' "  6) 管理自定义直连/代理域名"
        printf '%s\n' "  7) 管理国内/境外 DNS 多上游"
        printf '%s\n' "  8) 启用每周规则自动更新"
        printf '%s\n' "  9) 恢复最新配置备份"
        printf '%s\n' " 10) 卸载 mosdns"
        printf '%s\n' " 11) 设置安装及规则下载 HTTP 代理"
        printf '%s\n' "  0) 退出"
        _choice="$(ask "请选择" "1")"
        case "$_choice" in
            1) full_install; pause ;;
            2) install_core; [ -f "$CONF_FILE" ] && systemctl restart mosdns.service >/dev/null 2>&1 || true; pause ;;
            3) generate_config; pause ;;
            4) update_rules; pause ;;
            5) diagnose; pause ;;
            6) custom_rules_menu ;;
            7) upstream_menu ;;
            8) install_rule_timer; pause ;;
            9) restore_backup; pause ;;
            10) uninstall_mosdns; pause ;;
            11) install_proxy_menu ;;
            0) exit 0 ;;
            *) err "无效选项。"; sleep 1 ;;
        esac
    done
}

case "${1:-}" in
    --help|-h) show_help; exit 0 ;;
    --version|-V) printf '%s\n' "$SCRIPT_VERSION"; exit 0 ;;
    '') main_menu ;;
    *) err "未知参数：$1"; show_help; exit 2 ;;
esac
