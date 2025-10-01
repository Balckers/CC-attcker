import os
import subprocess
import sys
from datetime import datetime

def run_custom_file(file_path):
    """一键执行单个自定义Python文件，含路径校验与结果输出"""
    # 1. 校验文件是否存在（处理相对路径，确保兼容性）
    abs_file_path = os.path.abspath(file_path)  # 转为绝对路径，避免路径错误
    if not os.path.exists(abs_file_path):
        print(f"[{datetime.now()}] 错误：目标文件 '{abs_file_path}' 不存在，请检查路径！")
        return False
    # 2. 校验是否为Python文件
    if not abs_file_path.endswith(".py"):
        print(f"[{datetime.now()}] 错误：'{abs_file_path}' 不是.py格式的Python文件！")
        return False

    try:
        # 3. 调用当前Python环境执行文件（避免环境冲突）
        result = subprocess.run(
            [sys.executable, abs_file_path],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=30  # 添加超时限制，防止无限等待
        )
        # 4. 打印成功信息与文件输出
        print(f"\n[{datetime.now()}]✅ 自定义文件执行成功！文件路径：{abs_file_path}")
        print("="*50)
        if result.stdout.strip():
            print("文件输出内容：")
            print(result.stdout)
        else:
            print("文件执行完成，无输出内容")
        return True
    except subprocess.CalledProcessError as e:
        # 捕获自定义文件的运行错误（如代码语法错、逻辑错）
        print(f"\n[{datetime.now()}]❌ 自定义文件执行失败！文件路径：{abs_file_path}")
        print("="*50)
        print("错误信息：")
        print(e.stderr if e.stderr else "未知错误")
        return False
    except subprocess.TimeoutExpired:
        print(f"\n[{datetime.now()}]⏰ 自定义文件执行超时！文件路径：{abs_file_path}")
        return False
    except Exception as e:
        # 捕获启动脚本自身的异常（如权限问题）
        print(f"\n[{datetime.now()}]⚠️  脚本启动异常：{str(e)}")
        return False

def create_config_directory():
    """创建配置目录"""
    config_dir = "配置"
    if not os.path.exists(config_dir):
        try:
            os.makedirs(config_dir)
            print(f"✅ 已创建配置目录: {config_dir}")
        except Exception as e:
            print(f"❌ 创建配置目录失败: {e}")
            return False
    return True

def check_and_create_files():
    """检查并创建必要的文件"""
    files_to_check = {
        "配置/install_ja3.py": """# install_ja3.py
print("正在安装JA3依赖...")
try:
    import pip
    pip.main(['install', 'tls-client'])
    print("✅ JA3依赖安装完成")
except:
    print("❌ JA3依赖安装失败，请手动安装: pip install tls-client")
""",
        "配置/startja3_transport.py": """# startja3_transport.py
print("正在启动JA3传输模块...")
try:
    from ja3_transport import JA3Session
    print("✅ JA3传输模块启动成功")
except ImportError as e:
    print(f"❌ JA3传输模块启动失败: {e}")
""",
        "配置/async_attacker.py": """# async_attacker.py
print("正在初始化异步攻击器...")
try:
    import asyncio
    import aiohttp
    print("✅ 异步攻击器初始化成功")
except ImportError as e:
    print(f"❌ 异步攻击器初始化失败: {e}")
""",
        "配置/http2_client.py": """# http2_client.py
print("正在初始化HTTP/2客户端...")
try:
    import hyper
    print("✅ HTTP/2客户端初始化成功")
except ImportError as e:
    print(f"❌ HTTP/2客户端初始化失败: {e}")
"""
    }
    
    created_count = 0
    for file_path, content in files_to_check.items():
        if not os.path.exists(file_path):
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                print(f"✅ 已创建文件: {file_path}")
                created_count += 1
            except Exception as e:
                print(f"❌ 创建文件 {file_path} 失败: {e}")
    
    return created_count

if __name__ == "__main__":
    # 创建配置目录
    if not create_config_directory():
        print("❌ 配置目录创建失败，程序退出")
        sys.exit(1)
    
    # 检查并创建必要的文件
    print("正在检查必要文件...")
    created_files = check_and_create_files()
    if created_files > 0:
        print(f"✅ 已创建 {created_files} 个缺失文件")
    
    # -------------------------- 修复：多文件依次执行 --------------------------
    # 将需要执行的文件路径放入列表，脚本会按顺序逐个执行
    CUSTOM_FILES = [
        "配置/install_ja3.py",
        "配置/startja3_transport.py", 
        "配置/async_attacker.py",
        "配置/http2_client.py"
    ]
    # -------------------------------------------------------------------

    # 按列表顺序执行所有文件
    print(f"\n[{datetime.now()}] 开始批量执行 {len(CUSTOM_FILES)} 个自定义文件...")
    
    success_count = 0
    for idx, file_path in enumerate(CUSTOM_FILES, 1):
        print(f"\n【第 {idx}/{len(CUSTOM_FILES)} 个文件】{file_path}")
        if run_custom_file(file_path):
            success_count += 1
        print("\n" + "-"*60)  # 分隔每个文件的执行结果
    
    # 显示执行总结
    print(f"\n[{datetime.now()}] 执行完成！")
    print(f"📊 总结: 成功 {success_count}/{len(CUSTOM_FILES)} 个文件")
    
    if success_count == len(CUSTOM_FILES):
        print("🎉 所有文件执行成功！")
    else:
        print("⚠️  部分文件执行失败，请检查上述错误信息")
    
    # 防止命令行窗口一闪而过（按任意键关闭）
    input("\n按回车键关闭窗口...")