import subprocess
import sys


def build():
    # 运行PyInstaller
    print("\n正在打包程序...")
    command = [
        'pyinstaller',
    ]
    command.extend(['--onefile', '--windowed'])
    command.extend(['--name', "ClashConfig Tools"])
    command.extend(['--icon', "tools.ico"])
    command.append('generate_socks5_clash_config.py')
    print("Executing command:")
    # 使用 subprocess.list2cmdline 可以在 Windows 上很好地显示命令行的样子
    # 在 Linux/macOS 上，直接打印列表通常更清晰
    if sys.platform == 'win32':
        print(subprocess.list2cmdline(command))
    else:
        # 在非 Windows 系统上，为了清晰，可以简单地用空格连接
        print(' '.join(f'"{arg}"' if ' ' in arg else arg for arg in command))
    try:
        subprocess.run(command, check=True, text=True, capture_output=True, encoding='utf-8')
        # subprocess.run(['pyinstaller', '--onefile', '--windowed', '--name="ClashConfig Tools"', '--icon="tools.ico"', 'generate_socks5_clash_config.py'], check=True)
    except subprocess.CalledProcessError as e:
        error_msg = str(e)
        print(error_msg)

if __name__ == "__main__":
    try:
        success = build()
    except Exception as e:
        print(str(e))
    finally:
        input("\n按回车键退出...") 