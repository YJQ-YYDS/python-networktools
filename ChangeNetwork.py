#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Windows 网卡快速配置工具（最终版：掩码计算独立菜单）
功能：
- 查看所有网卡及当前配置，关键信息高亮显示
- 切换 DHCP / 静态IP（完整配置）
- 单独修改 DNS（不影响 IP）
- 添加多个额外IP
- 启用/禁用网卡
- 预配置管理：保存/加载/删除/重命名/查看/修改配置文件
- 修改后自动刷新 5 次，每次间隔 2 秒
- 应用配置前可选“禁用再启用”网卡，确保配置生效
- 掩码计算工具：支持 CIDR 与掩码互转，并提供复制纯数值按钮（菜单栏独立项）
- 主区域可上下左右滚动，适应小屏幕
- 控制台输出每条 netsh 命令及其返回值，便于调试
"""

import subprocess
import re
import sys
import os
import ctypes
import json
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, simpledialog, Toplevel

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

# ---------- 命令行输出辅助 ----------
def print_command(cmd_args, stdout=None, stderr=None, returncode=None):
    if isinstance(cmd_args, list):
        cmd_str = ' '.join(cmd_args)
    else:
        cmd_str = cmd_args
    print(f"\n[CMD] {cmd_str}")
    if stdout:
        print(f"[STDOUT]\n{stdout.rstrip()}")
    if stderr:
        print(f"[STDERR]\n{stderr.rstrip()}")
    if returncode is not None:
        print(f"[RETURNCODE] {returncode}")

# ---------- 配置文件路径 ----------
def get_profiles_base_dir():
    script_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
    profiles_dir = os.path.join(script_dir, "profiles")
    if not os.path.exists(profiles_dir):
        os.makedirs(profiles_dir)
    return profiles_dir

def get_netcard_profile_dir(netcard_name):
    base = get_profiles_base_dir()
    safe_name = re.sub(r'[\\/*?:"<>|]', '_', netcard_name)
    netcard_dir = os.path.join(base, safe_name)
    if not os.path.exists(netcard_dir):
        os.makedirs(netcard_dir)
    return netcard_dir

def list_profiles(netcard_name):
    dir_path = get_netcard_profile_dir(netcard_name)
    files = [f[:-5] for f in os.listdir(dir_path) if f.endswith('.json')]
    return files

def save_profile(netcard_name, profile_name, config_data):
    dir_path = get_netcard_profile_dir(netcard_name)
    file_path = os.path.join(dir_path, f"{profile_name}.json")
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(config_data, f, ensure_ascii=False, indent=2)
    return file_path

def load_profile(netcard_name, profile_name):
    dir_path = get_netcard_profile_dir(netcard_name)
    file_path = os.path.join(dir_path, f"{profile_name}.json")
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def delete_profile(netcard_name, profile_name):
    dir_path = get_netcard_profile_dir(netcard_name)
    file_path = os.path.join(dir_path, f"{profile_name}.json")
    if os.path.exists(file_path):
        os.remove(file_path)

def rename_profile(netcard_name, old_name, new_name):
    dir_path = get_netcard_profile_dir(netcard_name)
    old_path = os.path.join(dir_path, f"{old_name}.json")
    new_path = os.path.join(dir_path, f"{new_name}.json")
    if not os.path.exists(old_path):
        raise FileNotFoundError(f"配置文件 {old_name} 不存在")
    if os.path.exists(new_path):
        raise FileExistsError(f"配置 {new_name} 已存在")
    os.rename(old_path, new_path)

# ---------- 掩码计算工具 ----------
def cidr_to_mask(cidr):
    try:
        bits = int(cidr)
        if bits < 0 or bits > 32:
            return None
        mask = (0xffffffff << (32 - bits)) & 0xffffffff
        return f"{(mask >> 24) & 0xff}.{(mask >> 16) & 0xff}.{(mask >> 8) & 0xff}.{mask & 0xff}"
    except:
        return None

def mask_to_cidr(mask):
    try:
        parts = mask.split('.')
        if len(parts) != 4:
            return None
        mask_int = 0
        for p in parts:
            mask_int = (mask_int << 8) | int(p)
        if mask_int == 0:
            return 0
        count = 0
        while mask_int & 0x80000000:
            count += 1
            mask_int <<= 1
        return count
    except:
        return None

def show_mask_calc():
    win = Toplevel()
    win.title("掩码计算工具")
    win.geometry("450x230")
    win.resizable(False, False)
    ttk.Label(win, text="输入 CIDR（如 24）或子网掩码（如 255.255.255.0）：").pack(pady=10)
    entry = ttk.Entry(win, width=30)
    entry.pack(pady=5)
    result_var = tk.StringVar()
    result_var.set("结果将显示在此处")
    label_result = ttk.Label(win, textvariable=result_var, font=('Microsoft YaHei', 10, 'bold'), foreground='blue')
    label_result.pack(pady=5)
    
    pure_value = tk.StringVar()
    pure_value.set("")
    
    def calculate():
        val = entry.get().strip()
        if not val:
            result_var.set("请输入内容")
            pure_value.set("")
            return
        if val.isdigit():
            cidr = int(val)
            mask = cidr_to_mask(cidr)
            if mask:
                result_var.set(f"/{cidr}  →  子网掩码：{mask}")
                pure_value.set(mask)
            else:
                result_var.set("无效的 CIDR 前缀（0-32）")
                pure_value.set("")
        elif val.startswith('/') and val[1:].isdigit():
            cidr = int(val[1:])
            mask = cidr_to_mask(cidr)
            if mask:
                result_var.set(f"{val}  →  子网掩码：{mask}")
                pure_value.set(mask)
            else:
                result_var.set("无效的 CIDR 前缀（0-32）")
                pure_value.set("")
        else:
            cidr = mask_to_cidr(val)
            if cidr is not None:
                result_var.set(f"{val}  →  /{cidr}")
                pure_value.set(f"/{cidr}")
            else:
                result_var.set("无法识别，请输入合法的 CIDR 或子网掩码")
                pure_value.set("")
    
    def copy_pure():
        to_copy = pure_value.get()
        if to_copy:
            win.clipboard_clear()
            win.clipboard_append(to_copy)
            messagebox.showinfo("复制成功", f"已复制：{to_copy}")
        else:
            messagebox.showwarning("无内容", "请先进行有效转换")
    
    btn_calc = ttk.Button(win, text="转换", command=calculate)
    btn_calc.pack(pady=5)
    btn_copy = ttk.Button(win, text="复制结果（仅数值）", command=copy_pure)
    btn_copy.pack(pady=5)

# ---------- netsh 执行辅助 ----------
def run_netsh_utf8(args):
    cmd = f"chcp 65001 > nul && netsh {' '.join(args)}"
    print_command(cmd)
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=False, encoding=None)
        stdout = result.stdout.decode('utf-8', errors='replace')
        stderr = result.stderr.decode('utf-8', errors='replace') if result.stderr else ""
        print_command(cmd, stdout=stdout, stderr=stderr, returncode=result.returncode)
        return stdout
    except Exception as e:
        print(f"[EXCEPTION] {e}")
        return ""

def run_netsh_gbk(args):
    print_command(args)
    try:
        result = subprocess.run(args, capture_output=True, text=True, encoding='gbk', errors='replace')
        print_command(args, stdout=result.stdout, stderr=result.stderr, returncode=result.returncode)
        return result.stdout if result.stdout is not None else ""
    except Exception as e:
        print(f"[EXCEPTION] {e}")
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

    output_state = run_netsh_utf8(["interface", "show", "interface", f"name={adapter_name}"])
    if "已启用" in output_state or "Enabled" in output_state:
        config['enabled'] = True

    output = run_netsh_gbk(["netsh", "interface", "ip", "show", "config", f"name={adapter_name}"])
    if re.search(r"DHCP 启用:\s*是", output) or re.search(r"DHCP enabled:\s*Yes", output, re.IGNORECASE):
        config['dhcp_enabled'] = True
    else:
        config['dhcp_enabled'] = False

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

    output_dns = run_netsh_gbk(["netsh", "interface", "ip", "show", "dns", f"name={adapter_name}"])
    if re.search(r"DHCP 启用:\s*是", output_dns) or re.search(r"DHCP enabled:\s*Yes", output_dns, re.IGNORECASE):
        config['dhcp_dns'] = True
    else:
        config['dhcp_dns'] = False

    all_ips = re.findall(r"\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b", output_dns)
    dns_list = [ip for ip in all_ips if ip not in ("0.0.0.0", "255.255.255.255")]
    config['dns_servers'] = dns_list
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
        run_netsh_gbk(["netsh", "interface", "ip", "delete", "address", f"name={adapter_name}", f"addr={ip}"])

def set_dhcp(adapter_name):
    run_netsh_gbk(["netsh", "interface", "ip", "set", "address", f"name={adapter_name}", "source=dhcp"])
    run_netsh_gbk(["netsh", "interface", "ip", "set", "dns", f"name={adapter_name}", "source=dhcp"])

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
    run_netsh_gbk(cmd)
    if extra_ips:
        for ip, mask in extra_ips:
            if ip and mask:
                run_netsh_gbk(["netsh", "interface", "ip", "add", "address",
                               f"name={adapter_name}", f"addr={ip}", f"mask={mask}"])
    if dns_servers:
        run_netsh_gbk(["netsh", "interface", "ip", "set", "dns", f"name={adapter_name}", "source=dhcp"])
        run_netsh_gbk(["netsh", "interface", "ip", "set", "dns", f"name={adapter_name}",
                       "source=static", f"addr={dns_servers[0]}", "register=primary"])
        if len(dns_servers) > 1 and dns_servers[1]:
            run_netsh_gbk(["netsh", "interface", "ip", "add", "dns", f"name={adapter_name}",
                           f"addr={dns_servers[1]}", "index=2"])
    else:
        run_netsh_gbk(["netsh", "interface", "ip", "set", "dns", f"name={adapter_name}", "source=dhcp"])

def set_dns_only(adapter_name, dns_servers):
    if dns_servers:
        run_netsh_gbk(["netsh", "interface", "ip", "set", "dns", f"name={adapter_name}", "source=dhcp"])
        run_netsh_gbk(["netsh", "interface", "ip", "set", "dns", f"name={adapter_name}",
                       "source=static", f"addr={dns_servers[0]}", "register=primary"])
        if len(dns_servers) > 1 and dns_servers[1]:
            run_netsh_gbk(["netsh", "interface", "ip", "add", "dns", f"name={adapter_name}",
                           f"addr={dns_servers[1]}", "index=2"])
    else:
        run_netsh_gbk(["netsh", "interface", "ip", "set", "dns", f"name={adapter_name}", "source=dhcp"])

def set_adapter_state(adapter_name, enable):
    state = "ENABLED" if enable else "DISABLED"
    run_netsh_gbk(["netsh", "interface", "set", "interface", f"name={adapter_name}", f"admin={state}"])

# ---------- GUI 应用 ----------
class NetConfigApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Windows 网卡快速配置工具")
        self.root.geometry("900x700")
        self.root.minsize(700, 500)
        self.root.resizable(True, True)

        default_font = ('Microsoft YaHei', 9)
        self.root.option_add('*Font', default_font)

        self.create_menu()

        # 可滚动 Canvas
        self.canvas = tk.Canvas(self.root, borderwidth=0)
        self.h_scrollbar = ttk.Scrollbar(self.root, orient="horizontal", command=self.canvas.xview)
        self.v_scrollbar = ttk.Scrollbar(self.root, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(xscrollcommand=self.h_scrollbar.set, yscrollcommand=self.v_scrollbar.set)

        self.scrollable_frame = ttk.Frame(self.canvas)
        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )
        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")

        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.v_scrollbar.grid(row=0, column=1, sticky="ns")
        self.h_scrollbar.grid(row=1, column=0, sticky="ew")
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(0, weight=1)

        def _on_mousewheel(event):
            self.canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        self.canvas.bind_all("<MouseWheel>", _on_mousewheel)

        def _on_shift_mousewheel(event):
            self.canvas.xview_scroll(int(-1*(event.delta/120)), "units")
        self.canvas.bind_all("<Shift-MouseWheel>", _on_shift_mousewheel)

        self.current_adapter = tk.StringVar()
        self.dhcp_mode = tk.BooleanVar(value=True)
        self.dns_only_mode = tk.BooleanVar(value=False)
        self.reset_before_apply = tk.BooleanVar(value=True)
        self.current_adapter_name = None
        self.refresh_after_id = None
        self.pending_apply = None

        self.create_widgets()
        self.refresh_adapter_list()
        if self.combo_adapter['values']:
            self.combo_adapter.current(0)
            self.current_adapter.set(self.combo_adapter['values'][0])
            self.on_adapter_selected(None)

    def create_menu(self):
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)

        # 配置菜单
        config_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="配置", menu=config_menu)
        config_menu.add_command(label="保存当前配置为模板", command=self.save_current_as_profile)
        config_menu.add_command(label="加载模板并自动应用", command=self.load_profile_and_apply)
        config_menu.add_separator()
        config_menu.add_command(label="管理配置文件（删除/重命名/查看/修改）", command=self.manage_profiles)
        config_menu.add_separator()
        config_menu.add_command(label="刷新网卡列表", command=self.refresh_adapter_list)

        # 掩码计算独立菜单项（直接放在配置和帮助之间）
        menubar.add_command(label="掩码计算", command=show_mask_calc)

        # 帮助菜单
        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="帮助", menu=help_menu)
        help_menu.add_command(label="使用说明", command=self.show_help)

    def show_help(self):
        msg = """使用说明：
