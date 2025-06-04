import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import sv_ttk  # For the Sun Valley theme
import os
import json
import datetime
import yaml # version == 6.0.2

# 导入用户要求的库，即使暂时不用
try:
    import wmi
    import win32api # pywin32 的一部分
    # print("wmi and pywin32 imported successfully.")
except ImportError as e:
    print(f"Warning: Could not import wmi or pywin32. Some advanced features might be unavailable. Error: {e}")
    wmi = None
    win32api = None


# --- Placeholder Functions ---
# (Placeholder functions remain the same as the previous version)
def read_mapping_file(filepath):
    """读取并解析Socks5映射文件 (应为 JSON)""" 
    print(f"[INFO] Reading mapping file: {filepath}")
    if not os.path.exists(filepath):
        print(f"[ERROR] Mapping file not found: {filepath}")
        return None, "映射文件未找到"
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        # Basic validation (check if it's a dictionary)
        if not isinstance(data, dict):
             raise ValueError("JSON顶层结构必须是一个对象 (dictionary)")
        # Further validation could be added here (e.g., check keys like 'socks_local')
        print(f"[DEBUG] Successfully read and parsed mapping file.")
        return data, None # Return data and no error message
    except json.JSONDecodeError as e:
        print(f"[ERROR] Failed to parse mapping file (invalid JSON) {filepath}: {e}")
        return None, f"映射文件JSON格式无效: {e}"
    except Exception as e:
        print(f"[ERROR] Failed to read mapping file {filepath}: {e}")
        return None, f"读取映射文件失败: {e}"

def read_proxy_file(filepath):
    """读取并解析Socks5代理文件 (应为 TXT)"""
    print(f"[INFO] Reading proxy file: {filepath}")
    if not os.path.exists(filepath):
        print(f"[ERROR] Proxy file not found: {filepath}")
        return None, "代理文件未找到"
    proxies = []
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            for i, line in enumerate(f):
                line = line.strip()
                if not line or line.startswith('#'): # Skip empty lines and comments
                    continue
                parts = line.split(':')
                if len(parts) == 4:
                    proxies.append({
                        'ip': parts[0],
                        'port': parts[1],
                        'user': parts[2],
                        'pass': parts[3],
                        'line_num': i + 1 # For error reporting
                    })
                else:
                    print(f"代理文件第 {i+1} 行格式无效: '{line}'")
        print(f"[DEBUG] Successfully read and parsed proxy file. Found {len(proxies)} valid entries.")
        return proxies, None
    except Exception as e:
        print(f"[ERROR] Failed to read proxy file {filepath}: {e}")
        return None, f"读取代理文件失败: {e}"


def read_clash_config(filepath):
    """读取并解析Clash配置文件 (应为 YAML/YML)"""
    print(f"[INFO] Reading clash config file: {filepath}")
    if not os.path.exists(filepath):
        print(f"[ERROR] Clash config file not found: {filepath}")
        return None, "Clash配置文件未找到"
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
        if not isinstance(data, dict):
             raise ValueError("YAML顶层结构必须是一个对象 (dictionary)")
        data.setdefault('proxies', [])
        data.setdefault('proxy-groups', [])
        data.setdefault('listeners', [])
        print(f"[DEBUG] Successfully read and parsed clash config file.")
        return data, None
    except yaml.YAMLError as e:
        print(f"[ERROR] Failed to parse clash config file (invalid YAML) {filepath}: {e}")
        return None, f"Clash配置文件YAML格式无效: {e}"
    except Exception as e:
        print(f"[ERROR] Failed to read clash config file {filepath}: {e}")
        return None, f"读取Clash配置文件失败: {e}"

