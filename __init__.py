try:
    from .img_url_loader import ImageURLLoader
except ImportError:
    from img_url_loader import ImageURLLoader
try:
    from .load_multiimage import LoadMultiImage
except ImportError:
    from load_multiimage import LoadMultiImage

NODE_CLASS_MAPPINGS = {
    "ImageURLLoader": ImageURLLoader,
    "LoadMultiImage": LoadMultiImage
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "ImageURLLoader": "图像URL加载器",
    "LoadMultiImage": "Load Multi Image（多图合并）"
}

__all__ = ['NODE_CLASS_MAPPINGS', 'NODE_DISPLAY_NAME_MAPPINGS']



