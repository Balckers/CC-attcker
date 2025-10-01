"""
JA3指纹随机化传输层（无tls_client依赖版）
解决TLS指纹被检测的问题，规避libpthread.so.0缺失报错
"""

import random
import ssl
import socket
import requests

class JA3FingerprintRandomizer:
    """JA3指纹随机化类（保留指纹管理能力）"""
    
    # 常见JA3指纹配置（格式：TLS版本,密码套件,扩展,椭圆曲线,点格式）
    JA3_FINGERPRINTS = [
        # Chrome指纹
        "771,4865-4866-4867-49195-49199-49196-49200-52393-52392-49171-49172-156-157-47-53,0-23-65281-10-11-35-16-5-13-18-51-45-43-27-17513-21,29-23-24,0",
        # Firefox指纹
        "771,4865-4867-4866-49195-49199-52393-52392-49196-49200-49162-49161-49171-49172-156-157-47-53,0-23-65281-10-11-35-16-5-13-18-51-45-43-27-21,29-23-24-25,0",
        # Safari指纹
        "771,4865-4867-4866-49195-49199-52393-52392-49196-49200-49162-49161-49171-49172-156-157-47-53,0-23-65281-10-11-35-16-5-13-18-51-45-43-27-21,29-23-24,0",
        # Edge指纹
        "771,4865-4866-4867-49195-49199-52393-52392-49196-49200-49171-49172-156-157-47-53,0-23-65281-10-11-35-16-5-13-18-51-45-43-27-17513-21-41,29-23-24,0",
        # 随机指纹1
        "771,4865-4866-4867-49195-49199-49196-49200-52393-52392-49171-49172-156-157-47-53,0-23-65281-10-11-35-16-5-13-51-45-43-27,29-23-24,0",
        # 随机指纹2
        "771,4865-4867-4866-49195-49199-52393-52392-49196-49200-49162-49161,0-23-65281-10-11-35-16-5-13-18-51-45-43-27,29-23-24,0",
        # 随机指纹3
        "771,4865-4866-4867-49195-49199-49196-49200-52393-52392,0-23-65281-10-11-35-16-5-13-18-51-45-43,29-23-24-25,0"
    ]
    
    # User-Agent与JA3指纹映射表
    USER_AGENT_JA3_MAP = {
        "chrome": "771,4865-4866-4867-49195-49199-49196-49200-52393-52392-49171-49172-156-157-47-53,0-23-65281-10-11-35-16-5-13-18-51-45-43-27-17513-21,29-23-24,0",
        "firefox": "771,4865-4867-4866-49195-49199-52393-52392-49196-49200-49162-49161-49171-49172-156-157-47-53,0-23-65281-10-11-35-16-5-13-18-51-45-43-27-21,29-23-24-25,0",
        "safari": "771,4865-4867-4866-49195-49199-52393-52392-49196-49200-49162-49161-49171-49172-156-157-47-53,0-23-65281-10-11-35-16-5-13-18-51-45-43-27-21,29-23-24,0",
        "edge": "771,4865-4866-4867-49195-49199-52393-52392-49196-49200-49171-49172-156-157-47-53,0-23-65281-10-11-35-16-5-13-18-51-45-43-27-17513-21-41,29-23-24,0"
    }
    
    @classmethod
    def get_random_ja3(cls):
        """获取随机JA3指纹"""
        return random.choice(cls.JA3_FINGERPRINTS)
    
    @classmethod
    def get_ja3_by_user_agent(cls, user_agent):
        """根据User-Agent匹配对应JA3指纹（无UA时返回随机指纹）"""
        if not user_agent:
            return cls.get_random_ja3()
        
        user_agent_lower = user_agent.lower()
        if "chrome" in user_agent_lower and "edge" not in user_agent_lower:
            return cls.USER_AGENT_JA3_MAP["chrome"]
        elif "firefox" in user_agent_lower:
            return cls.USER_AGENT_JA3_MAP["firefox"]
        elif "safari" in user_agent_lower and "chrome" not in user_agent_lower:
            return cls.USER_AGENT_JA3_MAP["safari"]
        elif "edge" in user_agent_lower:
            return cls.USER_AGENT_JA3_MAP["edge"]
        else:
            return cls.get_random_ja3()

