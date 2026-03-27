"""
@description: 使用DecryptLogin爬取京东商品评价
@dependencies: DecryptLogin
@last_modified: 2026-03-16
"""

from DecryptLogin import login
import requests
import json
import time
from pathlib import Path

def login_jingdong():
    """京东登录（需要扫码）"""
    lg = login.Login()

    # 使用二维码登录
    info = lg.jingdong(
        login_way='qr',
        mode='pc',
        crack_captcha=False,
    )

    return info

def get_product_reviews(session, product_id, page=1):
    """获取商品评价"""
    url = f"https://club.jd.com/comment/productCommentSummaries.action?referenceIds={product_id}"

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Referer': f'https://item.jd.com/{product_id}.html'
    }

    try:
        r = session.get(url, headers=headers, timeout=15)
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        print(f"获取评价失败: {e}")

    return None

def main():
    """主函数"""
    output_dir = Path(".ai-state/competitive_analysis")
    output_dir.mkdir(parents=True, exist_ok=True)

    print("=== 京东商品评价采集 ===\n")
    print("注意: 首次使用需要扫码登录京东")
    print("      登录信息会被缓存，后续无需重复登录\n")

    try:
        # 尝试登录
        print("正在登录京东...")
        session, info = login_jingdong()

        if session and info:
            print(f"登录成功！用户: {info.get('nick', '未知')}")

            # 获取影目Air3评价
            product_id = "100070432376"
            print(f"\n正在获取商品 {product_id} 的评价...")

            reviews = get_product_reviews(session, product_id)

            if reviews:
                with open(output_dir / "jd_reviews.json", 'w', encoding='utf-8') as f:
                    json.dump(reviews, f, ensure_ascii=False, indent=2)
                print("评价数据已保存")
            else:
                print("获取评价失败")
        else:
            print("登录失败")

    except Exception as e:
        print(f"错误: {e}")
        print("\n提示: 如果登录失败，可以尝试:")
        print("1. 确保网络正常")
        print("2. 删除缓存的登录信息后重试")
        print("   缓存位置: ~/.decryptlogin/")

if __name__ == "__main__":
    main()