1. 选择网卡后，可查看当前配置（关键信息高亮显示）。
2. 修改配置：
   - 勾选“仅修改DNS”可单独修改DNS，不影响IP。
   - 取消勾选则可完整修改IP和DNS。
3. 预配置管理：
   - 保存当前配置为模板。
   - 加载模板并自动应用。
   - 管理配置文件：支持删除、重命名、查看/修改内容。
4. 应用前重置网卡：可选，先禁用再启用再应用配置。
5. 掩码计算工具：支持CIDR与掩码互转，并支持复制纯数值结果（点击“复制结果”按钮）。
6. 所有执行的netsh命令均显示在命令行窗口。
"""
        messagebox.showinfo("帮助", msg)

    def save_current_as_profile(self):
        if not self.current_adapter_name:
            messagebox.showwarning("警告", "请先选择一个网卡")
            return
        name = simpledialog.askstring("保存配置", "请输入配置名称（例如：办公环境、家里网络）:")
        if not name:
            return
        config_data = {
            'dhcp_mode': self.dhcp_mode.get(),
            'primary_ip': self.entry_ip.get().strip(),
            'subnet_mask': self.entry_mask.get().strip(),
            'gateway': self.entry_gateway.get().strip(),
            'extra_ips': self.extra_ips_text.get(1.0, tk.END).strip(),
            'dns1': self.entry_dns1.get().strip(),
            'dns2': self.entry_dns2.get().strip()
        }
        try:
            save_profile(self.current_adapter_name, name, config_data)
            messagebox.showinfo("成功", f"配置已保存到 {self.current_adapter_name}/{name}.json")
        except Exception as e:
            messagebox.showerror("错误", f"保存失败: {str(e)}")

    def load_profile_and_apply(self):
        if not self.current_adapter_name:
            messagebox.showwarning("警告", "请先选择一个网卡")
            return
        profiles = list_profiles(self.current_adapter_name)
        if not profiles:
            messagebox.showinfo("提示", "当前网卡没有保存任何配置文件。")
            return
        win = Toplevel(self.root)
        win.title("加载配置")
        win.geometry("300x150")
        win.resizable(False, False)
        ttk.Label(win, text=f"网卡：{self.current_adapter_name}").pack(pady=5)
        ttk.Label(win, text="请选择要加载的配置：").pack(pady=5)
        combo = ttk.Combobox(win, values=profiles, state="readonly", width=30)
        combo.pack(pady=5)
        combo.current(0)

        def do_load():
            selected = combo.get()
            if not selected:
                messagebox.showerror("错误", "请选择一个配置")
                return
            try:
                cfg = load_profile(self.current_adapter_name, selected)
                self.dhcp_mode.set(cfg.get('dhcp_mode', True))
                self.entry_ip.delete(0, tk.END)
                self.entry_ip.insert(0, cfg.get('primary_ip', ''))
                self.entry_mask.delete(0, tk.END)
                self.entry_mask.insert(0, cfg.get('subnet_mask', ''))
                self.entry_gateway.delete(0, tk.END)
                self.entry_gateway.insert(0, cfg.get('gateway', ''))
                self.extra_ips_text.delete(1.0, tk.END)
                self.extra_ips_text.insert(1.0, cfg.get('extra_ips', ''))
                self.entry_dns1.delete(0, tk.END)
                self.entry_dns1.insert(0, cfg.get('dns1', ''))
                self.entry_dns2.delete(0, tk.END)
                self.entry_dns2.insert(0, cfg.get('dns2', ''))
                self.on_mode_change()
                win.destroy()
                self.apply_config()
            except Exception as e:
                messagebox.showerror("错误", f"加载或应用失败: {str(e)}")
                win.destroy()
        btn = ttk.Button(win, text="确定并应用", command=do_load)
        btn.pack(pady=10)

    def manage_profiles(self):
        if not self.current_adapter_name:
            messagebox.showwarning("警告", "请先选择一个网卡")
            return
        profiles = list_profiles(self.current_adapter_name)
        if not profiles:
            messagebox.showinfo("提示", "当前网卡没有配置文件。")
            return
        win = Toplevel(self.root)
        win.title("管理配置文件")
        win.geometry("350x350")
        win.resizable(False, False)
        ttk.Label(win, text=f"网卡：{self.current_adapter_name}").pack(pady=5)
        listbox = tk.Listbox(win, height=8)
        listbox.pack(pady=5, padx=10, fill=tk.BOTH, expand=True)
        for p in profiles:
            listbox.insert(tk.END, p)

        def delete_selected():
            sel = listbox.curselection()
            if not sel:
                messagebox.showinfo("提示", "请先选择一个配置")
                return
            name = listbox.get(sel[0])
            if messagebox.askyesno("确认删除", f"确定要删除配置“{name}”吗？"):
                delete_profile(self.current_adapter_name, name)
                listbox.delete(sel[0])
                messagebox.showinfo("成功", "已删除")

        def rename_selected():
            sel = listbox.curselection()
            if not sel:
                messagebox.showinfo("提示", "请先选择一个配置")
                return
            old_name = listbox.get(sel[0])
            new_name = simpledialog.askstring("重命名", f"将“{old_name}”重命名为：")
            if not new_name or new_name == old_name:
                return
            if new_name in profiles:
                messagebox.showerror("错误", "配置名称已存在")
                return
            try:
                rename_profile(self.current_adapter_name, old_name, new_name)
                listbox.delete(sel[0])
                listbox.insert(sel[0], new_name)
                messagebox.showinfo("成功", "已重命名")
            except Exception as e:
                messagebox.showerror("错误", f"重命名失败: {str(e)}")

        def view_edit_selected():
            sel = listbox.curselection()
            if not sel:
                messagebox.showinfo("提示", "请先选择一个配置")
                return
            name = listbox.get(sel[0])
            try:
                cfg = load_profile(self.current_adapter_name, name)
            except Exception as e:
                messagebox.showerror("错误", f"读取配置文件失败: {str(e)}")
                return
            edit_win = Toplevel(win)
            edit_win.title(f"查看/修改配置 - {name}")
            edit_win.geometry("500x450")
            edit_win.resizable(True, True)
            ttk.Label(edit_win, text=f"配置文件：{name}.json", font=('Microsoft YaHei', 10, 'bold')).pack(pady=5)
            text_area = scrolledtext.ScrolledText(edit_win, wrap=tk.WORD, width=60, height=20, font=('Consolas', 9))
            text_area.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)
            text_area.insert(tk.END, json.dumps(cfg, ensure_ascii=False, indent=2))

            def save_changes():
                try:
                    new_content = text_area.get(1.0, tk.END).strip()
                    new_cfg = json.loads(new_content)
                    save_profile(self.current_adapter_name, name, new_cfg)
                    messagebox.showinfo("成功", "配置已更新")
                    edit_win.destroy()
                    if messagebox.askyesno("加载到界面", "是否将修改后的配置立即加载到主界面并应用？"):
                        self.dhcp_mode.set(new_cfg.get('dhcp_mode', True))
                        self.entry_ip.delete(0, tk.END)
                        self.entry_ip.insert(0, new_cfg.get('primary_ip', ''))
                        self.entry_mask.delete(0, tk.END)
                        self.entry_mask.insert(0, new_cfg.get('subnet_mask', ''))
                        self.entry_gateway.delete(0, tk.END)
                        self.entry_gateway.insert(0, new_cfg.get('gateway', ''))
                        self.extra_ips_text.delete(1.0, tk.END)
                        self.extra_ips_text.insert(1.0, new_cfg.get('extra_ips', ''))
                        self.entry_dns1.delete(0, tk.END)
                        self.entry_dns1.insert(0, new_cfg.get('dns1', ''))
                        self.entry_dns2.delete(0, tk.END)
                        self.entry_dns2.insert(0, new_cfg.get('dns2', ''))
                        self.on_mode_change()
                        self.apply_config()
                except json.JSONDecodeError as e:
                    messagebox.showerror("格式错误", f"无效的 JSON 格式：{str(e)}")
                except Exception as e:
                    messagebox.showerror("错误", f"保存失败: {str(e)}")
            btn_save = ttk.Button(edit_win, text="保存修改", command=save_changes)
            btn_save.pack(pady=5)

        btn_delete = ttk.Button(win, text="删除所选配置", command=delete_selected)
        btn_delete.pack(pady=5)
        btn_rename = ttk.Button(win, text="重命名所选配置", command=rename_selected)
        btn_rename.pack(pady=5)
        btn_view = ttk.Button(win, text="查看/修改所选配置", command=view_edit_selected)
        btn_view.pack(pady=5)

    def create_widgets(self):
        main_frame = self.scrollable_frame

        frame_adapter = ttk.LabelFrame(main_frame, text="网卡选择", padding=5)
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

        frame_info = ttk.LabelFrame(main_frame, text="当前配置", padding=5)
        frame_info.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        self.info_text = scrolledtext.ScrolledText(frame_info, height=12, width=80, wrap=tk.WORD, font=('Consolas', 9))
        self.info_text.pack(fill=tk.BOTH, expand=True)
        self.info_text.tag_config("highlight", foreground="blue", font=('Consolas', 9, 'bold'))

        frame_modify = ttk.LabelFrame(main_frame, text="修改配置", padding=5)
        frame_modify.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        rb_dhcp = ttk.Radiobutton(frame_modify, text="DHCP (自动获取IP)", variable=self.dhcp_mode, value=True, command=self.on_mode_change)
        rb_dhcp.grid(row=0, column=0, padx=5, pady=5, sticky=tk.W)
        rb_static = ttk.Radiobutton(frame_modify, text="静态IP", variable=self.dhcp_mode, value=False, command=self.on_mode_change)
        rb_static.grid(row=0, column=1, padx=5, pady=5, sticky=tk.W)
        reset_check = ttk.Checkbutton(frame_modify, text="应用前重置网卡（禁用再启用）", variable=self.reset_before_apply)
        reset_check.grid(row=0, column=2, padx=5, pady=5, sticky=tk.W)

        self.static_frame = ttk.Frame(frame_modify)
        self.static_frame.grid(row=1, column=0, columnspan=4, sticky=tk.W+tk.E, padx=5, pady=5)
        ttk.Label(self.static_frame, text="主IP地址:").grid(row=0, column=0, padx=5, pady=2, sticky=tk.W)
        self.entry_ip = ttk.Entry(self.static_frame, width=18)
        self.entry_ip.grid(row=0, column=1, padx=5, pady=2)
        ttk.Label(self.static_frame, text="子网掩码:").grid(row=0, column=2, padx=5, pady=2, sticky=tk.W)
        self.entry_mask = ttk.Entry(self.static_frame, width=18)
        self.entry_mask.grid(row=0, column=3, padx=5, pady=2)
        ttk.Label(self.static_frame, text="默认网关:").grid(row=0, column=4, padx=5, pady=2, sticky=tk.W)
        self.entry_gateway = ttk.Entry(self.static_frame, width=18)
        self.entry_gateway.grid(row=0, column=5, padx=5, pady=2)
        ttk.Label(self.static_frame, text="额外IP (每行一个, 格式: IP/掩码 或 IP 掩码):").grid(row=1, column=0, columnspan=6, padx=5, pady=2, sticky=tk.W)
        self.extra_ips_text = scrolledtext.ScrolledText(self.static_frame, height=4, width=70)
        self.extra_ips_text.grid(row=2, column=0, columnspan=6, padx=5, pady=2)

        dns_frame = ttk.LabelFrame(frame_modify, text="DNS 设置", padding=5)
        dns_frame.grid(row=2, column=0, columnspan=4, sticky=tk.W+tk.E, padx=5, pady=10)
        self.dns_only_check = ttk.Checkbutton(dns_frame, text="仅修改 DNS（不改变 IP 设置）", variable=self.dns_only_mode)
        self.dns_only_check.grid(row=0, column=0, columnspan=2, padx=5, pady=5, sticky=tk.W)
        ttk.Label(dns_frame, text="首选DNS:").grid(row=1, column=0, padx=5, pady=5, sticky=tk.W)
        self.entry_dns1 = ttk.Entry(dns_frame, width=20)
        self.entry_dns1.grid(row=1, column=1, padx=5, pady=5, sticky=tk.W)
        ttk.Label(dns_frame, text="备用DNS:").grid(row=1, column=2, padx=5, pady=5, sticky=tk.W)
        self.entry_dns2 = ttk.Entry(dns_frame, width=20)
        self.entry_dns2.grid(row=1, column=3, padx=5, pady=5, sticky=tk.W)

        btn_apply = ttk.Button(frame_modify, text="应用配置", command=self.apply_config)
        btn_apply.grid(row=3, column=0, columnspan=4, pady=10)

        self.status_var = tk.StringVar()
        self.status_var.set("就绪")
        status_bar = ttk.Label(main_frame, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W)
        status_bar.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=5)

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
        lines = []
        lines.append(("网卡: ", None))
        lines.append((self.current_adapter_name, "highlight"))
        lines.append(("\n", None))
        lines.append(("网卡状态: ", None))
        state = "已启用" if config['enabled'] else "已禁用"
        lines.append((state, "highlight"))
        lines.append(("\n", None))
        lines.append(("IP模式: ", None))
        ip_mode = "DHCP (自动获取)" if config['dhcp_enabled'] else "静态IP"
        lines.append((ip_mode, "highlight"))
        lines.append(("\n", None))
        if config['ip_list']:
            lines.append(("当前IP地址列表:\n", None))
            for ip, mask in config['ip_list']:
                lines.append((f"  {ip} / {mask}\n", "highlight"))
        else:
            if config['dhcp_enabled']:
                lines.append(("IP地址: 未获取到有效IP (可能未连接或DHCP失败)\n", "highlight"))
            else:
                lines.append(("IP地址: 无\n", "highlight"))
        lines.append(("默认网关: ", None))
        gw = config['gateway'] or "无"
        lines.append((gw, "highlight"))
        lines.append(("\n", None))
        lines.append(("DNS模式: ", None))
        dns_mode = "DHCP" if config['dhcp_dns'] else "手动"
        lines.append((dns_mode, "highlight"))
        lines.append(("\n", None))
        if config['dns_servers']:
            lines.append(("当前DNS服务器:\n", None))
            for dns in config['dns_servers']:
                lines.append((f"  {dns}\n", "highlight"))
        else:
            lines.append(("DNS: 无\n", "highlight"))
        for text, tag in lines:
            if tag:
                self.info_text.insert(tk.END, text, tag)
            else:
                self.info_text.insert(tk.END, text)

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
            self.entry_ip.delete(0, tk.END)
            self.entry_mask.delete(0, tk.END)
            self.entry_gateway.delete(0, tk.END)
            self.extra_ips_text.delete(1.0, tk.END)
        if config['dns_servers']:
            self.entry_dns1.delete(0, tk.END)
            self.entry_dns1.insert(0, config['dns_servers'][0])
            if len(config['dns_servers']) > 1:
                self.entry_dns2.delete(0, tk.END)
                self.entry_dns2.insert(0, config['dns_servers'][1])
        else:
            self.entry_dns1.delete(0, tk.END)
            self.entry_dns2.delete(0, tk.END)
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
        if self.pending_apply:
            self.root.after_cancel(self.pending_apply)
            self.pending_apply = None
        if self.reset_before_apply.get():
            self.status_var.set("正在重置网卡（禁用再启用）...")
            try:
                set_adapter_state(self.current_adapter_name, False)
                self.root.after(1000, self._enable_and_apply)
            except Exception as e:
                messagebox.showerror("错误", f"禁用网卡失败: {str(e)}")
                self.status_var.set("就绪")
        else:
            self._do_apply_config()

    def _enable_and_apply(self):
        try:
            set_adapter_state(self.current_adapter_name, True)
            self.root.after(500, self._do_apply_config)
        except Exception as e:
            messagebox.showerror("错误", f"启用网卡失败: {str(e)}")
            self.status_var.set("就绪")

    def _do_apply_config(self):
        if self.refresh_after_id:
            self.root.after_cancel(self.refresh_after_id)
            self.refresh_after_id = None
        dns_list = []
        dns1 = self.entry_dns1.get().strip()
        if dns1:
            dns_list.append(dns1)
        dns2 = self.entry_dns2.get().strip()
        if dns2:
            dns_list.append(dns2)
        if self.dns_only_mode.get():
            try:
                set_dns_only(self.current_adapter_name, dns_list)
                self.status_var.set(f"已为 {self.current_adapter_name} 单独修改 DNS")
                self.auto_refresh(5, 2000)
                messagebox.showinfo("成功", "DNS 已更新")
            except Exception as e:
                messagebox.showerror("错误", f"修改 DNS 失败: {str(e)}")
            return
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
                set_static(self.current_adapter_name, ip, mask, gateway if gateway else None, extra_ips, dns_list)
                self.status_var.set(f"已为 {self.current_adapter_name} 应用静态配置")
                self.auto_refresh(5, 2000)
                messagebox.showinfo("成功", "静态IP配置已应用")
            except Exception as e:
                messagebox.showerror("错误", f"设置静态IP失败: {str(e)}")

    def auto_refresh(self, times, interval_ms):
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