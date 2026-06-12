import json
import urllib.parse
from pathlib import Path

def extract_domains_from_har(har_path):
    """从 HAR 文件中提取所有请求的去重域名"""
    with open(har_path, 'r', encoding='utf-8') as f:
        har_data = json.load(f)
    
    domains = set()
    entries = har_data.get('log', {}).get('entries', [])
    
    for entry in entries:
        url = entry.get('request', {}).get('url', '')
        if url:
            domain = urllib.parse.urlparse(url).netloc
            if domain:
                domains.add(domain)
    
    return sorted(domains)

def save_domains(domains, output_path='domains.txt'):
    with open(output_path, 'w', encoding='utf-8') as f:
        for domain in domains:
            f.write(domain + '\n')
    print(f"✅ 共提取 {len(domains)} 个唯一域名，已保存至：{Path(output_path).absolute()}")

if __name__ == '__main__':
    import sys
    if len(sys.argv) < 2:
        print("用法：python extract_domains.py <your_export.har> [输出文件名]")
        print("示例：python extract_domains.py www.youtube.com.har")
        print("      python extract_domains.py www.youtube.com.har my_domains.txt")
        sys.exit(1)
    
    har_file = sys.argv[1]
    if not Path(har_file).exists():
        print(f"文件不存在：{har_file}")
        sys.exit(1)
    
    output_file = sys.argv[2] if len(sys.argv) > 2 else 'domains.txt'
    domains = extract_domains_from_har(har_file)
    save_domains(domains, output_file)