def process_data(mapping_data, proxy_list, base_clash_config):
    """根据读取的数据进行中间处理"""
    print("[INFO] Processing data...")
    final_config = base_clash_config.copy() # Start with the base config
    generated_proxies = []
    remote_ip_to_proxy_name = {} # Map remote IP to generated proxy name

    # 1. Generate 'proxies' from the proxy_list (TXT file)
    print("[INFO] Generating 'proxies' section from TXT data...")
    for i, proxy_info in enumerate(proxy_list):
        proxy_name = f"socks_out_{i+1:02d}" # e.g., socks_out_01, socks_out_02
        try:
            port_int = int(proxy_info['port'])
        except ValueError:
            msg = f"代理文件第 {proxy_info['line_num']} 行端口 '{proxy_info['port']}' 不是有效数字。"
            print(f"[ERROR] {msg}")
            return None, msg # Return error

        new_proxy = {
            "name": proxy_name,
            "type": "socks5",
            "server": proxy_info['ip'],
            "port": port_int,
            "username": proxy_info['user'],
            "password": proxy_info['pass'],
            "tls": False,
            "skip-cert-verify": True,
            "udp": True
        }
        generated_proxies.append(new_proxy)
        # Store mapping for later use in proxy-groups
        # Use server IP as the key for lookup based on 'socks_remote'
        remote_ip_to_proxy_name[proxy_info['ip']] = proxy_name
        print(f"[DEBUG] Generated proxy: {proxy_name} for {proxy_info['ip']}:{proxy_info['port']}")

    # Append generated proxies to the existing ones (if any) in the base config
    # Ensure 'proxies' key exists and is a list
    if not isinstance(final_config.get('proxies'), list):
        print("[WARNING] Base config 'proxies' key is missing or not a list. Creating a new list.")
        final_config['proxies'] = []
    final_config['proxies'].extend(generated_proxies)
    print(f"[INFO] Appended {len(generated_proxies)} generated proxies.")


    # 2. Generate 'listeners' and 'proxy-groups' from mapping_data (JSON file)
    print("[INFO] Generating 'listeners' and 'proxy-groups' sections from JSON data...")
    generated_listeners = []
    generated_proxy_groups = []

    # Sort keys numerically if they are strings representing numbers
    try:
        sorted_mapping_keys = sorted(mapping_data.keys(), key=lambda k: int(k))
    except ValueError:
        print("[WARNING] Mapping file keys are not all numeric strings. Using default string sort order.")
        sorted_mapping_keys = sorted(mapping_data.keys())

    for key in sorted_mapping_keys:
        map_entry = mapping_data[key]
        listener_name = f"socks_{key}"
        relay_group_name = f"socks_relay_{key}" # Use key directly as requested

        # --- Generate Listener ---
        socks_local = map_entry.get("socks_local")
        if not socks_local or ':' not in socks_local:
            msg = f"映射文件条目 '{key}' 的 'socks_local' 格式无效或缺失: '{socks_local}'"
            print(f"[ERROR] {msg}")
            return None, msg
        try:
            local_ip, local_port_str = socks_local.split(':', 1)
            local_port = int(local_port_str)
        except ValueError:
            msg = f"映射文件条目 '{key}' 的 'socks_local' 端口 '{local_port_str}' 不是有效数字。"
            print(f"[ERROR] {msg}")
            return None, msg

        new_listener = {
            "name": listener_name,
            "type": "mixed",
            "port": local_port,
            "proxy": relay_group_name # Link to the relay group
        }
        generated_listeners.append(new_listener)
        print(f"[DEBUG] Generated listener: {listener_name} on port {local_port} -> {relay_group_name}")

        # --- Generate Proxy Group (Relay) ---
        socks_remote_ip = map_entry.get("socks_remote")
        if not socks_remote_ip:
            msg = f"映射文件条目 '{key}' 的 'socks_remote' 缺失。"
            print(f"[ERROR] {msg}")
            return None, msg

        # Find the corresponding generated proxy name using the remote IP
        target_proxy_name = remote_ip_to_proxy_name.get(socks_remote_ip)
        if not target_proxy_name:
            # Check if socks_remote contains port, try splitting
            if ':' in socks_remote_ip:
                 socks_remote_ip_only, _ = socks_remote_ip.split(':', 1)
                 target_proxy_name = remote_ip_to_proxy_name.get(socks_remote_ip_only)

            if not target_proxy_name:
                 msg = f"映射文件条目 '{key}' 的 'socks_remote' IP '{socks_remote_ip}' 在代理文件(生成的proxies)中未找到对应的条目。"
                 print(f"[ERROR] {msg}")
                 print(f"[DEBUG] Available remote IPs from proxy file: {list(remote_ip_to_proxy_name.keys())}")
                 return None, msg # Stop processing

        new_group = {
            "name": relay_group_name,
            "type": "relay",
            "proxies": [
                "Switch-Proxy",     # Fixed entry
                target_proxy_name   # Dynamically linked proxy
            ]
        }
        generated_proxy_groups.append(new_group)
        print(f"[DEBUG] Generated proxy-group: {relay_group_name} with target '{target_proxy_name}'")

    # Replace the listeners list entirely
    final_config['listeners'] = generated_listeners
    print(f"[INFO] Replaced 'listeners' section with {len(generated_listeners)} generated listeners.")

    # Append generated proxy groups to the existing ones
    if not isinstance(final_config.get('proxy-groups'), list):
        print("[WARNING] Base config 'proxy-groups' key is missing or not a list. Creating a new list.")
        final_config['proxy-groups'] = []
    final_config['proxy-groups'].extend(generated_proxy_groups)
    print(f"[INFO] Appended {len(generated_proxy_groups)} generated proxy groups.")

    print("[INFO] Data processing complete.")
    return final_config, None # Return the modified config and no error

