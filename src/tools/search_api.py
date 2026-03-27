"""
@description: 统一搜索API工具 - 支持SerpAPI/Tavily/Exa/浏览器降级
@dependencies: requests, yaml
@last_modified: 2026-03-17
"""

import os
import json
import yaml
import time
import requests
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from enum import Enum


class SearchProvider(Enum):
    SERPAPI = "serpapi"
    TAVILY = "tavily"
    EXA = "exa"
    BROWSER = "browser"
    MANUAL = "manual"


@dataclass
class SearchResult:
    success: bool
    provider: str
    query: str
    results: List[Dict[str, Any]]
    raw_response: Optional[Dict] = None
    error: Optional[str] = None
    attempt_log: List[Dict] = None


class UnifiedSearchAPI:
    """
    统一搜索API - 优先使用第三方API，失败后降级到浏览器方案

    设计理念：
    - 豆包/Gemini之所以能一次获取丰富数据，是因为服务端预集成了搜索API
    - 我们模拟这个架构：优先调用商业搜索API，绕过客户端爬虫限制
    """

    def __init__(self, config_path: str = None):
        if config_path is None:
            config_path = Path(__file__).parent.parent / "config" / "search_api.yaml"

        self.config = self._load_config(config_path)
        self.attempt_log = []

    def _load_config(self, path: Path) -> dict:
        if not path.exists():
            return self._default_config()
        with open(path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f) or self._default_config()

    def _default_config(self) -> dict:
        """默认配置 - 从环境变量读取API密钥"""
        return {
            "providers": {
                "serpapi": {
                    "api_key": os.getenv("SERPAPI_KEY", ""),
                    "endpoint": "https://serpapi.com/search",
                    "free_limit": "100/month"
                },
                "tavily": {
                    "api_key": os.getenv("TAVILY_API_KEY", ""),
                    "endpoint": "https://api.tavily.com/search",
                    "free_limit": "1000/month"
                },
                "exa": {
                    "api_key": os.getenv("EXA_API_KEY", ""),
                    "endpoint": "https://api.exa.ai/search",
                    "free_limit": "1000/month"
                }
            },
            "fallback_order": ["serpapi", "tavily", "exa", "browser", "manual"],
            "timeout": 30,
            "max_results": 10
        }

    def search(self, query: str, max_results: int = 10) -> SearchResult:
        """
        执行搜索 - 按优先级尝试所有方案

        降级顺序：
        P1: SerpAPI (Google搜索结果API)
        P2: Tavily (AI Agent专用搜索)
        P3: Exa (AI原生搜索引擎)
        P4: 浏览器方案 (备用)
        P5: 请求用户协助
        """
        self.attempt_log = []

        # P1: SerpAPI
        result = self._try_serpapi(query, max_results)
        if result.success:
            return result

        # P2: Tavily
        result = self._try_tavily(query, max_results)
        if result.success:
            return result

        # P3: Exa
        result = self._try_exa(query, max_results)
        if result.success:
            return result

        # P4: 浏览器方案（占位，需要单独实现）
        result = self._try_browser_fallback(query, max_results)
        if result.success:
            return result

        # P5: 请求用户协助
        return self._request_manual_search(query)

    def _try_serpapi(self, query: str, max_results: int) -> SearchResult:
        """SerpAPI - Google搜索结果API"""
        provider_config = self.config.get("providers", {}).get("serpapi", {})
        api_key = provider_config.get("api_key", "")

        if not api_key:
            self._log_attempt("serpapi", False, "API Key not configured")
            return SearchResult(
                success=False,
                provider="serpapi",
                query=query,
                results=[],
                error="API Key not configured"
            )

        try:
            params = {
                "api_key": api_key,
                "q": query,
                "num": max_results,
                "hl": "zh-CN"
            }

            response = requests.get(
                provider_config.get("endpoint", "https://serpapi.com/search"),
                params=params,
                timeout=self.config.get("timeout", 30)
            )

            if response.status_code == 200:
                data = response.json()
                results = self._parse_serpapi_results(data)
                self._log_attempt("serpapi", True, f"Got {len(results)} results")
                return SearchResult(
                    success=True,
                    provider="serpapi",
                    query=query,
                    results=results,
                    raw_response=data
                )
            else:
                error = f"HTTP {response.status_code}: {response.text[:200]}"
                self._log_attempt("serpapi", False, error)
                return SearchResult(
                    success=False,
                    provider="serpapi",
                    query=query,
                    results=[],
                    error=error
                )

        except Exception as e:
            self._log_attempt("serpapi", False, str(e))
            return SearchResult(
                success=False,
                provider="serpapi",
                query=query,
                results=[],
                error=str(e)
            )

    def _try_tavily(self, query: str, max_results: int) -> SearchResult:
        """Tavily - 专为AI Agent设计的搜索API"""
        provider_config = self.config.get("providers", {}).get("tavily", {})
        api_key = provider_config.get("api_key", "")

        if not api_key:
            self._log_attempt("tavily", False, "API Key not configured")
            return SearchResult(
                success=False,
                provider="tavily",
                query=query,
                results=[],
                error="API Key not configured"
            )

        try:
            payload = {
                "api_key": api_key,
                "query": query,
                "max_results": max_results,
                "search_depth": "advanced",
                "include_answer": True,
                "include_raw_content": False
            }

            response = requests.post(
                provider_config.get("endpoint", "https://api.tavily.com/search"),
                json=payload,
                timeout=self.config.get("timeout", 30)
            )

            if response.status_code == 200:
                data = response.json()
                results = self._parse_tavily_results(data)
                self._log_attempt("tavily", True, f"Got {len(results)} results")
                return SearchResult(
                    success=True,
                    provider="tavily",
                    query=query,
                    results=results,
                    raw_response=data
                )
            else:
                error = f"HTTP {response.status_code}: {response.text[:200]}"
                self._log_attempt("tavily", False, error)
                return SearchResult(
                    success=False,
                    provider="tavily",
                    query=query,
                    results=[],
                    error=error
                )

        except Exception as e:
            self._log_attempt("tavily", False, str(e))
            return SearchResult(
                success=False,
                provider="tavily",
                query=query,
                results=[],
                error=str(e)
            )

    def _try_exa(self, query: str, max_results: int) -> SearchResult:
        """Exa - AI原生搜索引擎"""
        provider_config = self.config.get("providers", {}).get("exa", {})
        api_key = provider_config.get("api_key", "")

        if not api_key:
            self._log_attempt("exa", False, "API Key not configured")
            return SearchResult(
                success=False,
                provider="exa",
                query=query,
                results=[],
                error="API Key not configured"
            )

        try:
            headers = {
                "x-api-key": api_key,
                "Content-Type": "application/json"
            }

            payload = {
                "query": query,
                "numResults": max_results,
                "useAutoprompt": True,
                "type": "auto"
            }

            response = requests.post(
                provider_config.get("endpoint", "https://api.exa.ai/search"),
                headers=headers,
                json=payload,
                timeout=self.config.get("timeout", 30)
            )

            if response.status_code == 200:
                data = response.json()
                results = self._parse_exa_results(data)
                self._log_attempt("exa", True, f"Got {len(results)} results")
                return SearchResult(
                    success=True,
                    provider="exa",
                    query=query,
                    results=results,
                    raw_response=data
                )
            else:
                error = f"HTTP {response.status_code}: {response.text[:200]}"
                self._log_attempt("exa", False, error)
                return SearchResult(
                    success=False,
                    provider="exa",
                    query=query,
                    results=[],
                    error=error
                )

        except Exception as e:
            self._log_attempt("exa", False, str(e))
            return SearchResult(
                success=False,
                provider="exa",
                query=query,
                results=[],
                error=str(e)
            )

    def _try_browser_fallback(self, query: str, max_results: int) -> SearchResult:
        """
        浏览器降级方案 - 当所有API都失败时使用

        注意：这是最后的自动方案，通常会因为网络限制而失败
        """
        self._log_attempt("browser", False, "Browser fallback not implemented yet")
        return SearchResult(
            success=False,
            provider="browser",
            query=query,
            results=[],
            error="Browser fallback not implemented"
        )

    def _request_manual_search(self, query: str) -> SearchResult:
        """请求用户手动搜索"""
        self._log_attempt("manual", True, "Requesting user assistance")

        return SearchResult(
            success=False,
            provider="manual",
            query=query,
            results=[],
            error="All automated methods failed",
            attempt_log=self.attempt_log
        )

    def _parse_serpapi_results(self, data: dict) -> List[Dict]:
        """解析SerpAPI返回结果"""
        results = []

        # 有机搜索结果
        for item in data.get("organic_results", []):
            results.append({
                "title": item.get("title", ""),
                "url": item.get("link", ""),
                "snippet": item.get("snippet", ""),
                "source": "serpapi_organic"
            })

        # 知识图谱
        if "knowledge_graph" in data:
            kg = data["knowledge_graph"]
            results.append({
                "title": kg.get("title", ""),
                "url": kg.get("website", ""),
                "snippet": kg.get("description", ""),
                "source": "serpapi_knowledge_graph",
                "type": kg.get("type", "")
            })

        return results

    def _parse_tavily_results(self, data: dict) -> List[Dict]:
        """解析Tavily返回结果"""
        results = []

        # Tavily的answer字段
        if "answer" in data:
            results.append({
                "title": "Tavily AI Answer",
                "url": "",
                "snippet": data["answer"],
                "source": "tavily_answer"
            })

        # 搜索结果
        for item in data.get("results", []):
            results.append({
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "snippet": item.get("content", ""),
                "source": "tavily_search",
                "score": item.get("score", 0)
            })

        return results

    def _parse_exa_results(self, data: dict) -> List[Dict]:
        """解析Exa返回结果"""
        results = []

        for item in data.get("results", []):
            results.append({
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "snippet": item.get("text", "")[:500],  # Exa返回全文，截取前500字
                "source": "exa_search",
                "author": item.get("author", ""),
                "published_date": item.get("publishedDate", "")
            })

        return results

    def _log_attempt(self, provider: str, success: bool, message: str):
        """记录尝试日志"""
        self.attempt_log.append({
            "provider": provider,
            "success": success,
            "message": message,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        })


