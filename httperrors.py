import json
import urllib.parse
from pathlib import Path

# ========== 分类规则（可自定义） ==========
CRITICAL_PATTERNS = {
    "url_keywords": [
        "/main.", "/app.", "/index", "/home", "/login", "/auth", "/api/video",
        "/api/feed", "/api/user/", "/api/post/", "/graphql", "/products",
        "/checkout", "/cart", "/payment", "/videoplayback", ".m3u8", ".mp4"
    ],
    "status_codes": [403, 404, 500, 502, 503, 504],
    "resource_types": ["document", "script", "stylesheet", "media"],
    "domains": ["googlevideo.com", "youtube.com", "yt3.ggpht.com"]
}

NON_CRITICAL_PATTERNS = {
    "url_keywords": [
        "/log", "/track", "/analytics", "/metrics", "/beacon", "/telemetry",
        "/ads", "/adserver", "/doubleclick", "/facebook.com/tr", "/google-analytics",
        "/hotjar", "/clarity", "/sentry", "/cdn-cgi/", "/inbox/notice", "/ws/", "/socket"
    ],
    "status_codes": [101, 204, 304],
    "resource_types": ["image", "font", "websocket", "ping", "other"],
    "domains": [
        "google-analytics.com", "googletagmanager.com", "facebook.com",
        "doubleclick.net", "hotjar.com", "sentry.io"
    ]
}

ERROR_SUGGESTIONS = {
    400: "Bad Request - 请求参数错误或Header过大。",
    401: "Unauthorized - 缺少认证令牌。",
    403: "Forbidden - IP被封、权限不足或WAF拦截。",
    404: "Not Found - URL路径错误或资源已迁移。",
    408: "Request Timeout - 服务器等待超时。",
    429: "Too Many Requests - 请求频率过高。",
    500: "Internal Server Error - 后端代码异常。",
    502: "Bad Gateway - 上游服务无响应。",
    503: "Service Unavailable - 服务过载或维护。",
    504: "Gateway Timeout - 网关等待上游超时。",
    "net::ERR_CONNECTION_TIMED_OUT": "❗ **连接超时**：目标服务器无响应。\n    🛠️ 排障：1) ping 域名；2) 关闭代理/VPN；3) 更换DNS；4) 检查防火墙/安全软件。",
    "net::ERR_CONNECTION_REFUSED": "连接被拒绝 - 端口未开放或服务未启动。",
    "net::ERR_NAME_NOT_RESOLVED": "DNS解析失败 - 域名不存在或DNS异常。",
    "net::ERR_CONNECTION_RESET": "连接被重置 - 中间设备拦截。",
    "net::ERR_ABORTED_OR_INCOMPLETE": "请求被取消或未完成 - 可能是页面关闭或资源被跳过。",
}

def get_suggestion(error_code, error_text=""):
    if error_code and isinstance(error_code, int):
        return ERROR_SUGGESTIONS.get(error_code, f"HTTP {error_code}，请查阅RFC。")
    for key, msg in ERROR_SUGGESTIONS.items():
        if isinstance(key, str) and key in error_text:
            return msg
    if "TIMED_OUT" in error_text or "timeout" in error_text.lower():
        return ERROR_SUGGESTIONS["net::ERR_CONNECTION_TIMED_OUT"]
    return "未知网络错误，请结合Console日志分析。"

def categorize_error(entry, domain, url, status, error_text):
    url_lower = url.lower()
    domain_lower = domain.lower()
    resource_type = entry.get('_resourceType', '').lower() or ''

    for kw in NON_CRITICAL_PATTERNS["url_keywords"]:
        if kw in url_lower:
            return 'non_critical'
    for dom in NON_CRITICAL_PATTERNS["domains"]:
        if dom in domain_lower:
            return 'non_critical'
    if status in NON_CRITICAL_PATTERNS["status_codes"]:
        return 'non_critical'
    if resource_type in NON_CRITICAL_PATTERNS["resource_types"]:
        return 'non_critical'

    for kw in CRITICAL_PATTERNS["url_keywords"]:
        if kw in url_lower:
            return 'critical'
    for dom in CRITICAL_PATTERNS["domains"]:
        if dom in domain_lower:
            return 'critical'
    if status in CRITICAL_PATTERNS["status_codes"]:
        return 'critical'
    if resource_type in CRITICAL_PATTERNS["resource_types"]:
        return 'critical'

    return 'critical'

def detect_network_error(entry):
    status = entry.get('response', {}).get('status', 0)
    error_text = entry.get('_error', '')
    timings = entry.get('timings', {})
    
    if error_text:
        return True, error_text

    if status == 0:
        connect_time = timings.get('connect', -1)
        wait_time = timings.get('wait', -1)
        receive_time = timings.get('receive', -1)
        if connect_time > 30000 or wait_time > 30000 or receive_time > 30000:
            return True, "net::ERR_CONNECTION_TIMED_OUT (detected from timings)"
        if connect_time == -1 and wait_time == -1:
            return True, "net::ERR_CONNECTION_REFUSED_OR_DNS_FAILURE"
        return True, "net::ERR_ABORTED_OR_INCOMPLETE"

    url = entry.get('request', {}).get('url', '')
    content_type = entry.get('response', {}).get('content', {}).get('mimeType', '')
    if ('googlevideo' in url or 'videoplayback' in url) and status in [200, 206]:
        if 'video' not in content_type:
            return True, "MEDIA_BLOCKED - 服务器返回非视频内容（可能是错误页面）"

    return False, ""

