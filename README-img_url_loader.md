# 图像URL加载器 (Image URL Loader)

ComfyUI 自定义节点，用于从 URL 链接或本地文件路径加载图像。

## 功能特性

- 📥 支持 HTTP/HTTPS URL 图像链接
- 💾 支持本地文件路径
- ✅ 自动验证图像有效性和格式
- 🔄 批量处理多个图像链接
- ⚠️ 自定义错误处理和异常抛出
- 📊 输出图像链接统计信息
- 🛡️ **智能异常分类**：区分代理错误与其他网络异常
- ⚡ **快速失败机制**：代理问题不再浪费时间重试
- 🔧 **优化超时策略**：分层超时，适应不同网络环境
- 🐛 **详细调试信息**：便于排查网络问题

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
- **智能异常处理**：
  - `ProxyError`：立即失败，避免浪费时间重试代理问题
  - `SSLError`：尝试降级到无证书验证
  - `ConnectionError/Timeout`：正常重试机制
- **分层超时策略**：
  - HEAD检查：(5, 10)秒 - 快速检测资源可用性
  - GET下载：(10, 25)秒 - 允许正常图片下载
  - 总超时：40秒 - 避免无限等待
- 下载鲁棒性说明：
  - 节点已增强为使用稳健的下载策略以提升对 OSS/CDN 的兼容性与容错性：使用 requests.Session + urllib3.Retry 的重试机制、HEAD 预检（若服务器支持）、流式分块读取和多种 User-Agent/Referer header 尝试来避开常见的防盗链和短暂网络故障。
  - **新增智能异常分类**：区分代理错误与其他网络异常，代理问题不再进行无意义重试。
  - 在某些不可达或被限制的情况下（如私有 OSS bucket、需要签名的资源或特殊 Cookie），节点仍可能无法直接下载图片；此时请提供预签名 URL 或开启相应权限。
  - 节点内部实现对 PIL 打开失败有回退尝试，会尽量保证能加载可用图像并将失败 URL 记录在错误输出中（不影响其他有效图像加载）。
  - **新增详细调试信息**：控制台输出详细的下载过程，便于排查网络问题。

## 错误处理

- **有效链接数量 ≥ 1**：返回"OK"，输出图像列表
- **有效链接数量 < 1**：
  - 如果 `throw_error = False`：返回自定义错误消息，输出空图像列表
  - 如果 `throw_error = True`：抛出系统异常，停止工作流

### 智能异常分类

- **ProxyError（代理错误）**：立即失败，不重试
  - 原因：代理配置问题，重试无意义
  - 处理：检测到即终止，避免浪费时间
- **SSLError（SSL证书错误）**：尝试降级处理
  - 原因：证书过期、自签名等
  - 处理：先尝试正常SSL，失败后使用`verify=False`
- **ConnectionError/Timeout（连接超时）**：正常重试
  - 原因：网络波动、服务器负载
  - 处理：指数退避重试机制

## 调试建议（当图片无法加载时）

### 控制台调试信息
节点运行时会在控制台输出详细的调试信息：
```
[DEBUG] Starting _fetch_url_content_with_retries: URL=...
[DEBUG] Using enhanced Session approach with 2 attempts
[DEBUG] Starting attempt 1/2, elapsed: 0.0s
[DEBUG] Trying header variant 1/3: Mozilla/5.0...
[DEBUG] HEAD check with SSL verification...
[DEBUG] HEAD success: status=200, content-length=...
[DEBUG] GET request with SSL verification...
[DEBUG] GET success: status=200
[DEBUG] Download successful: XXXX bytes
[DEBUG] Processing content with PIL...
[DEBUG] PIL success: JPEG (XXXX, XXXX)
```

### 常见问题排查

1. **ProxyError代理错误**：
   - 控制台显示：`[DEBUG] HEAD proxy error detected`
   - 原因：网络代理配置问题
   - 解决：检查系统代理设置，或使用无代理环境

2. **SSLError证书错误**：
   - 控制台显示：`[DEBUG] HEAD SSL error` → `[DEBUG] Retrying HEAD without SSL`
   - 原因：网站SSL证书问题
   - 处理：节点会自动尝试无证书验证

3. **普通网络超时**：
   - 控制台显示：`[DEBUG] HEAD network exception: Timeout`
   - 原因：网络连接慢或目标服务器响应慢
   - 处理：节点会重试不同header组合

4. **基本URL检查**：
   - 在运行节点的同一台机器上使用 curl 检查 URL：
     ```bash
     curl -I "https://your.url/image.png"
     ```
   - 如果 HEAD 返回 403/401/404，说明权限或路径问题
   - 如果返回 200 且 content-length > 0，则下载一般可行

5. **代理环境问题**：
   - 如果你在内部网络或代理后面运行 ComfyUI，确保代理设置允许访问目标域名
   - 示例：`oss-cn-hangzhou.aliyuncs.com`

6. **私有资源访问**：
   - 对私有 OSS 对象，请使用预签名 URL（presigned URL）
   - 或在节点外部通过授权方式获取可访问链接


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

### v1.1.0
- 🛡️ **智能异常分类**：区分ProxyError等不同网络异常类型
- ⚡ **快速失败机制**：代理问题不再进行无意义重试
- 🔧 **优化超时策略**：分层超时(HEAD:5-10s, GET:10-25s, 总超时:40s)
- 🐛 **详细调试信息**：控制台输出完整的下载过程，便于排查问题
- 📈 **性能提升**：在网络受限环境下显著减少等待时间

### v1.0.0
- 初始版本发布
- 支持 URL 和本地文件路径加载
- 支持批量图像处理
- 错误处理和异常抛出功能

