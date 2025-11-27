import torch
import numpy as np
import requests
from PIL import Image
import io
import os
from typing import List, Tuple

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
        try:
            # 检查是否为本地文件路径
            if os.path.exists(url):
                return Image.open(url)
            
            # 尝试作为URL加载
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            response = requests.get(url, headers=headers, timeout=10, stream=True)
            response.raise_for_status()
            
            # 验证内容类型
            content_type = response.headers.get('content-type', '')
            if not content_type.startswith('image/'):
                raise ValueError(f"URL does not point to an image (content-type: {content_type})")
            
            # 加载图像
            image = Image.open(io.BytesIO(response.content))
            image.load()  # 确保图像数据已加载
            
            return image
            
        except requests.exceptions.RequestException as e:
            raise Exception(f"Failed to fetch image from URL: {str(e)}")
        except Exception as e:
            raise Exception(f"Failed to load image: {str(e)}")