def parse_har(har_path):
    with open(har_path, 'r', encoding='utf-8') as f:
        har_data = json.load(f)

    entries = har_data.get('log', {}).get('entries', [])
    critical_dict = {}   # domain -> err_item
    non_critical_dict = {}
    critical_domains = set()
    non_critical_domains = set()

    for entry in entries:
        request = entry.get('request', {})
        url = request.get('url', '')
        domain = urllib.parse.urlparse(url).netloc or url
        response = entry.get('response', {})
        status = response.get('status', 0)
        
        is_network_err, net_err_desc = detect_network_error(entry)
        is_http_err = 400 <= status <= 599
        
        if is_network_err or is_http_err:
            if is_http_err:
                err_msg = f"HTTP {status}"
                suggestion = get_suggestion(status)
            else:
                err_msg = net_err_desc
                suggestion = get_suggestion(0, net_err_desc)
            
            err_item = {
                'url': url,
                'domain': domain,
                'status': status if status != 0 else 'Network Error',
                'error': err_msg,
                'suggestion': suggestion,
                'resource_type': entry.get('_resourceType', '未知')
            }
            category = categorize_error(entry, domain, url, status, err_msg)
            
            if category == 'critical':
                critical_domains.add(domain)
                if domain not in critical_dict:   # 只保留第一次出现的错误
                    critical_dict[domain] = err_item
            else:
                non_critical_domains.add(domain)
                if domain not in non_critical_dict:
                    non_critical_dict[domain] = err_item

    # 将字典转换为列表（顺序可能乱，但没关系）
    critical_list = list(critical_dict.values())
    non_critical_list = list(non_critical_dict.values())
    return critical_list, non_critical_list, critical_domains, non_critical_domains

def write_report(critical_list, non_critical_list, critical_domains, non_critical_domains, output_path='filtered_errors.txt'):
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write("=" * 80 + "\n")
        f.write("【网络请求异常报告 - 域名去重版】\n")
        f.write(f"总计异常域名: {len(critical_domains) + len(non_critical_domains)} 个\n")
        f.write(f"  - 关键域名: {len(critical_domains)}\n")
        f.write(f"  - 非关键域名: {len(non_critical_domains)}\n")
        f.write("=" * 80 + "\n\n")

        # 1. 去重域名列表
        f.write("🌐 【问题域名汇总（去重）】\n")
        f.write("-" * 80 + "\n")
        f.write("🚨 关键域名（影响核心功能）：\n")
        if critical_domains:
            for dom in sorted(critical_domains):
                f.write(f"  {dom}\n")
        else:
            f.write("  无\n")
        f.write("\n📌 非关键域名（可忽略或次要影响）：\n")
        if non_critical_domains:
            for dom in sorted(non_critical_domains):
                f.write(f"  {dom}\n")
        else:
            f.write("  无\n")
        f.write("=" * 80 + "\n\n")

        # 2. 关键错误详情（每个域名一条）
        if critical_list:
            f.write("🚨 【关键错误详情】（每个域名只展示第一条错误）\n")
            f.write("-" * 80 + "\n")
            for idx, err in enumerate(critical_list, 1):
                f.write(f"[{idx}] 域名：{err['domain']}\n")
                f.write(f"    资源类型：{err['resource_type']}\n")
                f.write(f"    URL：{err['url']}\n")
                f.write(f"    错误：{err['status']} - {err['error']}\n")
                f.write(f"    排障建议：{err['suggestion']}\n")
                f.write("-" * 80 + "\n")
        else:
            f.write("🚨 关键错误：✅ 未发现\n\n")

        # 3. 非关键错误详情（每个域名一条）
        if non_critical_list:
            f.write("\n📌 【非关键错误详情】（每个域名只展示第一条错误）\n")
            f.write("-" * 80 + "\n")
            for idx, err in enumerate(non_critical_list, 1):
                f.write(f"[{idx}] 域名：{err['domain']}\n")
                f.write(f"    资源类型：{err['resource_type']}\n")
                f.write(f"    URL：{err['url'][:150]}...\n")
                f.write(f"    错误：{err['status']} - {err['error']}\n")
                f.write(f"    说明：此错误不影响页面核心访问。\n")
                f.write("-" * 80 + "\n")
        else:
            f.write("📌 非关键错误：✅ 无\n")

    print(f"✅ 报告已生成：{Path(output_path).absolute()}")
    print(f"   关键域名 {len(critical_domains)} 个，非关键域名 {len(non_critical_domains)} 个")
    print(f"   关键错误条目 {len(critical_list)} 条（已去重），非关键错误条目 {len(non_critical_list)} 条（已去重）")

if __name__ == '__main__':
    import sys
    if len(sys.argv) != 2:
        print("用法：python har_analyzer.py <your_export.har>")
        sys.exit(1)
    har_file = sys.argv[1]
    if not Path(har_file).exists():
        print(f"文件不存在：{har_file}")
        sys.exit(1)

    critical_list, non_critical_list, critical_domains, non_critical_domains = parse_har(har_file)
    write_report(critical_list, non_critical_list, critical_domains, non_critical_domains)