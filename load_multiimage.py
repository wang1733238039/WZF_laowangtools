import torch
import numpy as np
import requests
from PIL import Image
import io
import os
from typing import List
import time

class LoadMultiImage:
    """
    ComfyUI 节点：load_multiimage（简化版）
    - 固定预置 20 个输入插槽（image_0 .. image_19）为 optional（可选），上游不连线也不会报错
    - 还有一个可选的文本输入 `imgurl`（每行一条 URL 或本地路径）
    - 输出：第一个为图像列表（所有有效图像），接着 20 个独立图像输出（对应 image_0..image_19），
      最后两项为输入端图像总数量（字符串）和输出端图像总数量（字符串）
    """

    @classmethod
    def INPUT_TYPES(cls):
        max_slots = 20
        # required 为空，避免因为必需参数缺失导致报错
        required = {}
        optional = {}
        # 新增图像列表输入插槽：标记为 list 类型以确保 ComfyUI 将整个列表作为单个输入传递（避免被映射执行）
        optional["imglist"] = ("IMAGE", {"default": None, "list": True})
        optional["imgurl"] = ("STRING", {"multiline": True, "default": ""})
        for i in range(max_slots):
            optional[f"image_{i}"] = ("IMAGE", {"default": None})
        return {"required": required, "optional": optional}

    # 返回类型：第一个 IMAGE 列表，然后 20 个 IMAGE 输出，再两个 STRING
    max_slots = 20
    RETURN_TYPES = tuple(["IMAGE"] + ["IMAGE"] * max_slots + ["STRING", "STRING", "STRING"])
    RETURN_NAMES = tuple(["图像列表"] + [f"图像_{i}" for i in range(max_slots)] + ["输入端图像总数量", "输出端图像总数量", "加载报告"])
    # 第一个输出是一个 Python 列表（图像列表），但不应被 ComfyUI 自动展开为多次执行，
    # 因此将其标记为 False（普通对象），避免 ComfyUI 把节点映射多次执行导致重复输出。
    OUTPUT_IS_LIST = tuple([False] + [False] * max_slots + [False, False, False])
    # 明确指定输入中哪些是 list 类型，避免 ComfyUI 在连接 Image List 时对节点进行自动映射（map）。
    # 输入顺序与 INPUT_TYPES 中 required/optional 的顺序一致：imglist, imgurl, image_0..image_19
    INPUT_IS_LIST = tuple([True, False] + [False] * max_slots)
    FUNCTION = "process"
    CATEGORY = "WZF_laowangtools"

    def process(self, *args, **kwargs):
        """
        合并并输出图像（增强版）：
        - 支持从 kwargs 中读取 image_0..image_19（optional）和可选的 imgurl 文本
        - 位置参数中若包含字符串，也会被视为 imgurl 文本（兼容文本节点作为位置参数传入的情况）
        - 对 URL 下载使用重试逻辑以提高命中率
        """
        max_slots = 20

        # 收集图像与可能来自位置参数的 imgurl 文本
        imglist_images = []  # 存储图像列表输入
        input_images = []    # 存储直接连接的图像
        imgurl_texts = []    # 存储URL文本
        for a in args:
            if a is None:
                continue
            # 如果位置参数是字符串，则很可能是多行的 imgurl 文本
            if isinstance(a, str):
                imgurl_texts.append(a)
                continue
            if isinstance(a, (list, tuple)):
                for v in a:
                    if v is None:
                        continue
                    if isinstance(v, str):
                        imgurl_texts.append(v)
                        continue
                    input_images.append(v)
            else:
                input_images.append(a)

        # 从 kwargs 的 image_0..image_19 中收集（这些是 optional）
        for i in range(max_slots):
            key = f"image_{i}"
            if key in kwargs:
                val = kwargs.get(key)
                if val is None:
                    continue
                if isinstance(val, (list, tuple)):
                    for v in val:
                        if v is not None:
                            input_images.append(v)
                else:
                    input_images.append(val)

        # 收集 kwargs 中的 imgurl（如果有），兼容多种上游类型（字符串、多行字符串、列表/元组、或可转为字符串的对象）
        kw_imgurl = kwargs.get("imgurl", "")
        if kw_imgurl is not None:
            # 直接字符串
            if isinstance(kw_imgurl, str) and kw_imgurl.strip():
                imgurl_texts.append(kw_imgurl)
            # 列表或元组（例如某些节点会传入字符串列表）
            elif isinstance(kw_imgurl, (list, tuple)):
                for item in kw_imgurl:
                    if item is None:
                        continue
                    if isinstance(item, str) and item.strip():
                        imgurl_texts.append(item)
                    elif isinstance(item, (list, tuple)):
                        for sub in item:
                            if isinstance(sub, str) and sub.strip():
                                imgurl_texts.append(sub)
                    else:
                        try:
                            s = str(item)
                            if s.strip():
                                imgurl_texts.append(s)
                        except Exception:
                            continue
            else:
                # 其他可表示为字符串的对象
                try:
                    s = str(kw_imgurl)
                    if s.strip():
                        imgurl_texts.append(s)
                except Exception:
                    pass

        # 收集 kwargs 中的 imglist（图像列表），使用递归扁平化以兼容多层嵌套的列表结构
        kw_imglist = kwargs.get("imglist")
        if kw_imglist is not None:
            imglist_images.extend(self._ensure_list_of_images(kw_imglist))

        # 尝试解析 URL 文本并准备下载

        # 合并所有 imgurl 文本来源
        combined_imgurl = "\n".join([t for t in imgurl_texts if isinstance(t, str) and t.strip()]) if imgurl_texts else ""
        url_lines = [line.strip() for line in combined_imgurl.strip().split("\n") if line.strip()]

        # Attempt to extract full URLs robustly.
        import re
        combined_text = combined_imgurl
        # First try regex to find typical URLs
        found = re.findall(r"https?://[^\s'\"<>]+", combined_text)
        if found:
            url_lines = found
        else:
            # Fallback: per-line normalization to handle split tokens.
            normalized_urls = []
            i = 0
            while i < len(url_lines):
                line = url_lines[i].strip()
                # remove surrounding <> or quotes
                if (line.startswith("<") and line.endswith(">")) or (line.startswith('"') and line.endswith('"')) or (line.startswith("'") and line.endswith("'")):
                    line = line[1:-1].strip()

                # Case: line is "http:" or "https:" and next looks like domain or starts with '//' or without scheme
                if line.lower() in ("http:", "https:") and i + 1 < len(url_lines):
                    nxt = url_lines[i + 1].strip()
                    # if next starts with '//' attach directly
                    if nxt.startswith("//"):
                        combined = line + nxt
                        normalized_urls.append(combined)
                        i += 2
                        continue
                    # if next looks like domain/path (contains a dot and no space), join with '//' between
                    if "." in nxt and " " not in nxt:
                        combined = line + "//" + nxt.lstrip("/").lstrip()
                        normalized_urls.append(combined)
                        i += 2
                        continue
                # if line starts with '//' assume https
                if line.startswith("//"):
                    normalized_urls.append("https:" + line)
                    i += 1
                    continue
                # if line itself contains '://' it's probably ok
                if "://" in line:
                    normalized_urls.append(line)
                    i += 1
                    continue
                # as a last resort, if line contains a dot and looks like a path, prefix https://
                if "." in line and not line.lower().startswith("http"):
                    normalized_urls.append("https://" + line.lstrip("/"))
                    i += 1
                    continue
                # otherwise keep as-is
                normalized_urls.append(line)
                i += 1
            url_lines = [u for u in normalized_urls if u]

        # 从 URL 加载图像（使用重试），同时记录每个 URL 的加载状态便于调试
        loaded_from_urls = []

        # --------------- 辅助函数：描述对象类型/形状 ---------------
        def _describe_obj(obj):
            try:
                tname = type(obj).__name__
            except Exception:
                tname = "Unknown"
            shape_desc = None
            try:
                if hasattr(obj, "shape"):
                    try:
                        shp = obj.shape
                        shape_desc = tuple(shp) if not isinstance(shp, int) else (shp,)
                    except Exception:
                        shape_desc = str(getattr(obj, "shape", None))
                elif hasattr(obj, "size") and callable(getattr(obj, "size", None)):
                    try:
                        sz = obj.size()
                        shape_desc = tuple(sz) if not isinstance(sz, int) else (sz,)
                    except Exception:
                        try:
                            shape_desc = tuple(obj.size)
                        except Exception:
                            shape_desc = str(getattr(obj, "size", None))
            except Exception:
                shape_desc = None
            if shape_desc is not None:
                return f"{tname}{shape_desc}"
            return f"{tname}"

        url_results = []
        # add debug info about the combined text and parsed URLs
        try:
            preview_text = combined_text.strip().replace("\n", "\\n")
            if len(preview_text) > 1000:
                preview_text = preview_text[:1000] + "...(truncated)"
        except Exception:
            preview_text = ""
        url_results.append(f"COMBINED_TEXT: {preview_text}")
        url_results.append(f"PARSED_URLS: {url_lines}")
        # 诊断：记录 imglist/input_images 的类型与长度，方便在加载报告中查看
        try:
            url_results.append(f"DIAG_imglist_len: {len(imglist_images)}")
            url_results.append(f"DIAG_imglist_preview: {[ _describe_obj(x) for x in imglist_images[:10]]}")
            url_results.append(f"DIAG_input_images_len: {len(input_images)}")
            url_results.append(f"DIAG_input_preview: {[ _describe_obj(x) for x in input_images[:10]]}")
        except Exception as _e:
            try:
                url_results.append(f"DIAG_EXCEPTION_when_recording: {_e}")
            except Exception:
                pass
        for url in url_lines:
            try:
                content = self._fetch_url_content_with_retries(url, attempts=3, backoff=0.5)
                if not content:
                    url_results.append(f"FAILED: {url} -> no content")
                    continue
                try:
                    pil_img = Image.open(io.BytesIO(content))
                    pil_img.load()
                    if pil_img.mode != "RGB":
                        pil_img = pil_img.convert("RGB")
                    tensor_img = self._pil_to_image_tensor(pil_img)
                    loaded_from_urls.append(tensor_img)
                    url_results.append(f"OK: {url} (bytes={len(content)})")
                    continue
                except Exception as e:
                    # 后备尝试使用原有方法
                    try:
                        pil_img = self._load_image_from_url(url)
                        if pil_img is not None:
                            if pil_img.mode != "RGB":
                                pil_img = pil_img.convert("RGB")
                            tensor_img = self._pil_to_image_tensor(pil_img)
                            loaded_from_urls.append(tensor_img)
                            url_results.append(f"OK(fallback): {url}")
                            continue
                    except Exception as e2:
                        url_results.append(f"FAILED: {url} -> pil_open_failed:{e} | fallback_failed:{e2}")
                        continue
            except Exception as e:
                url_results.append(f"FAILED: {url} -> exception:{e}")
                continue

        # 合并：依次按 imglist、input_images、URL加载的图像 的顺序
        merged_images = []
        # 1. 先添加图像列表输入
        merged_images.extend(imglist_images)
        # 2. 再添加直接连接的图像
        merged_images.extend(input_images)
        # 3. 最后添加URL加载的图像
        merged_images.extend(loaded_from_urls)

        # 诊断：记录合并前的结构预览（未扁平化）
        try:
            url_results.append(f"DIAG_merged_before_len: {len(merged_images)}")
            url_results.append(f"DIAG_merged_before_preview: {[ _describe_obj(x) for x in merged_images[:20]]}")
        except Exception:
            pass

        # 安全：如果 merged_images 中仍存在嵌套的 list/tuple，将其完全扁平化，保证每个元素是单张图像 tensor
        def _flatten_list_once(items):
            out = []
            for it in items:
                if isinstance(it, (list, tuple)):
                    for sub in it:
                        out.append(sub)
                else:
                    out.append(it)
            return out

        # 反复扁平化直到没有嵌套 list/tuple（防止多层嵌套导致每个输出变成列表）
        flattened = merged_images
        max_flatten_iters = 5
        for _ in range(max_flatten_iters):
            if any(isinstance(x, (list, tuple)) for x in flattened):
                flattened = _flatten_list_once(flattened)
            else:
                break
        merged_images = flattened

        # 为避免上游复用同一 tensor 对象导致下游重复显示，针对常见类型做浅拷贝（确保每个元素为独立对象）
        try:
            cloned_images = []
            for x in merged_images:
                try:
                    # 优先处理 torch.Tensor
                    if 'torch' in globals() and hasattr(x, "data_ptr") and callable(getattr(x, "data_ptr")):
                        try:
                            new_x = x.clone()
                        except Exception:
                            try:
                                new_x = x.detach().clone()
                            except Exception:
                                new_x = x
                        cloned_images.append(new_x)
                        continue
                    # numpy 数组拷贝
                    if isinstance(x, np.ndarray):
                        cloned_images.append(x.copy())
                        continue
                except Exception:
                    pass
                # 其他类型保持原样
                cloned_images.append(x)
            merged_images = cloned_images
        except Exception:
            # 出错时保持原始列表
            merged_images = merged_images

        # 诊断：记录合并后的类型预览
        try:
            url_results.append(f"DIAG_merged_len: {len(merged_images)}")
            url_results.append(f"DIAG_merged_preview: {[ _describe_obj(x) for x in merged_images[:20]]}")
        except Exception:
            pass

        # 诊断：检查是否有重复对象（通过 tensor.data_ptr() 或 id() 判断），便于定位重复输出问题
        try:
            ids = []
            for x in merged_images:
                try:
                    # torch.Tensor 支持 data_ptr()
                    if hasattr(x, "data_ptr") and callable(getattr(x, "data_ptr")):
                        ids.append(("ptr", x.data_ptr()))
                    else:
                        ids.append(("id", id(x)))
                except Exception:
                    ids.append(("id", id(x)))
            # 统计唯一数与重复索引
            uniq = {}
            for idx, key in enumerate(ids):
                uniq.setdefault(key, []).append(idx)
            unique_count = len(uniq)
            dup_info = {k: v for k, v in uniq.items() if len(v) > 1}
            url_results.append(f"DIAG_merged_unique_count: {unique_count}")
            url_results.append(f"DIAG_merged_duplicates: { {str(k): v for k, v in dup_info.items()} }")
        except Exception:
            pass

        # 第一个输出：实际图像列表（不包含 None）
        image_list_for_export = merged_images.copy()

        # 逐一输出：固定 20 个槽，只取前20个图像，不足用None填充
        per_slot_outputs = []
        for i in range(max_slots):
            if i < len(merged_images):
                per_slot_outputs.append(merged_images[i])
            else:
                per_slot_outputs.append(None)

        # 统计：输入端图像总数 = imglist图像数量 + input_images有效数量 + URL加载的有效数量
        valid_imglist_count = len(imglist_images)
        valid_slot_count = len([x for x in input_images if x is not None])
        valid_url_count = len(loaded_from_urls)
        total_input_count = valid_imglist_count + valid_slot_count + valid_url_count

        # 输出实际计数：统计 merged_images 中的有效图像个数
        output_actual_count = len(merged_images)
        # 在返回前，统一把输出规范成 ComfyUI 期望的 IMAGE 张量（H,W,3） float32 范围 [0,1]
        def _to_output_tensor(obj):
            try:
                if obj is None:
                    return None

                # 将任意输入先转成 numpy array
                arr = None
                if isinstance(obj, Image.Image):
                    arr = np.array(obj.convert("RGB"))
                elif isinstance(obj, np.ndarray):
                    arr = obj.copy()
                elif 'torch' in globals() and hasattr(obj, "cpu") and hasattr(obj, "detach"):
                    try:
                        arr = obj.detach().cpu().numpy()
                    except Exception:
                        try:
                            arr = obj.cpu().numpy()
                        except Exception:
                            arr = None
                else:
                    # 尝试将其他对象转为字符串然后跳过
                    return None

                if arr is None:
                    return None

                # 如果有多余的首维为1，先 squeeze 掉
                while arr.ndim > 2 and arr.shape[0] == 1:
                    arr = arr.squeeze(0)

                # 如果还是 4D，尝试找到通道轴并移动到最后
                if arr.ndim == 4:
                    chan_axes = [i for i, s in enumerate(arr.shape) if s in (3, 4)]
                    if chan_axes:
                        arr = np.moveaxis(arr, chan_axes[0], -1)
                    # 然后再 squeeze leading singleton dims
                    while arr.ndim > 3 and arr.shape[0] == 1:
                        arr = arr.squeeze(0)

                # 处理 3D 的常见布局
                if arr.ndim == 3:
                    # channel last (H,W,3|4) -> ok
                    if arr.shape[-1] in (3, 4):
                        pass
                    # channel first (C,H,W) -> move to last
                    elif arr.shape[0] in (3, 4):
                        arr = np.moveaxis(arr, 0, -1)
                    else:
                        # 如果任一维度为3或4，尝试移动该维到最后
                        chan_axes = [i for i, s in enumerate(arr.shape) if s in (3, 4)]
                        if chan_axes:
                            arr = np.moveaxis(arr, chan_axes[0], -1)
                        else:
                            return None

                # 处理 2D 灰度
                if arr.ndim == 2:
                    arr = np.stack([arr, arr, arr], axis=-1)

                # 最终必须是 (H,W,3) 或 (H,W,4)
                if arr.ndim != 3 or arr.shape[-1] not in (3, 4):
                    return None

                # 丢弃 alpha 通道
                if arr.shape[-1] == 4:
                    arr = arr[..., :3]

                # 转为 float32 并归一化到 [0,1]
                if np.issubdtype(arr.dtype, np.integer):
                    arr = arr.astype(np.float32) / 255.0
                else:
                    arr = arr.astype(np.float32)
                    if arr.max() > 1.5:
                        arr = arr / 255.0

                # 返回 torch tensor 带 batch 维 (1,H,W,3) — 与 ComfyUI 通用节点格式一致
                return torch.from_numpy(arr)[None,]
            except Exception:
                return None

        try:
            image_list_for_export = [ _to_output_tensor(x) for x in image_list_for_export if x is not None ]
            # 为兼容下游保存/预览（save_images 期望 image.cpu().numpy() 返回 (H,W,3) 或 (C,H,W)），
            # 将图像列表中的每个 tensor 去掉领先的 batch 维，确保形状为 (H,W,3) 或 (C,H,W)。
            normalized_image_list = []
            for itm in image_list_for_export:
                try:
                    if itm is None:
                        normalized_image_list.append(None)
                        continue
                    if 'torch' in globals() and hasattr(itm, "detach"):
                        t = itm
                        # squeeze leading batch dim if present
                        if t.dim() == 4 and t.size(0) == 1:
                            t = t.squeeze(0)
                        normalized_image_list.append(t)
                    else:
                        normalized_image_list.append(itm)
                except Exception:
                    normalized_image_list.append(itm)
            image_list_for_export = normalized_image_list
            new_per_slot = []
            for x in per_slot_outputs:
                if x is None:
                    new_per_slot.append(None)
                else:
                    new_per_slot.append(_to_output_tensor(x))
            per_slot_outputs = new_per_slot
        except Exception:
            pass
        # 为保证 Preview/保存 节点能正确处理图像列表，生成一个用于 UI 的预览数组列表（numpy uint8, H,W,3）
        def _to_preview_uint8(elem):
            try:
                if elem is None:
                    return None
                arr = None
                if 'torch' in globals() and hasattr(elem, "cpu") and hasattr(elem, "detach"):
                    try:
                        arr = elem.detach().cpu().numpy()
                    except Exception:
                        arr = elem.cpu().numpy()
                elif isinstance(elem, np.ndarray):
                    arr = elem
                else:
                    return None
                # If has leading batch dim, squeeze it
                if arr.ndim == 4 and arr.shape[0] == 1:
                    arr = arr.squeeze(0)
                # If still 4D, try to move channel axis
                if arr.ndim == 4:
                    chan_axes = [i for i,s in enumerate(arr.shape) if s in (3,4)]
                    if chan_axes:
                        arr = np.moveaxis(arr, chan_axes[0], -1)
                # If channel-first (C,H,W), move to last
                if arr.ndim == 3 and arr.shape[0] in (1,3,4) and arr.shape[-1] not in (3,4):
                    arr = np.moveaxis(arr, 0, -1)
                # If 3D with channel last ok; if 2D replicate channels
                if arr.ndim == 2:
                    arr = np.stack([arr,arr,arr], axis=-1)
                if arr.ndim != 3 or arr.shape[-1] not in (3,4):
                    return None
                if arr.shape[-1] == 4:
                    arr = arr[..., :3]
                # Normalize to uint8
                if np.issubdtype(arr.dtype, np.floating):
                    if arr.max() <= 1.5:
                        out = (arr * 255.0).clip(0,255).astype(np.uint8)
                    else:
                        out = np.clip(arr,0,255).astype(np.uint8)
                else:
                    out = arr.astype(np.uint8)
                return out
            except Exception:
                return None

        try:
            preview_list = []
            for itm in image_list_for_export:
                pv = _to_preview_uint8(itm)
                preview_list.append(pv if pv is not None else None)
            # Keep the actual first output as the original tensor list (torch tensors).
            image_list_preview_output = image_list_for_export
        except Exception:
            image_list_preview_output = image_list_for_export
        # 追加诊断：记录最终导出前每个图像的实际 numpy 形状、dtype 及最小/最大值，便于定位通道/缩放问题
        try:
            final_shapes = []
            for idx, itm in enumerate(image_list_for_export):
                try:
                    if 'torch' in globals() and hasattr(itm, "cpu"):
                        arr = itm.detach().cpu().numpy()
                    elif isinstance(itm, np.ndarray):
                        arr = itm
                    else:
                        arr = None
                    if arr is not None:
                        final_shapes.append(f"idx{idx}:{arr.shape},{arr.dtype},min={float(np.min(arr)) if arr.size else None},max={float(np.max(arr)) if arr.size else None}")
                    else:
                        final_shapes.append(f"idx{idx}:UNKNOWN_TYPE")
                except Exception as _e:
                    final_shapes.append(f"idx{idx}:ERR:{_e}")
            url_results.append(f"DIAG_final_image_list_shapes: {final_shapes}")

            final_slot_shapes = []
            for idx, itm in enumerate(per_slot_outputs):
                try:
                    if itm is None:
                        final_slot_shapes.append(f"slot{idx}:None")
                        continue
                    if 'torch' in globals() and hasattr(itm, "cpu"):
                        arr = itm.detach().cpu().numpy()
                    elif isinstance(itm, np.ndarray):
                        arr = itm
                    else:
                        arr = None
                    if arr is not None:
                        final_slot_shapes.append(f"slot{idx}:{arr.shape},{arr.dtype},min={float(np.min(arr)) if arr.size else None},max={float(np.max(arr)) if arr.size else None}")
                    else:
                        final_slot_shapes.append(f"slot{idx}:UNKNOWN_TYPE")
                except Exception as _e:
                    final_slot_shapes.append(f"slot{idx}:ERR:{_e}")
            url_results.append(f"DIAG_final_slot_shapes: {final_slot_shapes}")
        except Exception:
            pass
        debug_report = "\n".join(url_results) if url_results else ""

        # 返回：第一个输出为 image_list_preview_output（便于预览/保存），同时保留原始 tensor 列表在 per_slot_outputs
        return tuple([image_list_preview_output] + per_slot_outputs + [str(total_input_count), str(output_actual_count), debug_report])

    def _ensure_list_of_images(self, image_input) -> List:
        """
        将 image_input 规范成列表并过滤 None:
        - None -> []
        - list/tuple -> 展开一层并过滤 None
        - 单张 tensor -> [tensor]
        """
        if image_input is None:
            return []
        if isinstance(image_input, (list, tuple)):
            result = []
            for itm in image_input:
                if itm is None:
                    continue
                # 如果内部还是 list/tuple，简单展开一层（避免嵌套列表造成问题）
                if isinstance(itm, (list, tuple)):
                    for sub in itm:
                        if sub is not None:
                            result.append(sub)
                else:
                    result.append(itm)
            return result
        # 单个对象直接返回列表
        return [image_input]

    def _pil_to_image_tensor(self, pil_img: Image.Image):
        """
        将 PIL.Image 转成 ComfyUI 常用的 IMAGE 张量格式 (1, H, W, 3)，dtype float32，范围 [0,1]
        """
        if pil_img.mode != "RGB":
            pil_img = pil_img.convert("RGB")
        arr = np.array(pil_img).astype(np.float32) / 255.0
        tensor = torch.from_numpy(arr)[None,]
        return tensor

    def _load_image_from_url(self, url: str) -> Image.Image:
        """
        支持从本地路径或 HTTP(S) URL 加载图像，返回 PIL.Image 或抛出异常
        """
        try:
            # 本地路径优先
            if os.path.exists(url):
                img = Image.open(url)
                img.load()
                return img

            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
            }
            resp = requests.get(url, headers=headers, timeout=10, stream=True)
            resp.raise_for_status()
            content_type = resp.headers.get("content-type", "")
            if not content_type.startswith("image/"):
                raise ValueError(f"URL 不像图像 (content-type: {content_type})")
            img = Image.open(io.BytesIO(resp.content))
            img.load()
            return img
        except Exception as e:
            # 抛出异常让调用方决定如何处理（process 中会忽略单张失败）
            raise e

    def _fetch_url_content_with_retries(self, url: str, attempts: int = 3, backoff: float = 0.5) -> bytes:
        """
        尝试多次获取 URL 内容，返回 bytes 或 None
        """
        # Use requests.Session with urllib3 Retry for robust retries
        try:
            from requests.adapters import HTTPAdapter
            from urllib3.util.retry import Retry
        except Exception:
            # fallback: simple requests loop
            header = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)", "Accept": "image/*,*/*;q=0.8"}
            for attempt in range(attempts):
                try:
                    resp = requests.get(url, headers=header, timeout=(10, 30), allow_redirects=True, stream=True)
                    resp.raise_for_status()
                    content = resp.content
                    if content and len(content) > 0:
                        return content
                except Exception:
                    try:
                        time.sleep(backoff * (attempt + 1))
                    except Exception:
                        pass
            return None

        session = requests.Session()
        retries = Retry(total=attempts, backoff_factor=backoff, status_forcelist=(429, 500, 502, 503, 504), allowed_methods=frozenset(['GET','HEAD']))
        adapter = HTTPAdapter(max_retries=retries)
        session.mount('http://', adapter)
        session.mount('https://', adapter)

        header_variants = [
            {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)", "Accept": "image/*,*/*;q=0.8"},
            {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36", "Accept": "image/*,*/*;q=0.8"},
            {"User-Agent": "curl/7.68.0", "Accept": "*/*", "Connection": "close"},
        ]

        last_exc = None
        for attempt in range(attempts):
            for headers in header_variants:
                # set referer
                try:
                    from urllib.parse import urlparse
                    parsed = urlparse(url)
                    if parsed.scheme and parsed.netloc:
                        headers["Referer"] = f"{parsed.scheme}://{parsed.netloc}/"
                except Exception:
                    pass

                try:
                    # Try HEAD first to check availability / content-length
                    try:
                        head = session.head(url, headers=headers, timeout=(10, 15), allow_redirects=True)
                        head.raise_for_status()
                        cl = head.headers.get('content-length')
                        ct = head.headers.get('content-type', '')
                        if cl is not None and int(cl) == 0:
                            # no content according to HEAD
                            last_exc = Exception("HEAD content-length 0")
                            continue
                    except Exception:
                        # HEAD may fail (405/others), proceed to GET
                        pass

                    resp = session.get(url, headers=headers, timeout=(10, 60), allow_redirects=True, stream=True)
                    resp.raise_for_status()
                    # read content in chunks
                    chunks = []
                    for chunk in resp.iter_content(chunk_size=32768):
                        if chunk:
                            chunks.append(chunk)
                    content = b"".join(chunks)
                    if content and len(content) > 0:
                        return content
                    else:
                        last_exc = Exception(f"empty content, status={resp.status_code}")
                except Exception as e:
                    last_exc = e
                    try:
                        time.sleep(backoff * (attempt + 1))
                    except Exception:
                        pass
                    continue
        return None

    def _empty_image_tensor(self, height: int = 64, width: int = 64):
        """
        返回一个小的空白图像张量（IMAGE 格式），避免返回 None 导致下游节点报错。
        """
        arr = np.zeros((height, width, 3), dtype=np.float32)
        tensor = torch.from_numpy(arr)[None,]
        return tensor