def write_output_file(output_dir, processed_data):
    """将处理结果写入到目标目录下的文件"""
    print(f"[INFO] Writing output file to directory: {output_dir}")
    timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    output_filename = f"generated_clash_config_{timestamp}.yaml"
    output_filepath = os.path.join(output_dir, output_filename)
    print(f"[INFO] Writing final YAML configuration to: {output_filepath}")
    if not os.path.isdir(output_dir):
        print(f"[ERROR] Output directory not found: {output_dir}")
        return False, None, "输出目录不存在"
    try:
        with open(output_filepath, 'w', encoding='utf-8') as f:
            yaml.dump(processed_data, f, allow_unicode=True, sort_keys=False, default_flow_style=False)
        print(f"[INFO] Successfully wrote output file.")
        return True, output_filepath, None
    except Exception as e:
        print(f"[ERROR] Failed to write output file to {output_filepath}: {e}")
        return False, None, f"写入输出文件失败: {e}"

# --- GUI Application Class ---

class FileProcessorApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("文件处理与生成工具")
        # Adjusted height slightly, as status bar isn't shown initially
        self.geometry("600x300")

        # --- Variables ---
        self.mapping_file_var = tk.StringVar()
        self.proxy_file_var = tk.StringVar()
        self.clash_file_var = tk.StringVar()
        self.output_dir_var = tk.StringVar()

        # --- Status Label Visibility Flag ---
        self.status_label_visible = False

        # --- UI Elements ---
        self.create_widgets()

        # --- Apply Theme ---
        sv_ttk.set_theme("light") # Or "dark"

    def create_widgets(self):
        """创建界面组件"""
        main_frame = ttk.Frame(self, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Configure grid layout
        main_frame.columnconfigure(1, weight=1)

        # Row indices start from 0 now for the file inputs
        # 1. Socks5 Mapping File
        ttk.Label(main_frame, text="Socks5 映射文件:").grid(row=0, column=0, padx=5, pady=5, sticky=tk.W)
        mapping_entry = ttk.Entry(main_frame, textvariable=self.mapping_file_var, state='readonly', width=50)
        mapping_entry.grid(row=0, column=1, padx=5, pady=5, sticky=tk.EW)
        mapping_button = ttk.Button(main_frame, text="浏览", command=self.browse_mapping_file)
        mapping_button.grid(row=0, column=2, padx=5, pady=5)

        # 2. Socks5 Proxy File
        ttk.Label(main_frame, text="Socks5 代理文件:").grid(row=1, column=0, padx=5, pady=5, sticky=tk.W)
        proxy_entry = ttk.Entry(main_frame, textvariable=self.proxy_file_var, state='readonly', width=50)
        proxy_entry.grid(row=1, column=1, padx=5, pady=5, sticky=tk.EW)
        proxy_button = ttk.Button(main_frame, text="浏览", command=self.browse_proxy_file)
        proxy_button.grid(row=1, column=2, padx=5, pady=5)

        # 3. Clash Config File
        ttk.Label(main_frame, text="Clash 基础配置:").grid(row=2, column=0, padx=5, pady=5, sticky=tk.W)
        clash_entry = ttk.Entry(main_frame, textvariable=self.clash_file_var, state='readonly', width=50)
        clash_entry.grid(row=2, column=1, padx=5, pady=5, sticky=tk.EW)
        clash_button = ttk.Button(main_frame, text="浏览", command=self.browse_clash_file)
        clash_button.grid(row=2, column=2, padx=5, pady=5)

        # 4. Output Directory
        ttk.Label(main_frame, text="输出目录:").grid(row=3, column=0, padx=5, pady=5, sticky=tk.W)
        output_entry = ttk.Entry(main_frame, textvariable=self.output_dir_var, state='readonly', width=50)
        output_entry.grid(row=3, column=1, padx=5, pady=5, sticky=tk.EW)
        output_button = ttk.Button(main_frame, text="选择目录", command=self.browse_output_dir)
        output_button.grid(row=3, column=2, padx=5, pady=5)

        # Separator
        ttk.Separator(main_frame, orient='horizontal').grid(row=4, column=0, columnspan=3, sticky='ew', pady=10)

        # Status Label (Defined but not gridded initially)
        self.status_label = ttk.Label(main_frame, text="") # Initial text is empty

        # Generate Button Frame (Row index adjusted)
        # It's now at row=6, leaving row=5 for the status label when it appears
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=6, column=0, columnspan=3, pady=(5, 10)) # Added top padding

        self.generate_button = ttk.Button(button_frame, text="生成文件", command=self.generate_files, style='Accent.TButton')
        self.generate_button.pack()

    # --- Callback Functions ---
    # (browse_* functions remain the same as the previous version)
    def browse_mapping_file(self):
        """浏览选择Socks5映射文件 (JSON)"""
        filetypes = (("JSON files", "*.json"), ("All files", "*.*"))
        filepath = filedialog.askopenfilename(title="选择Socks5映射文件", filetypes=filetypes)
        if filepath:
            self.mapping_file_var.set(filepath)
            # self.update_status("已选择映射文件") # Don't update status before generate clicked

    def browse_proxy_file(self):
        """浏览选择Socks5代理文件 (TXT)"""
        filetypes = (("Text files", "*.txt"), ("All files", "*.*"))
        filepath = filedialog.askopenfilename(title="选择Socks5代理文件", filetypes=filetypes)
        if filepath:
            self.proxy_file_var.set(filepath)
            # self.update_status("已选择代理文件")

    def browse_clash_file(self):
        """浏览选择Clash配置文件 (YAML/YML)"""
        filetypes = (("YAML files", "*.yaml"), ("YML files", "*.yml"), ("All files", "*.*"))
        filepath = filedialog.askopenfilename(title="选择Clash配置文件", filetypes=filetypes)
        if filepath:
            self.clash_file_var.set(filepath)
            # self.update_status("已选择Clash配置文件")

    def browse_output_dir(self):
        """浏览选择输出目录"""
        dirpath = filedialog.askdirectory(title="选择输出目录")
        if dirpath:
            self.output_dir_var.set(dirpath)
            # self.update_status("已选择输出目录")

    def update_status(self, message):
        """更新状态栏信息 (Only if visible)"""
        if self.status_label_visible: # Check if the label should be updated
            self.status_label.config(text=message)
            self.update_idletasks() # Force UI update

    def generate_files(self):
        """执行文件生成逻辑"""
        mapping_file = self.mapping_file_var.get()
        proxy_file = self.proxy_file_var.get()
        clash_file = self.clash_file_var.get()
        output_dir = self.output_dir_var.get()

        # --- Input Validation ---
        if not all([mapping_file, proxy_file, clash_file, output_dir]):
            messagebox.showerror("错误", "请确保所有文件和输出目录都已选择！")
            # Don't show status label for simple validation errors before processing starts
            return

        # --- Show Status Label if hidden ---
        if not self.status_label_visible:
            # Place the status label in the grid (row=5, between separator and button frame)
            self.status_label.grid(row=5, column=0, columnspan=3, padx=5, pady=5, sticky=tk.W)
            self.status_label_visible = True
            self.geometry("600x320") # Optionally resize window slightly to fit label

        # --- Validation for existing files/dirs (Now update status) ---
        if not os.path.exists(mapping_file):
            messagebox.showerror("错误", f"映射文件不存在:\n{mapping_file}")
            self.update_status("错误：映射文件无效")
            return
        if not os.path.exists(proxy_file):
            messagebox.showerror("错误", f"代理文件不存在:\n{proxy_file}")
            self.update_status("错误：代理文件无效")
            return
        if not os.path.exists(clash_file):
            messagebox.showerror("错误", f"Clash配置文件不存在:\n{clash_file}")
            self.update_status("错误：Clash配置文件无效")
            return
        if not os.path.isdir(output_dir):
             messagebox.showerror("错误", f"输出目录无效或不是一个目录:\n{output_dir}")
             self.update_status("错误：输出目录无效")
             return

        # --- Disable button and Update Status ---
        self.generate_button.config(state=tk.DISABLED)
        self.update_status("正在处理和生成文件...") # Now this will show

        try:
            # --- Call Processing Logic ---
            mapping_data, error_msg = read_mapping_file(mapping_file)
            if error_msg: raise ValueError(f"映射文件错误: {error_msg}")

            proxy_list, error_msg = read_proxy_file(proxy_file)
            if error_msg: raise ValueError(f"代理文件错误: {error_msg}")

            base_clash_config, error_msg = read_clash_config(clash_file)
            if error_msg: raise ValueError(f"基础配置错误: {error_msg}")

            if mapping_data is None or proxy_list is None or base_clash_config is None:
                 raise ValueError("读取输入文件时发生错误，请检查控制台输出。")

            self.update_status("正在合并和生成配置...")
            final_config, error_msg = process_data(mapping_data, proxy_list, base_clash_config)
            if error_msg: raise ValueError(f"数据处理错误: {error_msg}")
            if final_config is None: # Should be caught by error_msg, but defensive check
                 raise ValueError("数据处理返回了意外结果 (None)。")

            success, final_path, error_msg = write_output_file(output_dir, final_config)
            if not success:
                # 如果写入失败，error_msg 会包含错误信息
                raise RuntimeError(f"文件写入错误: {error_msg}")

            if success:
                self.update_status(f"文件生成成功！已写入到: {output_dir}")
                messagebox.showinfo("成功", f"文件已成功生成到:\n{output_dir}")
            else:
                 raise RuntimeError("写入输出文件时发生错误，请检查控制台输出。")

        except Exception as e:
            self.update_status(f"生成失败: {e}") # Update status with error
            messagebox.showerror("生成失败", f"处理或生成文件时发生错误:\n{e}\n\n请查看控制台获取详细信息。")
        finally:
            # --- Re-enable button ---
            self.generate_button.config(state=tk.NORMAL)


# --- Main Execution ---
if __name__ == "__main__":
    app = FileProcessorApp()
    app.mainloop()
