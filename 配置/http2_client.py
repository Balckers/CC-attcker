# http2_client.py
import ssl
import time
import socket

try:
    import hyper
    from hyper import HTTP20Connection
    from hyper.tls import init_context
    HTTP2_AVAILABLE = True
except ImportError:
    HTTP2_AVAILABLE = False
    print("⚠️ HTTP/2支持不可用，请安装: pip install hyper")

class HTTP2Client:
    """HTTP/2客户端封装，提供类似requests的接口"""
    
    def __init__(self, timeout=10, verify_ssl=False):
        self.timeout = timeout
        self.verify_ssl = verify_ssl
        self.connections = {}
        
    def _get_connection(self, host, port):
        """获取或创建HTTP/2连接"""
        if not HTTP2_AVAILABLE:
            raise ImportError("HTTP/2不可用，请安装hyper库")
            
        key = f"{host}:{port}"
        
        if key in self.connections:
            conn = self.connections[key]
            try:
                # 检查连接是否仍然有效
                conn.ping()
                return conn
            except:
                # 连接已失效，创建新的
                del self.connections[key]
        
        # 创建SSL上下文
        ssl_context = init_context()
        ssl_context.check_hostname = False
        if not self.verify_ssl:
            ssl_context.verify_mode = ssl.CERT_NONE
        
        # 创建HTTP/2连接
        try:
            conn = HTTP20Connection(
                host=host, 
                port=port,
                secure=True,
                ssl_context=ssl_context,
                timeout=self.timeout
            )
            
            self.connections[key] = conn
            return conn
        except Exception as e:
            raise ConnectionError(f"创建HTTP/2连接失败: {e}")
    
    def request(self, method, url, headers=None, body=None, timeout=None):
        """发送HTTP请求"""
        if not HTTP2_AVAILABLE:
            return self._fallback_http1(method, url, headers, body, timeout)
            
        try:
            # 解析URL
            if url.startswith('https://'):
                url = url[8:]
            elif url.startswith('http://'):
                raise ValueError("HTTP/2 requires HTTPS")
            
            # 提取主机和路径
            if '/' in url:
                host_path = url.split('/', 1)
                host = host_path[0]
                path = '/' + host_path[1] if len(host_path) > 1 else '/'
            else:
                host = url
                path = '/'
            
            # 处理端口
            if ':' in host:
                host, port_str = host.split(':', 1)
                port = int(port_str)
            else:
                port = 443
            
            # 获取连接
            conn = self._get_connection(host, port)
            
            # 准备头部 - hyper库需要unicode字符串，不需要编码为bytes
            headers_dict = {}
            if headers:
                for key, value in headers.items():
                    headers_dict[key] = str(value)
            
            # 发送请求
            start_time = time.time()
            
            # 处理请求体
            body_data = body
            if body and isinstance(body, str):
                body_data = body.encode('utf-8')
            
            conn.request(method, path, body=body_data, headers=headers_dict)
            response = conn.get_response()
            
            # 读取响应
            response_data = response.read()
            
            # 构建类似requests的响应对象
            class Response:
                def __init__(self):
                    self.status_code = response.status
                    self.headers = {}
                    # 转换headers为字典
                    if hasattr(response, 'headers'):
                        for key, value in response.headers.items():
                            if isinstance(key, bytes):
                                key = key.decode('utf-8')
                            if isinstance(value, bytes):
                                value = value.decode('utf-8')
                            self.headers[key] = value
                    self.content = response_data
                    self.elapsed = time.time() - start_time
                    
            return Response()
            
        except Exception as e:
            # 如果HTTP/2失败，尝试HTTP/1.1
            try:
                return self._fallback_http1(method, url, headers, body, timeout)
            except Exception as fallback_error:
                raise ConnectionError(f"HTTP/2请求失败: {e}, HTTP/1.1回退也失败: {fallback_error}")
    
    def _fallback_http1(self, method, url, headers=None, body=None, timeout=None):
        """回退到HTTP/1.1"""
        try:
            import requests
        except ImportError:
            raise ImportError("HTTP/2和HTTP/1.1回退都不可用，请安装requests库")
            
        session = requests.Session()
        session.verify = self.verify_ssl
        
        # 设置超时
        request_timeout = timeout or self.timeout
        
        response = session.request(
            method=method,
            url=url,
            headers=headers,
            data=body,
            timeout=request_timeout,
            allow_redirects=False  # 不自动重定向，保持与HTTP/2行为一致
        )
        
        # 构建与HTTP/2响应兼容的对象
        class Response:
            def __init__(self, resp):
                self.status_code = resp.status_code
                self.headers = dict(resp.headers)
                self.content = resp.content
                self.elapsed = resp.elapsed.total_seconds()
                
        return Response(response)
    
    def close(self):
        """关闭所有连接"""
        for conn in self.connections.values():
            try:
                conn.close()
            except:
                pass
        self.connections.clear()

# 全局HTTP/2客户端实例
_http2_client = None

def get_http2_client():
    """获取全局HTTP/2客户端实例"""
    global _http2_client
    if _http2_client is None:
        _http2_client = HTTP2Client()
    return _http2_client

# 测试函数
def test_http2_client():
    """测试HTTP/2客户端"""
    if not HTTP2_AVAILABLE:
        print("❌ HTTP/2不可用，跳过测试")
        return False
        
    client = HTTP2Client()
    try:
        # 测试一个已知支持HTTP/2的网站
        response = client.request('GET', 'https://http2.pro/api/v1')
        print(f"✅ HTTP/2测试成功: 状态码 {response.status_code}")
        return True
    except Exception as e:
        print(f"❌ HTTP/2测试失败: {e}")
        return False

if __name__ == "__main__":
    print("🚀 HTTP/2客户端测试")
    if test_http2_client():
        print("✅ HTTP/2客户端工作正常")
    else:
        print("❌ HTTP/2客户端需要调试")