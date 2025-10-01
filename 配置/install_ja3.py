"""
JA3指纹随机化依赖安装脚本
"""

import subprocess
import sys
import os

def install_ja3_dependencies():
    """安装JA3相关依赖"""
    print("🔧 正在安装JA3指纹随机化依赖...")
    
    packages = [
        "tls-client",
        "requests"
    ]
    
    for package in packages:
        try:
            print(f"📦 安装 {package}...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", package])
            print(f"✅ {package} 安装成功")
        except subprocess.CalledProcessError:
            print(f"❌ {package} 安装失败")
            return False
    
    print("🎉 所有依赖安装完成！")
    print("💡 现在您可以启用JA3指纹随机化功能了")
    return True

if __name__ == "__main__":
    install_ja3_dependencies()
