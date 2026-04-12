"""
@description: Agent 工具注册表 - 统一管理外部工具调用，支持扩展
@dependencies: src.utils.model_gateway, requests
@last_modified: 2026-03-27
"""
from typing import Dict, Any, Callable, Optional
from pathlib import Path
import time
from scripts.litellm_gateway import get_model_gateway


class ToolRegistry:
    """轻量级工具注册表，Agent 通过统一接口调用外部工具"""

    def __init__(self):
        self._tools: Dict[str, Dict[str, Any]] = {}
        self._tavily_exhausted_until = 0  # Unix timestamp，在此之前不尝试 Tavily

        # === Tavily 短路持久化 ===
        self._tavily_status_file = Path(__file__).resolve().parent.parent.parent / ".ai-state" / "tavily_status.json"
        if self._tavily_status_file.exists():
            try:
                import json
                status = json.loads(self._tavily_status_file.read_text(encoding="utf-8"))
                saved_until = status.get("exhausted_until", 0)
                if saved_until > time.time():
                    self._tavily_exhausted_until = saved_until
                    remaining = int((saved_until - time.time()) / 60)
                    print(f"[Tavily] Restored circuit-breaker, {remaining} min remaining")
            except:
                pass

        self._register_defaults()

    def _register_defaults(self):
        """注册默认工具"""
        self.register("deep_research", self._tool_deep_research,
                      "深度搜索：竞品调研、市场数据、技术趋势")
        self.register("design_vision_analysis", self._tool_vision_analysis,
                      "设计视觉分析：分析竞品外观、参考造型、UI截图")
        self.register("technical_research", self._tool_technical_research,
                      "技术调研：芯片选型、行业标准、参考设计、BOM成本")
        self.register("figma_design", self._tool_figma,
                      "Figma 设计工具（待配置 API token）")
        self.register("image_generation", self._tool_imagen,
                      "AI图像生成：根据文字描述生成概念渲染图")
        self.register("platform_search", self._tool_platform_search,
                      "平台专属搜索：根据 URL 域名自动选择最佳搜索策略")
        self.register("multi_engine_search", self._tool_multi_engine_search,
                      "多引擎并行搜索：Google+Bing+百度+搜狗同时搜索，结果合并去重")
        self.register("web_rooter_search", self._tool_web_rooter_search,
                      "Web-Rooter 多引擎深度搜索：21个搜索引擎并行，支持社交媒体和学术搜索")
        self.register("tavily_search", self._tool_tavily_search,
                      "Tavily AI搜索：专为AI Agent设计的高质量搜索API，返回结构化结果")
        self.register("apify_scrape", self._tool_apify_scrape,
                      "Apify 社媒数据抓取：小红书/B站/微博热搜（结构化数据）")
        self.register("industry_data_search", self._tool_industry_data_search,
                      "行业大数据搜索：Grand View Research, Statista 等权威市场研究数据")

    def register(self, name: str, func: Callable, description: str):
        self._tools[name] = {"func": func, "description": description}

    def list_tools(self) -> list:
        return [{"name": k, "description": v["description"]} for k, v in self._tools.items()]

    def call(self, tool_name: str, query: str) -> Dict[str, Any]:
        tool = self._tools.get(tool_name)
        if not tool:
            return {"success": False, "error": f"Tool '{tool_name}' not found"}
        try:
            return tool["func"](query)
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _tool_deep_research(self, query: str) -> Dict[str, Any]:
        """使用 Gemini Deep Research 做深度搜索"""
        gateway = get_model_gateway()
        system_prompt = "你是一个研究助手。请对以下问题进行深入调研，提供数据和事实支撑。"
        # 优先 Gemini deep research，降级到 gemini_2_5_flash
        result = gateway.call_gemini("gemini_deep_research", query, system_prompt, "research")
        if result.get("success"):
            return {"success": True, "tool": "gemini_deep_research", "data": result["response"]}
        result = gateway.call_gemini("gemini_2_5_flash", query, system_prompt, "research")
        if result.get("success"):
            return {"success": True, "tool": "gemini_2_5_flash(fallback)", "data": result["response"]}
        return {"success": False, "error": "All research models failed"}

    def _tool_vision_analysis(self, query: str) -> Dict[str, Any]:
        """使用 Gemini Vision 分析设计相关图片（文字描述模式）"""
        gateway = get_model_gateway()
        system_prompt = "你是一个工业设计分析专家。请根据描述分析设计趋势、造型特点、材质工艺。"
        result = gateway.call_gemini("gemini_3_pro", query, system_prompt, "design_analysis")
        if result.get("success"):
            return {"success": True, "tool": "gemini_vision_analysis", "data": result["response"]}
        return {"success": False, "error": "Vision analysis failed"}

    def _tool_technical_research(self, query: str) -> Dict[str, Any]:
        """使用 Gemini Deep Research 做技术调研"""
        gateway = get_model_gateway()
        system_prompt = "你是一个硬件技术调研专家。请对以下技术问题进行深入调研，提供具体的芯片型号、关键参数、价格区间、供应商信息和技术对比。优先引用 datasheet 和行业标准。"
        result = gateway.call_gemini("gemini_deep_research", query, system_prompt, "technical_research")
        if result.get("success"):
            return {"success": True, "tool": "gemini_deep_research", "data": result["response"]}
        result = gateway.call_gemini("gemini_2_5_flash", query, system_prompt, "technical_research")
        if result.get("success"):
            return {"success": True, "tool": "gemini_2_5_flash(fallback)", "data": result["response"]}
        return {"success": False, "error": "All research models failed"}

    def _tool_figma(self, query: str) -> Dict[str, Any]:
        """Figma 设计工具 - 待配置"""
        return {"success": False, "error": "Figma API token 未配置，请在环境变量 FIGMA_API_TOKEN 中设置",
                "tool": "figma_design", "status": "pending_configuration"}

    def _tool_imagen(self, prompt: str) -> Dict[str, Any]:
        """使用 Gemini Imagen 生成图片，返回 base64 图片数据"""
        import os
        import requests as req
        api_key = os.environ.get("GEMINI_API_KEY", "")
        if not api_key:
            return {"success": False, "error": "GEMINI_API_KEY 环境变量未设置"}
        url = f"https://generativelanguage.googleapis.com/v1beta/models/imagen-4.0-fast-generate-001:predict?key={api_key}"
        payload = {
            "instances": [{"prompt": prompt}],
            "parameters": {"sampleCount": 1, "aspectRatio": "16:9"}
        }
        try:
            resp = req.post(url, json=payload, timeout=60,
                           headers={"Content-Type": "application/json"})
            result = resp.json()
            if "predictions" in result and result["predictions"]:
                image_b64 = result["predictions"][0].get("bytesBase64Encoded", "")
                if image_b64:
                    return {"success": True, "tool": "imagen", "image_base64": image_b64}
            return {"success": False, "error": f"Imagen 返回异常: {str(result)[:300]}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _tool_web_rooter_search(self, query: str, mode: str = "deep") -> Dict[str, Any]:
        """调用 Web-Rooter 进行多引擎搜索"""
        import subprocess
        import os

        rooter_dir = os.path.join(os.path.dirname(__file__), "..", "..", "tools", "web-rooter")
        python_path = os.path.join(rooter_dir, ".venv312", "Scripts", "python.exe")
        main_path = os.path.join(rooter_dir, "main.py")

        if not os.path.exists(main_path):
            return {"success": False, "error": "Web-Rooter not installed"}

        # mode: deep(深度搜索), social(社交媒体), web(普通搜索)
        cmd = [python_path, main_path, mode, query]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60,
                cwd=rooter_dir,
                encoding="utf-8",
                errors="ignore"
            )

            output = result.stdout.strip()
            if result.returncode == 0 and output and len(output) > 50:
                return {"success": True, "tool": f"web_rooter_{mode}", "data": output[:5000]}
            else:
                stderr = result.stderr.strip()[:300] if result.stderr else ""
                return {"success": False, "error": f"returncode={result.returncode}, stderr={stderr}"}
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "Web-Rooter timeout (60s)"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _tool_tavily_search(self, query: str, search_depth: str = "advanced") -> Dict[str, Any]:
        """Tavily AI 搜索，返回高质量结构化结果

        失败时自动降级到 Gemini Deep Research
        """
        import os
        import time

        # === 配额耗尽短路：4 小时内不重试 ===
        if time.time() < self._tavily_exhausted_until:
            return self._tavily_fallback_gemini(query)

        api_key = os.environ.get("TAVILY_API_KEY", "")
        if not api_key:
            return {"success": False, "error": "TAVILY_API_KEY not set"}

        try:
            from tavily import TavilyClient
            client = TavilyClient(api_key=api_key)

            # 重试 2 次
            last_error = None
            for attempt in range(2):
                try:
                    response = client.search(
                        query=query,
                        search_depth=search_depth if attempt == 0 else "basic",  # 第二次降级为 basic
                        max_results=5,
                        include_answer=True
                    )

                    parts = []
                    # Tavily 自带的 AI 总结
                    if response.get("answer"):
                        parts.append(f"[AI Summary]\n{response['answer']}")

                    # 各条结果
                    for r in response.get("results", [])[:5]:
                        title = r.get("title", "")
                        content = r.get("content", "")
                        url = r.get("url", "")
                        if content:
                            parts.append(f"[{title}]\n{content[:500]}\nURL: {url}")

                    if parts:
                        combined = "\n\n".join(parts)[:5000]
                        return {"success": True, "tool": "tavily", "data": combined}
                    return {"success": False, "error": "No results"}
                except Exception as e:
                    last_error = e
                    error_str = str(e)
                    # 如果是配额耗尽，设置短路时间，不重试
                    if "usage limit" in error_str.lower() or "quota" in error_str.lower() or "exceeds your plan" in error_str.lower():
                        self._tavily_exhausted_until = time.time() + 4 * 3600  # 4 小时后再试
                        # 持久化到磁盘
                        try:
                            import json as _json
                            from datetime import datetime
                            self._tavily_status_file.parent.mkdir(parents=True, exist_ok=True)
                            self._tavily_status_file.write_text(_json.dumps({
                                "exhausted_until": self._tavily_exhausted_until,
                                "reason": "plan usage limit exceeded",
                                "set_at": datetime.now().isoformat()
                            }, ensure_ascii=False), encoding="utf-8")
                        except:
                            pass
                        print(f"[Tavily] Quota exhausted, skipping for 4h, falling back to Gemini")
                        return self._tavily_fallback_gemini(query)
                    print(f"[Tavily] Attempt {attempt+1}/2 failed: {error_str[:100]}")
                    time.sleep(2)

            # 降级到 Gemini Deep Research
            return self._tavily_fallback_gemini(query)

        except ImportError:
            return {"success": False, "error": "tavily package not installed"}

    def _tavily_fallback_gemini(self, query: str) -> Dict[str, Any]:
        """Tavily 降级到 Gemini"""
        gateway = get_model_gateway()
        fallback_prompt = f"请搜索并总结关于以下主题的信息，提供数据、事实和来源：\n{query}"
        result = gateway.call_gemini("gemini_2_5_flash", fallback_prompt, "你是研究助手。", "tavily_fallback")
        if result.get("success"):
            return {"success": True, "tool": "tavily_fallback_gemini", "data": result["response"]}
        return {"success": False, "error": "Tavily exhausted and Gemini fallback failed"}

    def _tool_apify_scrape(self, query: str) -> Dict[str, Any]:
        """使用 Apify Actor 抓取社媒平台数据

        query 格式：
          "xiaohongshu:关键词" - 小红书搜索
          "bilibili:关键词" - B站搜索
          "weibo:关键词" - 微博搜索
        """
        import os
        try:
            from apify_client import ApifyClient
        except ImportError:
            return {"success": False, "error": "apify-client 未安装"}

        token = os.environ.get("APIFY_TOKEN", "")
        if not token:
            return {"success": False, "error": "APIFY_TOKEN 未配置"}

        client = ApifyClient(token)

        # 解析平台和关键词
        if ":" in query:
            platform, keyword = query.split(":", 1)
            platform = platform.strip().lower()
            keyword = keyword.strip()
        else:
            platform = "xiaohongshu"
            keyword = query.strip()

        try:
            if platform in ("xiaohongshu", "xhs", "小红书", "rednote"):
                # 使用 kuaima/xiaohongshu-search Actor
                run_input = {
                    "keyword": keyword,
                    "maxItems": 5,
                    "sort": "general"
                }
                run = client.actor("kuaima/xiaohongshu-search").call(run_input=run_input, timeout_secs=60)

            elif platform in ("bilibili", "bili", "b站"):
                # 使用 hanmingli/bilibili-search Actor
                run_input = {
                    "keyword": keyword,
                    "maxItems": 5
                }
                run = client.actor("hanmingli/bilibili-search").call(run_input=run_input, timeout_secs=60)

            elif platform in ("weibo", "微博"):
                run_input = {
                    "keyword": keyword,
                    "maxItems": 5
                }
                run = client.actor("stomber/weibo-search").call(run_input=run_input, timeout_secs=60)
            else:
                return {"success": False, "error": f"不支持的平台: {platform}"}

            # 获取结果
            items = list(client.dataset(run["defaultDatasetId"]).iterate_items(limit=10))

            if not items:
                return {"success": True, "data": "", "count": 0, "platform": platform}

            # 格式化输出
            results = []
            for item in items:
                # 尝试提取通用字段
                title = item.get("title") or item.get("note_card", {}).get("title", "") or item.get("desc", "")
                content = item.get("content") or item.get("desc") or item.get("description", "") or item.get("text", "")
                author = item.get("author", {}).get("username", "") or item.get("nickname", "") or item.get("user", {}).get("nickname", "") or item.get("authorName", "")
                likes = item.get("likes") or item.get("liked_count") or item.get("like_count") or item.get("stats", {}).get("likes", 0) or 0
                url = item.get("url") or item.get("noteUrl", "") or item.get("link", "") or item.get("postUrl", "")

                entry = f"[{author}] {title}" if author else str(title)
                if content and len(str(content)) > 10:
                    entry += f"\n{str(content)[:300]}"
                if likes:
                    entry += f"\n👍 {likes}"
                if url:
                    entry += f"\n🔗 {url}"
                results.append(entry)

            combined = "\n---\n".join(results)
            return {
                "success": True,
                "data": combined[:5000],
                "count": len(items),
                "platform": platform
            }

        except Exception as e:
            error_msg = str(e)
            if "Actor" in error_msg and "not found" in error_msg.lower():
                return {"success": False, "error": f"Apify Actor 不存在: {error_msg[:100]}"}
            return {"success": False, "error": f"Apify 调用失败: {error_msg[:200]}"}

    def _tool_platform_search(self, query: str) -> Dict[str, Any]:
        """按平台场景分流搜索"""
        import re

        # 解析可能的 [domain] 前缀
        _domain_hint = ""
        if query.startswith("[") and "]" in query:
            _bracket_end = query.index("]")
            _domain_hint = query[1:_bracket_end].strip().lower()
            query = query[_bracket_end+1:].strip()

        # 检测平台（从 URL 或 domain hint）
        platform = "general"
        combined = f"{query} {_domain_hint}"
        if "weixin" in combined or "weixin.qq" in combined or "wechat" in combined or "mp.weixin" in combined:
            platform = "wechat"
        elif "xiaohongshu" in combined or "xhslink" in combined or "xhs" in combined:
            platform = "xiaohongshu"
        elif "zhihu" in combined:
            platform = "zhihu"
        elif "bilibili" in combined or "b23.tv" in combined:
            platform = "bilibili"
        elif "weibo" in combined:
            platform = "weibo"
        elif "douyin" in combined or "tiktok" in combined:
            platform = "douyin"

        # 提取有意义的文字（去掉 URL 和平台噪音）
        clean = re.sub(r'https?://[^\s]+', '', query).strip()
        for noise in ["mp.weixin.qq.com", "xhslink.com", "xiaohongshu.com",
                       "zhihu.com", "bilibili.com", "weibo.com",
                       "复制后打开", "查看笔记", "【小红书】", "【微信】", "【知乎】"]:
            clean = clean.replace(noise, "").strip()
        clean = clean.strip("！!。.…，,\n\r")

        # 提取 URL
        url_match = re.search(r'https?://[^\s<>"{}|\\^`\[\]]+', query)
        url = url_match.group(0) if url_match else ""

        all_data = []

        # === 场景分流 ===
        MIN_DATA_LEN = 200  # 最小有效数据长度

        if platform == "wechat":
            # 有标题文字时用标题搜（Tavily 搜微信 URL 结果不可靠）
            search_term = clean if len(clean) > 5 else url
            tv = self._tool_tavily_search(search_term)
            if tv.get("success") and len(tv.get("data", "")) >= MIN_DATA_LEN:
                all_data.append(f"[Tavily]\n{tv['data']}")
            # 补充：用标题搜（如果 Tavily 返回了标题，提取后再深搜）
            if all_data:
                gateway = get_model_gateway()
                title_extract = gateway.call_azure_openai(
                    "cpo",
                    f"从以下搜索结果中提取文章的真实标题（不是平台名）。只输出标题，不要其他。\n\n{all_data[0][:1000]}",
                    "只输出标题。", "extract_title"
                )
                if title_extract.get("success") and len(title_extract["response"].strip()) > 5:
                    real_title = title_extract["response"].strip()
                    deep = self._tool_deep_research(real_title)
                    if deep.get("success") and len(deep.get("data", "")) >= MIN_DATA_LEN:
                        all_data.append(f"[DeepSearch:{real_title[:30]}]\n{deep['data']}")
            # 如果没有结果，用 clean 调用 deep_research 兜底
            if not all_data and clean:
                deep = self._tool_deep_research(clean)
                if deep.get("success") and len(deep.get("data", "")) >= MIN_DATA_LEN:
                    all_data.append(f"[DeepSearch]\n{deep['data']}")

        elif platform in ("xiaohongshu", "bilibili", "weibo", "douyin"):
            # 国内社媒：优先 Apify（结构化数据更好），fallback 到 Tavily+Gemini
            search_text = clean if len(clean) > 5 else url

            # 小红书和B站优先用 Apify
            if platform in ("xiaohongshu", "bilibili"):
                apify_result = self._tool_apify_scrape(f"{platform}:{search_text}")
                if apify_result.get("success") and apify_result.get("count", 0) > 0 and len(apify_result.get("data", "")) >= MIN_DATA_LEN:
                    all_data.append(f"[Apify:{platform}]\n{apify_result['data']}")

            # fallback 到 Tavily + Gemini
            if not all_data:
                tv = self._tool_tavily_search(search_text)
                if tv.get("success") and len(tv.get("data", "")) >= MIN_DATA_LEN:
                    all_data.append(f"[Tavily]\n{tv['data']}")
                # Gemini 补充
                gateway = get_model_gateway()
                r = gateway.call_gemini("gemini_deep_research", search_text,
                    "搜索以下内容的详细信息，包括原文要点、作者观点、关键数据", "social_search")
                if r.get("success") and len(r.get("response", "")) >= MIN_DATA_LEN:
                    all_data.append(f"[Gemini]\n{r['response']}")

            # 最终兜底：用 clean 调用 deep_research
            if not all_data and clean:
                deep = self._tool_deep_research(clean)
                if deep.get("success") and len(deep.get("data", "")) >= MIN_DATA_LEN:
                    all_data.append(f"[DeepSearch]\n{deep['data']}")

        elif platform == "zhihu":
            # 知乎：Jina Reader 通常能抓到
            import requests as _req
            try:
                jina = _req.get(f"https://r.jina.ai/{url}", headers={"Accept": "text/markdown"}, timeout=20)
                if jina.status_code == 200 and len(jina.text.strip()) >= MIN_DATA_LEN:
                    all_data.append(f"[Jina]\n{jina.text.strip()[:3000]}")
            except Exception:
                pass
            if not all_data:
                tv = self._tool_tavily_search(url if url else clean)
                if tv.get("success") and len(tv.get("data", "")) >= MIN_DATA_LEN:
                    all_data.append(f"[Tavily]\n{tv['data']}")
            if not all_data and clean:
                deep = self._tool_deep_research(clean)
                if deep.get("success") and len(deep.get("data", "")) >= MIN_DATA_LEN:
                    all_data.append(f"[DeepSearch]\n{deep['data']}")
        else:
            # 普通网页：Jina（快）→ Tavily → Gemini → DeepResearch
            import requests as _req
            try:
                jina = _req.get(f"https://r.jina.ai/{url}", headers={"Accept": "text/markdown"}, timeout=20)
                if jina.status_code == 200 and len(jina.text.strip()) >= MIN_DATA_LEN:
                    all_data.append(f"[Jina]\n{jina.text.strip()[:3000]}")
            except Exception:
                pass
            if not all_data:
                tv = self._tool_tavily_search(url if url else clean)
                if tv.get("success") and len(tv.get("data", "")) >= MIN_DATA_LEN:
                    all_data.append(f"[Tavily]\n{tv['data']}")
            if not all_data:
                gateway = get_model_gateway()
                r = gateway.call_gemini("gemini_deep_research", url,
                    "获取这个网页的完整内容", "web_search")
                if r.get("success") and len(r.get("response", "")) >= MIN_DATA_LEN:
                    all_data.append(f"[Gemini]\n{r['response']}")
            # 最终兜底：用 clean 调用 deep_research
            if not all_data and clean:
                deep = self._tool_deep_research(clean)
                if deep.get("success") and len(deep.get("data", "")) >= MIN_DATA_LEN:
                    all_data.append(f"[DeepSearch]\n{deep['data']}")

        if all_data:
            combined = "\n\n---\n\n".join(all_data)[:5000]
            return {"success": True, "tool": "platform_search", "platform": platform, "data": combined}
        return {"success": False, "error": f"All searches failed for platform={platform}"}

    def _tool_multi_engine_search(self, query: str) -> Dict[str, Any]:
        """多引擎搜索"""
        all_data = []

        # 优先：Web-Rooter 深度搜索（21 引擎并行）
        wr = self._tool_web_rooter_search(query, "deep")
        if wr.get("success"):
            all_data.append(f"[Web-Rooter Deep]\n{wr['data']}")

        # Tavily AI 搜索（高质量，有额度限制，用于关键搜索）
        if len(all_data) < 2:  # 只有前面结果不够时才用，节省额度
            tv = self._tool_tavily_search(query)
            if tv.get("success"):
                all_data.append(f"[Tavily AI]\n{tv['data']}")

        # 补充：Gemini Deep Research
        gateway = get_model_gateway()
        r1 = gateway.call_gemini("gemini_deep_research", query, "详细搜索以下内容", "multi_search_1")
        if r1.get("success") and len(r1.get("response", "")) > 50:
            all_data.append(f"[Gemini Deep]\n{r1['response']}")

        # 补充：中英双语搜索
        has_chinese = any('\u4e00' <= c <= '\u9fff' for c in query)
        if has_chinese:
            en_result = gateway.call_azure_openai("cpo", f"把以下中文翻译成英文搜索词，只输出英文：{query}", "只输出翻译。", "translate")
            if en_result.get("success"):
                en_query = en_result["response"].strip()
                r2 = gateway.call_gemini("gemini_2_5_flash", en_query, "Search for detailed information", "multi_en")
                if r2.get("success") and len(r2.get("response", "")) > 50:
                    all_data.append(f"[English]\n{r2['response']}")

        if all_data:
            return {"success": True, "tool": "multi_engine_search", "data": "\n\n".join(all_data)[:6000]}
        return {"success": False, "error": "All engines failed"}

    def _tool_industry_data_search(self, query: str) -> Dict[str, Any]:
        """搜索行业大数据：Grand View Research, Statista 等"""
        gateway = get_model_gateway()

        # 让 Gemini 搜索行业数据
        search_prompt = (
            f"搜索以下行业数据问题，优先引用 Grand View Research, Statista, "
            f"IDC, Gartner, Markets and Markets 等权威市场研究机构的数据。\n"
            f"必须给出具体数字（市场规模、增长率、份额、出货量）和数据年份。\n\n"
            f"查询: {query}"
        )

        result = gateway.call_gemini("gemini_deep_research", search_prompt,
            "你是市场研究分析师，必须引用权威数据源和具体数字。", "industry_data")

        if result.get("success"):
            return {"success": True, "tool": "industry_data", "data": result["response"]}
        # Fallback to Azure OpenAI
        result = gateway.call_azure_openai("cpo", search_prompt,
            "你是市场研究分析师，必须引用权威数据源和具体数字。", "industry_data")
        if result.get("success"):
            return {"success": True, "tool": "industry_data(azure)", "data": result["response"]}
        return {"success": False, "error": "行业数据搜索失败"}


_registry: Optional[ToolRegistry] = None


def get_tool_registry() -> ToolRegistry:
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
    return _registry