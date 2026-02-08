"""
浏览器自动化服务 - 使用 Playwright 同步 API 实现无头浏览器功能
"""
from typing import Dict, Any, List
from playwright.sync_api import sync_playwright
from concurrent.futures import ThreadPoolExecutor
import functools

# 全局线程池，用于在异步环境中运行同步的 Playwright 代码
_executor = ThreadPoolExecutor(max_workers=2)


class BrowserService:
    """无头浏览器服务（同步版本）"""

    # 内容长度限制
    MAX_TEXT_LENGTH = 10000
    MAX_LINKS = 50

    # 默认超时(毫秒)
    DEFAULT_TIMEOUT = 30000

    def browse_page(
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
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                )
                page = context.new_page()
                page.set_default_timeout(timeout)

                # 访问页面
                page.goto(url, wait_until="domcontentloaded")

                # 获取标题
                title = page.title()

                # 提取文本
                text = ""
                if extract_text:
                    text = page.inner_text("body")
                    if len(text) > self.MAX_TEXT_LENGTH:
                        text = text[:self.MAX_TEXT_LENGTH] + "...(内容已截断)"

                # 提取链接
                links = []
                if extract_links:
                    link_elements = page.query_selector_all("a[href]")
                    for link in link_elements[:self.MAX_LINKS]:
                        href = link.get_attribute("href")
                        link_text = link.inner_text()
                        if href and link_text.strip():
                            links.append({"text": link_text.strip()[:100], "href": href})

                browser.close()

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

    def search_baidu(self, query: str, max_results: int = 5) -> Dict[str, Any]:
        """
        使用百度搜索并提取结果

        Args:
            query: 搜索关键词
            max_results: 最大结果数

        Returns:
            {"success": bool, "results": list, "error": str}
        """
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                )
                page = context.new_page()
                page.set_default_timeout(self.DEFAULT_TIMEOUT)

                # 访问百度
                search_url = f"https://www.baidu.com/s?wd={query}"
                page.goto(search_url, wait_until="domcontentloaded")

                # 等待页面加载，尝试多个选择器
                selectors = ["#content_left", ".c-container", ".result", "#wrapper"]
                loaded = False
                for selector in selectors:
                    try:
                        page.wait_for_selector(selector, timeout=5000)
                        loaded = True
                        break
                    except:
                        continue

                if not loaded:
                    # 如果都找不到，等待一下再继续
                    page.wait_for_timeout(2000)

                # 提取搜索结果 - 尝试多种选择器
                results = []
                result_selectors = [".c-container", ".result", "[class*='result']"]
                result_elements = []

                for selector in result_selectors:
                    result_elements = page.query_selector_all(selector)
                    if result_elements:
                        break

                for elem in result_elements[:max_results]:
                    try:
                        # 尝试多种标题选择器
                        title_elem = elem.query_selector("h3 a") or elem.query_selector("a h3") or elem.query_selector("h3")
                        if title_elem:
                            title = title_elem.inner_text()
                            # 获取链接
                            link_elem = elem.query_selector("a[href]")
                            href = link_elem.get_attribute("href") if link_elem else ""

                            # 提取摘要 - 尝试多种选择器
                            abstract = ""
                            for abs_selector in [".c-abstract", ".c-span-last", "[class*='abstract']", "span"]:
                                abstract_elem = elem.query_selector(abs_selector)
                                if abstract_elem:
                                    abstract = abstract_elem.inner_text()
                                    if len(abstract) > 20:
                                        break

                            if title.strip():
                                results.append({
                                    "title": title.strip(),
                                    "url": href,
                                    "abstract": abstract.strip()[:200]
                                })
                    except:
                        continue

                # 如果没有提取到结果，尝试直接获取页面文本
                if not results:
                    page_text = page.inner_text("body")[:3000]
                    results.append({
                        "title": "搜索结果页面内容",
                        "url": search_url,
                        "abstract": page_text[:500]
                    })

                browser.close()

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


# 同步包装函数（使用线程池在异步环境中安全运行）
def browse_page_sync(url: str, extract_text: bool = True, extract_links: bool = False) -> Dict[str, Any]:
    """同步版本的页面浏览，使用线程池避免 asyncio 冲突"""
    def _run():
        service = BrowserService()
        return service.browse_page(url, extract_text, extract_links)

    future = _executor.submit(_run)
    return future.result(timeout=60)


def search_baidu_sync(query: str, max_results: int = 5) -> Dict[str, Any]:
    """同步版本的百度搜索，使用线程池避免 asyncio 冲突"""
    def _run():
        service = BrowserService()
        return service.search_baidu(query, max_results)

    future = _executor.submit(_run)
    return future.result(timeout=60)
