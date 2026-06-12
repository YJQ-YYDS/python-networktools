# python-changenetwork

> 快速修改网卡信息的一个脚本集合

## 📁 文件列表

### [ChangeNetwork.py](ChangeNetwork.py)

**功能说明**：

1. 快速禁用/启用网卡
2. 修改网卡模式（DHCP / 静态）
3. 修改网卡 IP 等信息（支持保存配置、一键加载）
4. 内置掩码计算器，一键计算掩码位并可复制

需要安装python管理器使用，默认安装到c盘，打开cmd管理员运行使用
（建议单独c盘创建一个文件夹"py"，脚本放到py文件夹下，命令行“cd /py/ ”目录下运行脚本）  
cd /py/  
python ChangeNetwork.py  
运行后内置有帮助说明功能菜单

---

### [httperrors.py](httperrors.py)

**功能说明**：

浏览器 F12 辅助脚本 – 捕获并展示 HTTP 错误状态码（如 4xx、5xx），便于前端/后端调试。
需要安装python管理器使用，默认安装到c盘，脚本目录和导出文件放一个目录里；打开cmd管理员运行使用
浏览器F12导出HAR文件分析网络请求异常脚本
httperrors.py
python httperrors.py 导出的HAR文件名

浏览器导出HAR文件操作流程总览
1.打开目标网页，按下 F12 → 切换到 Network 标签页
2.勾选“Preserve log”（保留日志），确保记录跳转或刷新前的请求
3.正常浏览网页，直到问题复现，点击停止加载
4.点击 Export HAR（导出为 .har 文件）下载标识

---

### [export_domains.py](export_domains.py)

**功能说明**：

浏览器 F12 辅助脚本 – 从浏览器开发者工具导出的请求记录中提取所有请求的域名，并去重输出。
需要安装python管理器使用，默认安装到c盘，脚本目录和导出文件放一个目录里；打开cmd管理员运行使用
浏览器F12导出har文件过滤网络请求所有域名脚本
export_domains.py 
python httperrors.py 导出的HAR文件名

浏览器导出HAR文件操作流程总览
1.打开目标网页，按下 F12 → 切换到 Network 标签页
2.勾选“Preserve log”（保留日志），确保记录跳转或刷新前的请求
3.正常浏览网页，直到问题复现，点击停止加载
4.点击 Export HAR（导出为 .har 文件）下载标识

---

## 🛠 使用场景

适用于需要频繁切换网络配置、调试 HTTP 错误或导出浏览器域名信息的开发与运维工作。

---

## 📄 贡献来源

DeepSeek
