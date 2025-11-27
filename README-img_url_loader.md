# 图像URL加载器 (Image URL Loader)

ComfyUI 自定义节点，用于从 URL 链接或本地文件路径加载图像。

## 功能特性

- 📥 支持 HTTP/HTTPS URL 图像链接
- 💾 支持本地文件路径
- ✅ 自动验证图像有效性和格式
- 🔄 批量处理多个图像链接
- ⚠️ 自定义错误处理和异常抛出
- 📊 输出图像链接统计信息

## 安装

1. 将此文件夹复制到 ComfyUI 的 `custom_nodes` 目录下

2. 安装依赖：
   ```bash
   pip install -r requirements.txt
   ```

3. 重启 ComfyUI

## 使用方法

1. 在 ComfyUI 工作流中找到 `WZF_laowangtools` 分类
2. 添加 `图像URL加载器` 节点
3. 在 `imgurl` 输入框中输入图像链接，每行一个：
   ```
   https://example.com/image1.jpg
   https://example.com/image2.png
   /path/to/local/image.jpg
   ```

## 输入参数

| 参数名 | 类型 | 说明 | 默认值 |
|--------|------|------|--------|
| `imgurl` | STRING (多行) | 图像URL链接或本地文件路径，每行一个 | 空字符串 |
| `error_message` | STRING | 当没有找到有效图像时显示的错误消息 | "未找到有效的图像链接" |
| `throw_error` | BOOLEAN | 是否在找不到有效图像时抛出系统异常 | False |

## 输出参数

| 输出名 | 类型 | 说明 |
|--------|------|------|
| `图像列表` | IMAGE | 所有有效图像的列表（已转换为 ComfyUI IMAGE 格式） |
| `报错显示` | STRING | 状态消息：有效链接≥1时显示"OK"，否则显示自定义错误消息 |
| `有效图像链接数量` | STRING | 成功加载的有效图像数量 |
| `输入端imgurl图像链接总数量` | STRING | 输入的图像链接总数（包括无效的） |

## 使用示例

### 示例 1：加载单个URL图像
```
imgurl: https://example.com/sample.jpg
error_message: 未找到有效的图像链接
throw_error: False
```

### 示例 2：批量加载多个图像
```
imgurl: 
https://example.com/image1.jpg
https://example.com/image2.png
https://example.com/image3.jpg

error_message: 没有找到可用的图像
throw_error: False
```

### 示例 3：混合URL和本地路径
```
imgurl:
https://example.com/remote.jpg
C:/Users/Administrator/Desktop/local.jpg
./images/local.png

error_message: 图像加载失败
throw_error: False
```

### 示例 4：启用异常抛出
```
imgurl: https://example.com/image.jpg
error_message: 无法加载图像，请检查链接
throw_error: True
```
当找不到有效图像时，系统会抛出异常，停止工作流执行。

## 支持的图像格式

- JPEG (.jpg, .jpeg)
- PNG (.png)
- GIF (.gif)
- BMP (.bmp)
- WebP (.webp)
- 其他 PIL/Image 支持的格式

## 技术说明

- 节点会自动将图像转换为 RGB 模式
- 图像会被归一化到 [0, 1] 范围（除以 255.0）
- 所有图像会被合并为一个批次张量
- 对于 URL 请求，默认超时时间为 10 秒

## 错误处理

- **有效链接数量 ≥ 1**：返回"OK"，输出图像列表
- **有效链接数量 < 1**：
  - 如果 `throw_error = False`：返回自定义错误消息，输出空图像列表
  - 如果 `throw_error = True`：抛出系统异常，停止工作流

## 注意事项

1. 确保网络连接正常，以便加载远程URL图像
2. 本地文件路径需要确保 ComfyUI 有读取权限
3. 大型图像可能会占用较多内存
4. 多个图像的尺寸可能会不同，但都会正常加载

## 依赖项

- torch >= 1.0.0
- requests >= 2.25.0
- Pillow >= 8.0.0
- numpy >= 1.19.0

## 许可证

请根据您的项目许可证进行使用。

## 更新日志

### v1.0.0
- 初始版本发布
- 支持 URL 和本地文件路径加载
- 支持批量图像处理
- 错误处理和异常抛出功能