# 全局实例
_search_api: Optional[UnifiedSearchAPI] = None


def get_search_api() -> UnifiedSearchAPI:
    """获取全局搜索API实例"""
    global _search_api
    if _search_api is None:
        _search_api = UnifiedSearchAPI()
    return _search_api


# === 便捷函数 ===

def search(query: str, max_results: int = 10) -> SearchResult:
    """便捷搜索函数"""
    return get_search_api().search(query, max_results)


# === 测试 ===
if __name__ == "__main__":
    print("=" * 60)
    print("[UNIFIED SEARCH API TEST]")
    print("=" * 60)

    api = get_search_api()

    # 测试搜索
    print("\n[TEST] Searching for 'INMO Air3 AR glasses specs'...")
    result = api.search("INMO Air3 AR glasses specifications", max_results=5)

    print(f"\n[RESULT] Provider: {result.provider}")
    print(f"[RESULT] Success: {result.success}")

    if result.success:
        print(f"[RESULT] Found {len(result.results)} results:")
        for i, item in enumerate(result.results[:3], 1):
            print(f"  {i}. {item.get('title', 'N/A')[:50]}")
            print(f"     URL: {item.get('url', 'N/A')[:60]}")
    else:
        print(f"[ERROR] {result.error}")
        print(f"[ATTEMPTS] {len(result.attempt_log or [])} attempts made")

    print("\n" + "=" * 60)