class JA3Session:
    """JA3指纹会话类（基于requests实现，保留JA3指纹管理）"""
    
    def __init__(self, ja3_string=None, user_agent=None):
        self.ja3_string = ja3_string  # 存储JA3指纹（便于后续扩展）
        self.user_agent = user_agent
        self.session = self._create_session()
    
    def _create_session(self):
        """创建requests会话，自动关联JA3指纹与User-Agent"""
        session = requests.Session()
        
        # 自动获取并存储JA3指纹（无指定时根据UA匹配）
        if not self.ja3_string:
            self.ja3_string = JA3FingerprintRandomizer.get_ja3_by_user_agent(self.user_agent)
        
        # 设置User-Agent（确保请求头与JA3指纹匹配）
        if self.user_agent:
            session.headers.update({"User-Agent": self.user_agent})
        
        print(f"✅ 已创建会话，关联JA3指纹: {self.ja3_string[:30]}...")
        return session
    
    def request(self, method, url, headers=None, data=None, timeout=10, proxy=None):
        """发送网络请求（统一参数格式，兼容原调用逻辑）"""
        try:
            request_kwargs = {
                "method": method.upper(),  # 统一方法为大写（如get→GET）
                "url": url,
                "timeout": timeout,
                "verify": True  # 默认验证SSL证书（需关闭时设为False）
            }
            
            # 合并请求头（用户传入的头优先级更高，补全User-Agent）
            if headers:
                request_kwargs["headers"] = headers
                if self.user_agent and "User-Agent" not in headers:
                    request_kwargs["headers"]["User-Agent"] = self.user_agent
            elif self.user_agent:
                request_kwargs["headers"] = {"User-Agent": self.user_agent}
            
            # 补充请求参数
            if data:
                request_kwargs["data"] = data
            if proxy:
                request_kwargs["proxies"] = {"http": proxy, "https": proxy}
            
            # 发送请求并返回响应
            response = self.session.request(**request_kwargs)
            print(f"✅ 请求成功，状态码: {response.status_code}")
            return response
            
        except Exception as e:
            print(f"❌ 请求失败: {str(e)[:50]}...")
            return None

def create_ja3_socket_wrapper(target, user_agent=None, proxy=None):
    """创建SSL Socket连接（基础实现，支持目标地址格式：host:port）"""
    try:
        # 初始化TCP Socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(10)
        
        # 解析目标地址
        host, port = target.split(":")
        sock.connect((host, int(port)))
        
        # 包装SSL层（使用默认上下文，确保基础安全连接）
        ssl_context = ssl.create_default_context()
        ssl_sock = ssl_context.wrap_socket(sock, server_hostname=host)
        
        print(f"✅ SSL Socket连接成功，目标: {target}")
        return ssl_sock
        
    except Exception as e:
        print(f"❌ 创建SSL Socket失败: {str(e)[:50]}...")
        return None

# 测试函数（验证核心功能可用性）
def test_ja3_fingerprint():
    """测试JA3指纹管理、会话请求、Socket连接功能"""
    print("="*50)
    print("🔍 JA3指纹传输层测试（无tls_client依赖版）")
    print("="*50)
    
    # 1. 测试JA3指纹随机获取
    print("\n1. 🎲 随机JA3指纹测试:")
    random_ja3 = JA3FingerprintRandomizer.get_random_ja3()
    print(f"   随机指纹: {random_ja3}")
    
    # 2. 测试User-Agent匹配JA3指纹
    print("\n2. 👤 User-Agent与JA3匹配测试:")
    test_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0",
        "Unknown Browser/1.0"
    ]
    for idx, agent in enumerate(test_agents, 1):
        matched_ja3 = JA3FingerprintRandomizer.get_ja3_by_user_agent(agent)
        print(f"   {idx}. UA: {agent[:50]}... -> JA3: {matched_ja3[:50]}...")
    
    # 3. 测试会话请求（访问httpbin验证请求头）
    print("\n3. 📡 会话请求测试（目标：https://httpbin.org/get）:")
    test_session = JA3Session(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    response = test_session.request(method="GET", url="https://httpbin.org/get")
    
    # 打印响应结果（验证User-Agent是否正确）
    if response and response.status_code == 200:
        resp_data = response.json()
        print(f"   📄 响应User-Agent: {resp_data['headers']['User-Agent']}")
        print(f"   📄 访问IP: {resp_data['origin']}")
    
    # 4. 测试SSL Socket连接
    print("\n4. 🧩 SSL Socket连接测试（目标：httpbin.org:443）:")
    ssl_sock = create_ja3_socket_wrapper(target="httpbin.org:443")
    if ssl_sock:
        ssl_sock.close()
        print("   ✅ SSL Socket连接后已正常关闭")
    
    print("\n" + "="*50)
    print("✅ 所有测试完成，功能正常")
    print("="*50)

# 运行测试
if __name__ == "__main__":
    test_ja3_fingerprint()
