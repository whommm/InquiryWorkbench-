"""
网络搜索服务 - 使用 Tavily API 搜索供应商信息
"""
import os
import requests
from typing import List, Dict, Optional


def search_suppliers_online(brand_name: str, max_results: int = 5) -> List[Dict]:
    """
    在互联网上搜索品牌的供应商、代理商、经销商信息

    Args:
        brand_name: 品牌名称，例如 "西门子"、"ABB"
        max_results: 最多返回结果数量

    Returns:
        搜索结果列表，每个结果包含 title, url, content
    """
    api_key = os.getenv("TAVILY_API_KEY")

    if not api_key or api_key == "your_tavily_api_key_here":
        print("警告：未配置 TAVILY_API_KEY，网络搜索功能不可用")
        return []

    # 构造搜索查询 - 针对中国市场的供应商搜索
    query = f"{brand_name} 中国 代理商 经销商 供应商 联系方式 电话"

    try:
        response = requests.post(
            "https://api.tavily.com/search",
            json={
                "api_key": api_key,
                "query": query,
                "search_depth": "basic",  # basic 或 advanced
                "max_results": max_results,
                "include_answer": False,  # 不需要 AI 生成的答案
                "include_raw_content": False,  # 不需要原始HTML
            },
            timeout=10  # 10秒超时
        )

        if response.status_code != 200:
            print(f"Tavily API 错误: {response.status_code} - {response.text}")
            return []

        data = response.json()
        results = data.get("results", [])

        # 格式化结果
        formatted_results = []
        for r in results:
            formatted_results.append({
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "content": r.get("content", "")[:300]  # 限制内容长度
            })

        return formatted_results

    except requests.exceptions.Timeout:
        print("Tavily API 请求超时")
        return []
    except Exception as e:
        print(f"网络搜索错误: {e}")
        return []


def format_search_results(brand: str, results: List[Dict]) -> str:
    """
    格式化搜索结果为可读的文本

    Args:
        brand: 品牌名称
        results: 搜索结果列表

    Returns:
        格式化后的文本
    """
    if not results:
        return f"未找到'{brand}'的供应商信息。建议尝试其他搜索方式或直接联系品牌官方。"

    output = f"🔍 已为您搜索到 {len(results)} 条'{brand}'的供应商信息：\n\n"

    for i, r in enumerate(results, 1):
        title = r.get("title", "未知标题")
        url = r.get("url", "")
        content = r.get("content", "")

        output += f"{i}. **{title}**\n"
        if content:
            output += f"   {content}\n"
        if url:
            output += f"   🌐 {url}\n"
        output += "\n"

    output += "💡 提示：点击链接查看详细信息，或直接拨打电话联系供应商。"

    return output
