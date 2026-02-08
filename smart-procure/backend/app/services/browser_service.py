"""
浏览器自动化服务 - 使用 Playwright 实现无头浏览器功能
"""
import asyncio
from typing import Optional, Dict, Any, List
from playwright.async_api import async_playwright, Browser, Page


class BrowserService:
    """无头浏览器服务"""

    # 内容长度限制
    MAX_TEXT_LENGTH = 10000
    MAX_LINKS = 50

    # 默认超时(毫秒)
    DEFAULT_TIMEOUT = 30000

    async def browse_page(
        self,
        url: str,
        extract_text: bool = True,
        extract_links: bool = False,
        timeout: int = DEFAULT_TIMEOUT
    ) -> Dict[str, Any]:
        """
        访问页面并提取内容

        Args:
            url: 目标 URL
            extract_text: 是否提取文本内容
            extract_links: 是否提取链接
            timeout: 超时时间(毫秒)

        Returns:
            {"success": bool, "title": str, "text": str, "links": list, "error": str}
        """
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                )
                page = await context.new_page()
                page.set_default_timeout(timeout)

                # 访问页面
                await page.goto(url, wait_until="domcontentloaded")

                # 获取标题
                title = await page.title()

                # 提取文本
                text = ""
                if extract_text:
                    text = await page.inner_text("body")
                    if len(text) > self.MAX_TEXT_LENGTH:
                        text = text[:self.MAX_TEXT_LENGTH] + "...(内容已截断)"

                # 提取链接
                links = []
                if extract_links:
                    link_elements = await page.query_selector_all("a[href]")
                    for link in link_elements[:self.MAX_LINKS]:
                        href = await link.get_attribute("href")
                        link_text = await link.inner_text()
                        if href and link_text.strip():
                            links.append({"text": link_text.strip()[:100], "href": href})

                await browser.close()

                return {
                    "success": True,
                    "title": title,
                    "text": text,
                    "links": links,
                    "error": None
                }

        except Exception as e:
            return {
                "success": False,
                "title": None,
                "text": None,
                "links": [],
                "error": str(e)
            }

    async def search_baidu(self, query: str, max_results: int = 5) -> Dict[str, Any]:
        """
        使用百度搜索并提取结果

        Args:
            query: 搜索关键词
            max_results: 最大结果数

        Returns:
            {"success": bool, "results": list, "error": str}
        """
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                )
                page = await context.new_page()
                page.set_default_timeout(self.DEFAULT_TIMEOUT)

                # 访问百度
                search_url = f"https://www.baidu.com/s?wd={query}"
                await page.goto(search_url, wait_until="domcontentloaded")

                # 等待搜索结果加载
                await page.wait_for_selector(".result", timeout=10000)

                # 提取搜索结果
                results = []
                result_elements = await page.query_selector_all(".result")

                for elem in result_elements[:max_results]:
                    try:
                        title_elem = await elem.query_selector("h3 a")
                        if title_elem:
                            title = await title_elem.inner_text()
                            href = await title_elem.get_attribute("href")

                            # 提取摘要
                            abstract = ""
                            abstract_elem = await elem.query_selector(".c-abstract")
                            if abstract_elem:
                                abstract = await abstract_elem.inner_text()

                            results.append({
                                "title": title.strip(),
                                "url": href,
                                "abstract": abstract.strip()[:200]
                            })
                    except:
                        continue

                await browser.close()

                return {
                    "success": True,
                    "query": query,
                    "results": results,
                    "count": len(results),
                    "error": None
                }

        except Exception as e:
            return {
                "success": False,
                "query": query,
                "results": [],
                "count": 0,
                "error": str(e)
            }


# 同步包装函数，供非异步环境调用
def browse_page_sync(url: str, extract_text: bool = True, extract_links: bool = False) -> Dict[str, Any]:
    """同步版本的页面浏览"""
    service = BrowserService()
    return asyncio.run(service.browse_page(url, extract_text, extract_links))


def search_baidu_sync(query: str, max_results: int = 5) -> Dict[str, Any]:
    """同步版本的百度搜索"""
    service = BrowserService()
    return asyncio.run(service.search_baidu(query, max_results))
