import torch
import numpy as np
import requests
from PIL import Image
import io
import os
from typing import List, Tuple
import time
from urllib.parse import urlparse

class ImageURLLoader:
    """
    ComfyUI节点：读取图像URL链接，验证有效性并输出图像列表
    """
    
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "imgurl": ("STRING", {
                    "multiline": True,
                    "default": ""
                }),
                "error_message": ("STRING", {
                    "multiline": False,
                    "default": "未找到有效的图像链接"
                }),
                "throw_error": ("BOOLEAN", {
                    "default": False
                }),
            }
        }
    
    RETURN_TYPES = ("IMAGE", "STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("图像列表", "报错显示", "有效图像链接数量", "输入端imgurl图像链接总数量", "有效图像链接")
    OUTPUT_IS_LIST = (True, False, False, False, False)  # 第一个输出（图像列表）是列表类型
    FUNCTION = "load_images_from_urls"
    CATEGORY = "WZF_laowangtools"
    
    def load_images_from_urls(self, imgurl: str, error_message: str, throw_error: bool):
        """
        从URL加载图像
        
        Args:
            imgurl: 图像URL字符串，每行一个URL
            error_message: 自定义错误消息
            throw_error: 是否抛出异常
            
        Returns:
            tuple: (图像列表, 报错显示, 有效图像链接数量, 总链接数量, 有效图像链接)
        """
        # 解析URL列表（按回车分隔）
        url_lines = [line.strip() for line in imgurl.strip().split('\n') if line.strip()]
        total_count = len(url_lines)
        
        # 验证并加载有效图像
        valid_images = []
        valid_urls = []  # 保存有效图像链接，按输入顺序
        invalid_urls = []
        
        for url in url_lines:
            try:
                # 尝试加载图像
                image = self._load_image_from_url(url)
                if image is not None:
                    valid_images.append(image)
                    valid_urls.append(url)  # 保存有效的URL，保持输入顺序
            except Exception as e:
                invalid_urls.append(f"{url}: {str(e)}")
                continue
        
        valid_count = len(valid_images)
        
        # 确定错误消息
        if valid_count < 1:
            display_error = error_message
        else:
            display_error = "OK"
        
        # 如果没有有效图像且需要抛出异常
        if valid_count < 1 and throw_error:
            raise Exception(display_error)
        
        # 将图像列表转换为ComfyUI的IMAGE格式
        if valid_images:
            # 转换为tensor格式，保持每个图像的独立张量
            image_tensors = []
            for img in valid_images:
                # 转换为RGB模式
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                
                # 转换为numpy数组，然后转换为tensor
                # ComfyUI的IMAGE格式: (H, W, 3) -> (1, H, W, 3)
                img_array = np.array(img).astype(np.float32) / 255.0
                img_tensor = torch.from_numpy(img_array)[None,]  # 添加batch维度: (1, H, W, 3)
                image_tensors.append(img_tensor)
            
            # 返回张量列表，而不是拼接
            # 这样每个图像保持原始尺寸，不会出现尺寸不匹配错误
            result_images = image_tensors
        else:
            # 如果没有有效图像，返回一个空的列表
            result_images = []
        
        # 构建有效图像链接字符串（以回车分隔）
        valid_urls_text = '\n'.join(valid_urls) if valid_urls else ""
        
        return (
            result_images,
            display_error,
            str(valid_count),
            str(total_count),
            valid_urls_text
        )
    
    def _load_image_from_url(self, url: str) -> Image.Image:
        """
        从URL加载单个图像

        Args:
            url: 图像URL

        Returns:
            PIL.Image对象，如果加载失败则返回None
        """
        print(f"[DEBUG] Starting _load_image_from_url: {url[:50]}...")
        # Timeout configuration for fallback requests
        NORMAL_TIMEOUT = (10, 30)  # (connect, read) - for actual downloads
        try:
            # 检查是否为本地文件路径
            if os.path.exists(url):
                img = Image.open(url)
                img.load()
                return img

            # Normalize url
            parsed = urlparse(url)
            if not parsed.scheme:
                # try add https
                url = "https://" + url.lstrip("/")

            # 使用更稳健的会话与重试策略下载
            content = self._fetch_url_content_with_retries(url, attempts=3, backoff=0.5)
            if not content:
                raise Exception("no content")

            # 尝试用 PIL 打开 bytes
            print(f"[DEBUG] Processing content with PIL...")
            try:
                image = Image.open(io.BytesIO(content))
                image.load()
                print(f"[DEBUG] PIL success: {image.format} {image.size}")
                return image
            except Exception as e:
                print(f"[DEBUG] PIL failed: {e}")
                # 如果 PIL 打开失败，再尝试基于 headers 的简单检查+原始请求回退
                try:
                    print(f"[DEBUG] Trying fallback request...")
                    headers = {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                    }
                    resp = requests.get(url, headers=headers, timeout=NORMAL_TIMEOUT, stream=True)
                    resp.raise_for_status()
                    # 如果 content-type 明确不是 image/* 则报错
                    content_type = resp.headers.get('content-type', '')
                    if content_type and not content_type.startswith('image/'):
                        print(f"[DEBUG] Content-Type check failed: {content_type}")
                        raise ValueError(f"URL does not point to an image (content-type: {content_type})")
                    print(f"[DEBUG] Fallback PIL processing...")
                    image = Image.open(io.BytesIO(resp.content))
                    image.load()
                    print(f"[DEBUG] Fallback PIL success: {image.format} {image.size}")
                    return image
                except Exception as e2:
                    raise Exception(f"PIL open failed: {e}; fallback failed: {e2}")

        except requests.exceptions.RequestException as e:
            raise Exception(f"Failed to fetch image from URL: {str(e)}")
        except Exception as e:
            raise Exception(f"Failed to load image: {str(e)}")

    def _fetch_url_content_with_retries(self, url: str, attempts: int = 2, backoff: float = 0.3) -> bytes:
        """
        Robust fetch: use requests.Session + urllib3.Retry with SSL compatibility,
        try multiple headers and read in chunks. Enhanced SSL handling for various network environments.
        Optimized for fast failure in poor network conditions.
        Returns bytes or None.
        """
        # Tiered timeout configuration for better performance
        QUICK_TIMEOUT = (5, 10)     # (connect, read) - for HEAD checks and quick detection
        NORMAL_TIMEOUT = (10, 25)   # (connect, read) - for actual downloads
        MAX_TOTAL_TIME = 40        # Maximum total execution time in seconds

        start_time = time.time()
        print(f"[DEBUG] Starting _fetch_url_content_with_retries: URL={url[:50]}..., attempts={attempts}, max_time={MAX_TOTAL_TIME}s")

        # Try to use urllib3 Retry with enhanced SSL handling
        try:
            from requests.adapters import HTTPAdapter
            from urllib3.util.retry import Retry
        except Exception:
            # simple fallback loop with comprehensive exception handling
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
            for attempt in range(attempts):
                try:
                    # Check total timeout before each request
                    if time.time() - start_time > MAX_TOTAL_TIME:
                        print(f"Total timeout exceeded ({MAX_TOTAL_TIME}s), aborting")
                        return None

                    # Try with SSL verification first
                    try:
                        r = requests.get(url, headers=headers, timeout=NORMAL_TIMEOUT, allow_redirects=True, stream=True)
                        r.raise_for_status()
                    except requests.exceptions.SSLError:
                        # Fallback to disable SSL verification
                        try:
                            requests.packages.urllib3.disable_warnings()
                        except Exception:
                            pass
                        r = requests.get(url, headers=headers, timeout=NORMAL_TIMEOUT, allow_redirects=True, stream=True, verify=False)
                        r.raise_for_status()
                    except requests.exceptions.ProxyError as e:
                        print(f"[DEBUG] Simple fallback proxy error: {e}")
                        # Proxy errors are fatal, abort immediately
                        return None
                    except (requests.exceptions.ConnectionError,
                            requests.exceptions.Timeout,
                            requests.exceptions.TooManyRedirects,
                            requests.exceptions.ChunkedEncodingError) as e:
                        # Network-related exceptions, retry
                        raise e
                    except requests.exceptions.RequestException as e:
                        # Other request exceptions, don't retry
                        return None

                    chunks = []
                    for chunk in r.iter_content(chunk_size=32768):
                        if chunk:
                            chunks.append(chunk)
                    content = b"".join(chunks)
                    if content:
                        return content
                except requests.exceptions.ProxyError:
                    # Proxy errors are fatal, abort immediately
                    return None
                except (requests.exceptions.ConnectionError,
                        requests.exceptions.Timeout,
                        requests.exceptions.TooManyRedirects,
                        requests.exceptions.ChunkedEncodingError):
                    # Network exceptions that should be retried
                    try:
                        time.sleep(backoff * (attempt + 1))
                    except Exception:
                        pass
                    continue
                except Exception:
                    # Other exceptions, don't retry
                    break
            return None

        # Enhanced session with SSL compatibility and optimized timeouts
        print(f"[DEBUG] Using enhanced Session approach with {attempts} attempts")
        session = requests.Session()
        retry_cfg = Retry(
            total=attempts,
            backoff_factor=backoff,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset(['GET', 'HEAD'])
        )
        adapter = HTTPAdapter(max_retries=retry_cfg)
        session.mount('http://', adapter)
        session.mount('https://', adapter)

        header_variants = [
            {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)", "Accept": "image/*,*/*;q=0.8"},
            {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36", "Accept": "image/*,*/*;q=0.8"},
            {"User-Agent": "curl/7.68.0", "Accept": "*/*", "Connection": "close"},
        ]

        for attempt in range(attempts):
            # Check total timeout at the start of each attempt
            elapsed = time.time() - start_time
            print(f"[DEBUG] Starting attempt {attempt + 1}/{attempts}, elapsed: {elapsed:.1f}s")
            if elapsed > MAX_TOTAL_TIME:
                print(f"[DEBUG] Total timeout exceeded ({MAX_TOTAL_TIME}s), aborting")
                return None

            for header_idx, headers in enumerate(header_variants):
                print(f"[DEBUG] Trying header variant {header_idx + 1}/{len(header_variants)}: {headers['User-Agent'][:30]}...")

                # set referer
                try:
                    parsed = urlparse(url)
                    if parsed.scheme and parsed.netloc:
                        headers["Referer"] = f"{parsed.scheme}://{parsed.netloc}/"
                except Exception:
                    pass

                try:
                    # Additional timeout check before each header variant
                    if time.time() - start_time > MAX_TOTAL_TIME:
                        print(f"[DEBUG] Timeout check failed before header variant")
                        return None

                    # Try with SSL verification first
                    try:
                        # optional HEAD check with SSL handling (use quick timeout)
                        print(f"[DEBUG] HEAD check with SSL verification...")
                        try:
                            h = session.head(url, headers=headers, timeout=QUICK_TIMEOUT, allow_redirects=True)
                            h.raise_for_status()
                            cl = h.headers.get('content-length')
                            print(f"[DEBUG] HEAD success: status={h.status_code}, content-length={cl}")
                            if cl is not None and int(cl) == 0:
                                # no content
                                print(f"[DEBUG] Skipping due to zero content-length")
                                continue
                        except requests.exceptions.SSLError as e:
                            print(f"[DEBUG] HEAD SSL error: {e}")
                            # Try HEAD without SSL verification
                            try:
                                requests.packages.urllib3.disable_warnings()
                            except Exception:
                                pass
                            print(f"[DEBUG] Retrying HEAD without SSL verification...")
                            h = session.head(url, headers=headers, timeout=QUICK_TIMEOUT, allow_redirects=True, verify=False)
                            h.raise_for_status()
                            cl = h.headers.get('content-length')
                            print(f"[DEBUG] HEAD success (no SSL): status={h.status_code}, content-length={cl}")
                            if cl is not None and int(cl) == 0:
                                continue
                        except requests.exceptions.ProxyError as e:
                            print(f"[DEBUG] HEAD proxy error detected: {e}")
                            # Proxy errors are configuration issues, don't retry
                            return None
                        except (requests.exceptions.ConnectionError,
                                requests.exceptions.Timeout,
                                requests.exceptions.TooManyRedirects) as e:
                            print(f"[DEBUG] HEAD network exception: {type(e).__name__}: {e}")
                            # Network exceptions for HEAD, continue to GET
                            pass
                        except Exception as e:
                            print(f"[DEBUG] HEAD other exception: {type(e).__name__}: {e}")
                            pass  # HEAD check failed, continue to GET

                        # GET request with SSL handling (use normal timeout)
                        print(f"[DEBUG] GET request with SSL verification...")
                        r = session.get(url, headers=headers, timeout=NORMAL_TIMEOUT, allow_redirects=True, stream=True)
                        r.raise_for_status()
                        print(f"[DEBUG] GET success: status={r.status_code}")

                    except requests.exceptions.SSLError as e:
                        print(f"[DEBUG] GET SSL error: {e}")
                        # Fallback to disable SSL verification for GET
                        try:
                            requests.packages.urllib3.disable_warnings()
                        except Exception:
                            pass
                        print(f"[DEBUG] Retrying GET without SSL verification...")
                        r = session.get(url, headers=headers, timeout=NORMAL_TIMEOUT, allow_redirects=True, stream=True, verify=False)
                        r.raise_for_status()
                        print(f"[DEBUG] GET success (no SSL): status={r.status_code}")
                    except requests.exceptions.ProxyError as e:
                        print(f"[DEBUG] GET proxy error detected: {e}")
                        # Proxy errors are configuration issues, don't retry
                        return None
                    except (requests.exceptions.ConnectionError,
                            requests.exceptions.Timeout,
                            requests.exceptions.TooManyRedirects,
                            requests.exceptions.ChunkedEncodingError) as e:
                        # Network-related exceptions that should trigger retry
                        raise e
                    except requests.exceptions.RequestException as e:
                        # Other request exceptions, skip this header variant
                        continue

                    print(f"[DEBUG] Downloading content...")
                    chunks = []
                    for chunk in r.iter_content(chunk_size=32768):
                        if chunk:
                            chunks.append(chunk)
                    content = b"".join(chunks)
                    if content and len(content) > 0:
                        print(f"[DEBUG] Download successful: {len(content)} bytes")
                        return content
                    else:
                        print(f"[DEBUG] Download failed: empty content")

                except requests.exceptions.ProxyError as e:
                    print(f"[DEBUG] Proxy error in header variant loop: {e}")
                    # Proxy errors are fatal, abort immediately
                    return None
                except (requests.exceptions.ConnectionError,
                        requests.exceptions.Timeout,
                        requests.exceptions.TooManyRedirects,
                        requests.exceptions.ChunkedEncodingError) as e:
                    print(f"[DEBUG] Network exception for header variant: {type(e).__name__}: {e}")
                    # Network exceptions that should be retried with different header
                    # Add small delay before trying next header
                    try:
                        time.sleep(0.1)
                    except Exception:
                        pass
                    continue
                except Exception as e:
                    print(f"[DEBUG] Other exception for header variant: {type(e).__name__}: {e}")
                    # Other exceptions, skip this header variant
                    continue

        total_elapsed = time.time() - start_time
        print(f"[DEBUG] All attempts failed, total time: {total_elapsed:.1f}s")
        return None

