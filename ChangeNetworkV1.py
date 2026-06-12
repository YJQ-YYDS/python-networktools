#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Windows 网卡快速配置工具（最终版：支持仅修改 DNS，不影响 IP）
功能：
- 查看所有网卡及当前配置（IP/掩码/网关/DNS）
- 切换 DHCP / 静态IP（完整配置）
- 单独修改 DNS（适用于 DHCP 或静态模式，不影响 IP）
- 添加多个额外IP
- 启用/禁用网卡
- 修改后自动刷新 5 次，每次间隔 2 秒
"""

import subprocess
import re
import sys
import os
import ctypes
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox

# ---------- 管理员权限 ----------
def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

def run_as_admin():
    script = os.path.abspath(sys.argv[0])
    ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, script, None, 1)
    sys.exit()

if not is_admin():
    print("本工具需要管理员权限，正在请求提升...")
    run_as_admin()

# ---------- netsh 执行辅助 ----------
def run_netsh_utf8(args):
    cmd = f"chcp 65001 > nul && netsh {' '.join(args)}"
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=False, encoding=None)
        stdout = result.stdout.decode('utf-8', errors='replace')
        return stdout
    except Exception as e:
        print(f"执行命令失败: {e}")
        return ""

def run_netsh_gbk(args):
    try:
        result = subprocess.run(args, capture_output=True, text=True, encoding='gbk', errors='replace')
        return result.stdout if result.stdout is not None else ""
    except Exception as e:
        print(f"执行命令 {' '.join(args)} 时出错: {e}")
        return ""

# ---------- 获取网卡列表 ----------
def get_adapters():
    output = run_netsh_utf8(["interface", "show", "interface"])
    lines = output.splitlines()
    adapters = []
    for line in lines:
        match = re.match(r"\s*(\S+)\s+(\S+)\s+(\S+)\s+(.+)", line.strip())
        if match:
            state = match.group(1)
            name = match.group(4).strip()
            lower_name = name.lower()
            if lower_name in ("loopback pseudo-interface 1", "bluetooth"):
                continue
            if any(v in lower_name for v in ("virtual", "vmware", "vbox", "hyper-v")):
                continue
            if name and not name.isspace():
                adapters.append((name, state))
    print(f"[DEBUG] 获取到网卡列表: {adapters}")
    return adapters

# ---------- 获取单个网卡详细配置 ----------
def get_adapter_config(adapter_name):
    config = {
        'enabled': False,
        'dhcp_enabled': True,
        'ip_list': [],
        'gateway': None,
        'dns_servers': [],
        'dhcp_dns': True
    }

    # 网卡启用状态
    output_state = run_netsh_utf8(["interface", "show", "interface", f"name={adapter_name}"])
    if "已启用" in output_state or "Enabled" in output_state:
        config['enabled'] = True

    # IP 配置
    output = run_netsh_gbk(["netsh", "interface", "ip", "show", "config", f"name={adapter_name}"])
    print(f"[DEBUG] netsh show config 输出:\n{output}")

    # DHCP 状态
    if re.search(r"DHCP 启用:\s*是", output) or re.search(r"DHCP enabled:\s*Yes", output, re.IGNORECASE):
        config['dhcp_enabled'] = True
    else:
        config['dhcp_enabled'] = False

    # 解析 IP 和掩码
    lines = output.splitlines()
    ip_list = []
    current_ip = None
    for line in lines:
        ip_match = re.search(r"(?:IP\s+Address|IP\s+地址)\s*:\s*([0-9.]+)", line, re.IGNORECASE)
        if ip_match:
            current_ip = ip_match.group(1)
            continue
        mask_match = re.search(r"Subnet\s+Prefix\s*:\s*[0-9./]+\s*\(mask\s+([0-9.]+)\)", line, re.IGNORECASE)
        if mask_match and current_ip:
            mask = mask_match.group(1)
            ip_list.append((current_ip, mask))
            current_ip = None
    if current_ip:
        ip_list.append((current_ip, "255.255.255.0"))
    config['ip_list'] = ip_list
    print(f"[DEBUG] 提取到的 IP+掩码: {ip_list}")

    # 默认网关
    gw_patterns = [
        r"Default\s+Gateway:\s*([0-9.]+)",
        r"默认网关:\s*([0-9.]+)"
    ]
    gateway = None
    for pattern in gw_patterns:
        m = re.search(pattern, output, re.IGNORECASE)
        if m and m.group(1) != "0.0.0.0":
            gateway = m.group(1)
            break
    config['gateway'] = gateway
    print(f"[DEBUG] 默认网关: {config['gateway']}")

    # DNS 信息（提取所有 IPv4 地址）
    output_dns = run_netsh_gbk(["netsh", "interface", "ip", "show", "dns", f"name={adapter_name}"])
    print(f"[DEBUG] netsh show dns 输出:\n{output_dns}")

    if re.search(r"DHCP 启用:\s*是", output_dns) or re.search(r"DHCP enabled:\s*Yes", output_dns, re.IGNORECASE):
        config['dhcp_dns'] = True
    else:
        config['dhcp_dns'] = False

    # 提取所有 IPv4 地址
    all_ips = re.findall(r"\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b", output_dns)
    dns_list = [ip for ip in all_ips if ip not in ("0.0.0.0", "255.255.255.255")]
    config['dns_servers'] = dns_list
    print(f"[DEBUG] DNS: DHCP={config['dhcp_dns']}, 服务器列表={config['dns_servers']}")

    return config

# ---------- 网络操作函数 ----------
def clear_extra_ips(adapter_name):
    output = run_netsh_gbk(["netsh", "interface", "ip", "show", "addresses", f"name={adapter_name}"])
    ip_pattern = re.compile(r"IP 地址:\s*([0-9.]+)")
    all_ips = ip_pattern.findall(output)
    if not all_ips:
        return
    primary_ip = all_ips[0] if all_ips else None
    for ip in all_ips:
        if ip == primary_ip:
            continue
        subprocess.run(
            ["netsh", "interface", "ip", "delete", "address", f"name={adapter_name}", f"addr={ip}"],
            capture_output=True, text=True, encoding='gbk', errors='replace'
        )

def set_dhcp(adapter_name):
    subprocess.run(
        ["netsh", "interface", "ip", "set", "address", f"name={adapter_name}", "source=dhcp"],
        capture_output=True, text=True, encoding='gbk', errors='replace'
    )
    subprocess.run(
        ["netsh", "interface", "ip", "set", "dns", f"name={adapter_name}", "source=dhcp"],
        capture_output=True, text=True, encoding='gbk', errors='replace'
    )

def set_static(adapter_name, primary_ip, subnet_mask, gateway, extra_ips=None, dns_servers=None):
    clear_extra_ips(adapter_name)

    if gateway and gateway.strip():
        cmd = ["netsh", "interface", "ip", "set", "address",
               f"name={adapter_name}", "source=static", f"addr={primary_ip}",
               f"mask={subnet_mask}", f"gateway={gateway}", "gwmetric=1"]
    else:
        cmd = ["netsh", "interface", "ip", "set", "address",
               f"name={adapter_name}", "source=static", f"addr={primary_ip}",
               f"mask={subnet_mask}", "gateway=none"]
    subprocess.run(cmd, capture_output=True, text=True, encoding='gbk', errors='replace')

    if extra_ips:
        for ip, mask in extra_ips:
            if ip and mask:
                subprocess.run(
                    ["netsh", "interface", "ip", "add", "address",
                     f"name={adapter_name}", f"addr={ip}", f"mask={mask}"],
                    capture_output=True, text=True, encoding='gbk', errors='replace'
                )

    # 设置 DNS
    if dns_servers:
        # 先恢复为 DHCP，再设置静态
        subprocess.run(
            ["netsh", "interface", "ip", "set", "dns", f"name={adapter_name}", "source=dhcp"],
            capture_output=True, text=True, encoding='gbk', errors='replace'
        )
        subprocess.run(
            ["netsh", "interface", "ip", "set", "dns", f"name={adapter_name}",
             "source=static", f"addr={dns_servers[0]}", "register=primary"],
            capture_output=True, text=True, encoding='gbk', errors='replace'
        )
        if len(dns_servers) > 1 and dns_servers[1]:
            subprocess.run(
                ["netsh", "interface", "ip", "add", "dns", f"name={adapter_name}",
                 f"addr={dns_servers[1]}", "index=2"],
                capture_output=True, text=True, encoding='gbk', errors='replace'
            )
    else:
        # 没有提供 DNS，则设为 DHCP
        subprocess.run(
            ["netsh", "interface", "ip", "set", "dns", f"name={adapter_name}", "source=dhcp"],
            capture_output=True, text=True, encoding='gbk', errors='replace'
        )

def set_dns_only(adapter_name, dns_servers):
    """
    仅修改 DNS，不改动 IP 配置（无论 IP 是 DHCP 还是静态）
    """
    if dns_servers:
        # 先恢复为 DHCP，再设置静态
        subprocess.run(
            ["netsh", "interface", "ip", "set", "dns", f"name={adapter_name}", "source=dhcp"],
            capture_output=True, text=True, encoding='gbk', errors='replace'
        )
        subprocess.run(
            ["netsh", "interface", "ip", "set", "dns", f"name={adapter_name}",
             "source=static", f"addr={dns_servers[0]}", "register=primary"],
            capture_output=True, text=True, encoding='gbk', errors='replace'
        )
        if len(dns_servers) > 1 and dns_servers[1]:
            subprocess.run(
                ["netsh", "interface", "ip", "add", "dns", f"name={adapter_name}",
                 f"addr={dns_servers[1]}", "index=2"],
                capture_output=True, text=True, encoding='gbk', errors='replace'
            )
    else:
        # 清空 DNS 设置，恢复为 DHCP
        subprocess.run(
            ["netsh", "interface", "ip", "set", "dns", f"name={adapter_name}", "source=dhcp"],
            capture_output=True, text=True, encoding='gbk', errors='replace'
        )

def set_adapter_state(adapter_name, enable):
    state = "ENABLED" if enable else "DISABLED"
    subprocess.run(
        ["netsh", "interface", "set", "interface", f"name={adapter_name}", f"admin={state}"],
        capture_output=True, text=True, encoding='gbk', errors='replace'
    )

# ---------- GUI 应用 ----------
class NetConfigApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Windows 网卡快速配置工具")
        self.root.geometry("700x750")
        self.root.resizable(True, True)

        default_font = ('Microsoft YaHei', 9)
        self.root.option_add('*Font', default_font)

        self.current_adapter = tk.StringVar()
        self.dhcp_mode = tk.BooleanVar(value=True)
        self.dns_only_mode = tk.BooleanVar(value=False)  # 仅修改 DNS 模式
        self.current_adapter_name = None
        self.refresh_after_id = None

        self.create_widgets()
        self.refresh_adapter_list()
        if self.combo_adapter['values']:
            self.combo_adapter.current(0)
            self.current_adapter.set(self.combo_adapter['values'][0])
            self.on_adapter_selected(None)

    def create_widgets(self):
        # ----- 网卡选择区域 -----
        frame_adapter = ttk.LabelFrame(self.root, text="网卡选择", padding=5)
        frame_adapter.pack(fill=tk.X, padx=10, pady=5)

        ttk.Label(frame_adapter, text="可用网卡:").grid(row=0, column=0, padx=5, pady=5, sticky=tk.W)
        self.combo_adapter = ttk.Combobox(frame_adapter, textvariable=self.current_adapter, width=40)
        self.combo_adapter.grid(row=0, column=1, padx=5, pady=5)
        self.combo_adapter.bind("<<ComboboxSelected>>", self.on_adapter_selected)

        btn_refresh = ttk.Button(frame_adapter, text="刷新列表", command=self.refresh_adapter_list)
        btn_refresh.grid(row=0, column=2, padx=5, pady=5)

        btn_enable = ttk.Button(frame_adapter, text="启用网卡", command=lambda: self.set_adapter(True))
        btn_enable.grid(row=0, column=3, padx=5, pady=5)
        btn_disable = ttk.Button(frame_adapter, text="禁用网卡", command=lambda: self.set_adapter(False))
        btn_disable.grid(row=0, column=4, padx=5, pady=5)

        # ----- 当前配置显示区域 -----
        frame_info = ttk.LabelFrame(self.root, text="当前配置", padding=5)
        frame_info.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        self.info_text = scrolledtext.ScrolledText(frame_info, height=12, width=80, wrap=tk.WORD,
                                                   font=('Consolas', 9))
        self.info_text.pack(fill=tk.BOTH, expand=True)

        # ----- 配置修改区域 -----
        frame_modify = ttk.LabelFrame(self.root, text="修改配置", padding=5)
        frame_modify.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # IP 模式选择
        rb_dhcp = ttk.Radiobutton(frame_modify, text="DHCP (自动获取IP)", variable=self.dhcp_mode, value=True,
                                  command=self.on_mode_change)
        rb_dhcp.grid(row=0, column=0, padx=5, pady=5, sticky=tk.W)
        rb_static = ttk.Radiobutton(frame_modify, text="静态IP", variable=self.dhcp_mode, value=False,
                                    command=self.on_mode_change)
        rb_static.grid(row=0, column=1, padx=5, pady=5, sticky=tk.W)

        # 静态 IP 参数框架（初始隐藏）
        self.static_frame = ttk.Frame(frame_modify)
        self.static_frame.grid(row=1, column=0, columnspan=3, sticky=tk.W+tk.E, padx=5, pady=5)

        ttk.Label(self.static_frame, text="主IP地址:").grid(row=0, column=0, padx=5, pady=2, sticky=tk.W)
        self.entry_ip = ttk.Entry(self.static_frame, width=18)
        self.entry_ip.grid(row=0, column=1, padx=5, pady=2)

        ttk.Label(self.static_frame, text="子网掩码:").grid(row=0, column=2, padx=5, pady=2, sticky=tk.W)
        self.entry_mask = ttk.Entry(self.static_frame, width=18)
        self.entry_mask.grid(row=0, column=3, padx=5, pady=2)

        ttk.Label(self.static_frame, text="默认网关:").grid(row=0, column=4, padx=5, pady=2, sticky=tk.W)
        self.entry_gateway = ttk.Entry(self.static_frame, width=18)
        self.entry_gateway.grid(row=0, column=5, padx=5, pady=2)

        ttk.Label(self.static_frame, text="额外IP (每行一个, 格式: IP/掩码 或 IP 掩码):").grid(
            row=1, column=0, columnspan=6, padx=5, pady=2, sticky=tk.W)
        self.extra_ips_text = scrolledtext.ScrolledText(self.static_frame, height=4, width=70)
        self.extra_ips_text.grid(row=2, column=0, columnspan=6, padx=5, pady=2)

        # ----- DNS 配置区域（始终可见）-----
        dns_frame = ttk.LabelFrame(frame_modify, text="DNS 设置", padding=5)
        dns_frame.grid(row=2, column=0, columnspan=3, sticky=tk.W+tk.E, padx=5, pady=10)

        # 仅修改 DNS 复选框
        self.dns_only_check = ttk.Checkbutton(dns_frame, text="仅修改 DNS（不改变 IP 设置）",
                                              variable=self.dns_only_mode)
        self.dns_only_check.grid(row=0, column=0, columnspan=2, padx=5, pady=5, sticky=tk.W)

        ttk.Label(dns_frame, text="首选DNS:").grid(row=1, column=0, padx=5, pady=5, sticky=tk.W)
        self.entry_dns1 = ttk.Entry(dns_frame, width=20)
        self.entry_dns1.grid(row=1, column=1, padx=5, pady=5, sticky=tk.W)

        ttk.Label(dns_frame, text="备用DNS:").grid(row=1, column=2, padx=5, pady=5, sticky=tk.W)
        self.entry_dns2 = ttk.Entry(dns_frame, width=20)
        self.entry_dns2.grid(row=1, column=3, padx=5, pady=5, sticky=tk.W)

        # 应用按钮
        btn_apply = ttk.Button(frame_modify, text="应用配置", command=self.apply_config)
        btn_apply.grid(row=3, column=0, columnspan=3, pady=10)

        # 状态栏
        self.status_var = tk.StringVar()
        self.status_var.set("就绪")
        status_bar = ttk.Label(self.root, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W)
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)

        self.on_mode_change()

    def refresh_adapter_list(self):
        previous_name = self.current_adapter_name
        self.adapters = get_adapters()
        names = [f"{name} ({state})" for name, state in self.adapters]
        self.combo_adapter['values'] = names
        if previous_name:
            new_selection = None
            for item in names:
                if item.startswith(previous_name + " ("):
                    new_selection = item
                    break
            if new_selection:
                self.current_adapter.set(new_selection)
                self.combo_adapter.current(names.index(new_selection))
                self.on_adapter_selected(None)
            elif names:
                self.combo_adapter.current(0)
                self.current_adapter.set(names[0])
                self.on_adapter_selected(None)
        elif names:
            self.combo_adapter.current(0)
            self.current_adapter.set(names[0])
            self.on_adapter_selected(None)
        if not names:
            self.info_text.delete(1.0, tk.END)
            self.info_text.insert(tk.END, "未找到可用的物理网卡！\n请检查网络适配器设置。")

    def on_adapter_selected(self, event):
        if not self.current_adapter.get():
            return
        selected = self.current_adapter.get()
        name = selected.split(" (")[0]
        self.current_adapter_name = name
        self.refresh_current_config()

    def refresh_current_config(self):
        if not self.current_adapter_name:
            return
        config = get_adapter_config(self.current_adapter_name)
        self.info_text.delete(1.0, tk.END)

        info = f"网卡: {self.current_adapter_name}\n"
        info += f"网卡状态: {'已启用' if config['enabled'] else '已禁用'}\n"
        info += f"IP模式: {'DHCP (自动获取)' if config['dhcp_enabled'] else '静态IP'}\n"

        if config['ip_list']:
            info += "当前IP地址列表:\n"
            for ip, mask in config['ip_list']:
                info += f"  {ip} / {mask}\n"
        else:
            if config['dhcp_enabled']:
                info += "IP地址: 未获取到有效IP (可能未连接或DHCP失败)\n"
            else:
                info += "IP地址: 无\n"

        info += f"默认网关: {config['gateway'] or '无'}\n"
        info += f"DNS模式: {'DHCP' if config['dhcp_dns'] else '手动'}\n"
        if config['dns_servers']:
            info += "当前DNS服务器:\n"
            for dns in config['dns_servers']:
                info += f"  {dns}\n"
        else:
            info += "DNS: 无\n"

        self.info_text.insert(tk.END, info)

        # 如果是静态模式且有IP，将主IP和掩码填入编辑框
        if not config['dhcp_enabled'] and config['ip_list']:
            primary_ip, primary_mask = config['ip_list'][0]
            self.entry_ip.delete(0, tk.END)
            self.entry_ip.insert(0, primary_ip)
            self.entry_mask.delete(0, tk.END)
            self.entry_mask.insert(0, primary_mask)
            self.entry_gateway.delete(0, tk.END)
            if config['gateway']:
                self.entry_gateway.insert(0, config['gateway'])
        else:
            # DHCP 模式，清空静态 IP 编辑框（避免干扰）
            self.entry_ip.delete(0, tk.END)
            self.entry_mask.delete(0, tk.END)
            self.entry_gateway.delete(0, tk.END)
            self.extra_ips_text.delete(1.0, tk.END)

        # 填充 DNS 编辑框（方便修改）
        if config['dns_servers']:
            self.entry_dns1.delete(0, tk.END)
            self.entry_dns1.insert(0, config['dns_servers'][0])
            if len(config['dns_servers']) > 1:
                self.entry_dns2.delete(0, tk.END)
                self.entry_dns2.insert(0, config['dns_servers'][1])
        else:
            self.entry_dns1.delete(0, tk.END)
            self.entry_dns2.delete(0, tk.END)

        # 同步单选按钮
        self.dhcp_mode.set(config['dhcp_enabled'])
        self.on_mode_change()

    def on_mode_change(self):
        if self.dhcp_mode.get():
            self.static_frame.grid_remove()
        else:
            self.static_frame.grid()

    def set_adapter(self, enable):
        if not self.current_adapter_name:
            messagebox.showwarning("警告", "请先选择一个网卡")
            return
        try:
            set_adapter_state(self.current_adapter_name, enable)
            self.status_var.set(f"已{'启用' if enable else '禁用'}网卡 {self.current_adapter_name}")
            self.root.after(500, self.refresh_adapter_list)
        except Exception as e:
            messagebox.showerror("错误", f"操作失败: {str(e)}")

    def apply_config(self):
        if not self.current_adapter_name:
            messagebox.showwarning("警告", "请先选择一个网卡")
            return

        # 取消之前的自动刷新
        if self.refresh_after_id:
            self.root.after_cancel(self.refresh_after_id)
            self.refresh_after_id = None

        # 解析 DNS 输入
        dns_list = []
        dns1 = self.entry_dns1.get().strip()
        if dns1:
            dns_list.append(dns1)
        dns2 = self.entry_dns2.get().strip()
        if dns2:
            dns_list.append(dns2)

        # 如果勾选了“仅修改 DNS”
        if self.dns_only_mode.get():
            try:
                set_dns_only(self.current_adapter_name, dns_list)
                self.status_var.set(f"已为 {self.current_adapter_name} 单独修改 DNS")
                self.auto_refresh(5, 2000)
                messagebox.showinfo("成功", "DNS 已更新")
            except Exception as e:
                messagebox.showerror("错误", f"修改 DNS 失败: {str(e)}")
            return

        # 否则，完整修改 IP 和 DNS
        if self.dhcp_mode.get():
            try:
                set_dhcp(self.current_adapter_name)
                self.status_var.set(f"已为 {self.current_adapter_name} 启用 DHCP (IP和DNS)")
                self.auto_refresh(5, 2000)
                messagebox.showinfo("成功", "已切换到 DHCP 模式")
            except Exception as e:
                messagebox.showerror("错误", f"设置DHCP失败: {str(e)}")
        else:
            ip = self.entry_ip.get().strip()
            mask = self.entry_mask.get().strip()
            gateway = self.entry_gateway.get().strip()
            if not ip or not mask:
                messagebox.showerror("参数错误", "主IP地址和子网掩码不能为空")
                return

            # 解析额外 IP
            extra_ips = []
            extra_text = self.extra_ips_text.get(1.0, tk.END).strip()
            if extra_text:
                for line in extra_text.splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    if '/' in line:
                        ip_part, mask_part = line.split('/', 1)
                        if mask_part.isdigit():
                            cidr = int(mask_part)
                            mask_part = '.'.join(str((0xffffffff << (32 - cidr) >> i) & 0xff) for i in [24, 16, 8, 0])
                        extra_ips.append((ip_part.strip(), mask_part))
                    elif ' ' in line:
                        parts = line.split()
                        if len(parts) >= 2:
                            extra_ips.append((parts[0].strip(), parts[1].strip()))
                    else:
                        messagebox.showerror("格式错误", f"额外IP行格式错误: {line}\n正确示例: 192.168.1.10/24 或 192.168.1.10 255.255.255.0")
                        return

            try:
                set_static(self.current_adapter_name, ip, mask, gateway if gateway else None,
                           extra_ips, dns_list)
                self.status_var.set(f"已为 {self.current_adapter_name} 应用静态配置")
                self.auto_refresh(5, 2000)
                messagebox.showinfo("成功", "静态IP配置已应用")
            except Exception as e:
                messagebox.showerror("错误", f"设置静态IP失败: {str(e)}")

    def auto_refresh(self, times, interval_ms):
        """自动刷新当前配置，次数递减，间隔毫秒"""
        if times <= 0:
            self.status_var.set("就绪")
            return
        self.refresh_current_config()
        self.status_var.set(f"正在刷新配置... 剩余 {times-1} 次")
        self.refresh_after_id = self.root.after(interval_ms, lambda: self.auto_refresh(times-1, interval_ms))

if __name__ == "__main__":
    root = tk.Tk()
    app = NetConfigApp(root)
    root.mainloop()