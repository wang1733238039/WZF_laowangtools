try:
    from .img_url_loader import ImageURLLoader
except ImportError:
    from img_url_loader import ImageURLLoader

NODE_CLASS_MAPPINGS = {
    "ImageURLLoader": ImageURLLoader
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "ImageURLLoader": "图像URL加载器"
}

__all__ = ['NODE_CLASS_MAPPINGS', 'NODE_DISPLAY_NAME_MAPPINGS']

