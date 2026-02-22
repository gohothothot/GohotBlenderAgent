"""
Web Search Tool - 让 Agent 能联网搜索参考资料

增强版：
- DuckDuckGo 搜索 + HTML 搜索结果解析（双引擎 fallback）
- 智能网页抓取（支持 bilibili、YouTube 等视频页面提取描述）
- Blender 专题搜索
- 参考链接分析（从用户提供的 URL 提取材质/节点相关信息）
- 自动保存到知识库
"""

import urllib.request
import urllib.parse
import json
import re
from typing import Optional, List


# ========== Search Engines ==========

def _ddg_search(query: str, max_results: int = 5) -> list:
    """DuckDuckGo Instant Answer API"""
    url = "https://api.duckduckgo.com/?" + urllib.parse.urlencode({
        "q": query,
        "format": "json",
        "no_html": 1,
        "skip_disambig": 1,
    })

    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    })

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        results = []

        if data.get("Abstract"):
            results.append({
                "title": data.get("Heading", ""),
                "snippet": data["Abstract"],
                "url": data.get("AbstractURL", ""),
            })

        for topic in data.get("RelatedTopics", [])[:max_results]:
            if "Text" in topic:
                results.append({
                    "title": topic.get("FirstURL", "").split("/")[-1].replace("_", " "),
                    "snippet": topic["Text"],
                    "url": topic.get("FirstURL", ""),
                })

        return results[:max_results]
    except Exception:
        return []


def _ddg_html_search(query: str, max_results: int = 5) -> list:
    """DuckDuckGo HTML 搜索结果解析 - 比 Instant Answer API 更全面"""
    url = "https://html.duckduckgo.com/html/?" + urllib.parse.urlencode({"q": query})

    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    })

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="ignore")

        results = []

        # Parse result blocks
        result_blocks = re.findall(
            r'<a[^>]*class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>.*?'
            r'<a[^>]*class="result__snippet"[^>]*>(.*?)</a>',
            html, re.DOTALL
        )

        for href, title, snippet in result_blocks[:max_results]:
            title = re.sub(r'<[^>]+>', '', title).strip()
            snippet = re.sub(r'<[^>]+>', '', snippet).strip()

            if href.startswith("//duckduckgo.com/l/?uddg="):
                href = urllib.parse.unquote(href.split("uddg=")[1].split("&")[0])

            if title and snippet:
                results.append({
                    "title": title,
                    "snippet": snippet,
                    "url": href,
                })

        return results[:max_results]
    except Exception:
        return []


# ========== Web Fetching ==========

def _clean_html(html: str) -> str:
    """清理 HTML 为纯文本"""
    text = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL)
    text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL)
    text = re.sub(r'<nav[^>]*>.*?</nav>', '', text, flags=re.DOTALL)
    text = re.sub(r'<header[^>]*>.*?</header>', '', text, flags=re.DOTALL)
    text = re.sub(r'<footer[^>]*>.*?</footer>', '', text, flags=re.DOTALL)
    text = re.sub(r'<!--.*?-->', '', text, flags=re.DOTALL)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def _extract_bilibili_info(html: str, url: str) -> dict:
    """从 bilibili 页面提取视频信息"""
    info = {"source": "bilibili", "url": url}

    title_match = re.search(r'<title[^>]*>(.*?)</title>', html, re.DOTALL)
    if title_match:
        info["title"] = re.sub(r'<[^>]+>', '', title_match.group(1)).strip()
        info["title"] = info["title"].replace("_哔哩哔哩_bilibili", "").strip()

    desc_match = re.search(r'"desc"\s*:\s*"([^"]*)"', html)
    if desc_match:
        info["description"] = desc_match.group(1).replace("\\n", "\n")

    keywords_match = re.search(r'"keywords"\s*:\s*"([^"]*)"', html)
    if keywords_match:
        info["keywords"] = keywords_match.group(1)

    owner_match = re.search(r'"owner"\s*:\s*\{[^}]*"name"\s*:\s*"([^"]*)"', html)
    if owner_match:
        info["author"] = owner_match.group(1)

    pages = re.findall(r'"part"\s*:\s*"([^"]*)"', html)
    if pages:
        info["parts"] = pages

    related = re.findall(
        r'"title"\s*:\s*"([^"]*(?:材质|shader|着色|渲染|blender)[^"]*)"',
        html, re.IGNORECASE
    )
    if related:
        info["related_videos"] = list(set(related))[:5]

    return info


def _extract_youtube_info(html: str, url: str) -> dict:
    """从 YouTube 页面提取视频信息"""
    info = {"source": "youtube", "url": url}

    title_match = re.search(r'<title>(.*?)</title>', html)
    if title_match:
        info["title"] = title_match.group(1).replace(" - YouTube", "").strip()

    desc_match = re.search(r'"shortDescription"\s*:\s*"(.*?)"', html)
    if desc_match:
        desc = desc_match.group(1).replace("\\n", "\n").replace('\\"', '"')
        info["description"] = desc[:2000]

    keywords_match = re.search(r'"keywords"\s*:\s*\[(.*?)\]', html)
    if keywords_match:
        info["keywords"] = keywords_match.group(1).replace('"', '').strip()

    return info


def _extract_generic_article(html: str, url: str, max_chars: int = 4000) -> dict:
    """从普通网页提取文章内容"""
    info = {"source": "webpage", "url": url}

    title_match = re.search(r'<title[^>]*>(.*?)</title>', html, re.DOTALL)
    if title_match:
        info["title"] = re.sub(r'<[^>]+>', '', title_match.group(1)).strip()

    article_match = re.search(r'<article[^>]*>(.*?)</article>', html, re.DOTALL)
    if article_match:
        content = _clean_html(article_match.group(1))
    else:
        main_match = re.search(r'<main[^>]*>(.*?)</main>', html, re.DOTALL)
        if main_match:
            content = _clean_html(main_match.group(1))
        else:
            content = _clean_html(html)

    info["content"] = content[:max_chars]

    img_alts = re.findall(r'<img[^>]*alt="([^"]+)"', html)
    if img_alts:
        info["images"] = [alt for alt in img_alts if len(alt) > 5][:10]

    return info


def _web_fetch_smart(url: str, max_chars: int = 4000) -> dict:
    """智能网页抓取 - 根据 URL 类型选择不同的解析策略"""
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    })

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="ignore")

        if "bilibili.com" in url:
            return _extract_bilibili_info(html, url)
        elif "youtube.com" in url or "youtu.be" in url:
            return _extract_youtube_info(html, url)
        else:
            return _extract_generic_article(html, url, max_chars)

    except Exception as e:
        return {"source": "error", "url": url, "error": str(e)}


def _web_fetch_snippet(url: str, max_chars: int = 3000) -> str:
    """抓取网页文本摘要（兼容旧接口）"""
    result = _web_fetch_smart(url, max_chars)
    if "error" in result and result.get("source") == "error":
        return f"抓取失败: {result['error']}"
    if "content" in result:
        return result["content"]
    parts = []
    for key, val in result.items():
        if key in ("source", "url"):
            continue
        if isinstance(val, list):
            parts.append(f"{key}: {', '.join(str(v) for v in val)}")
        else:
            parts.append(f"{key}: {val}")
    return "\n".join(parts)


# ========== Public API ==========

def web_search(query: str, max_results: int = 5) -> dict:
    """搜索网络获取参考资料 - 多引擎 fallback"""
    try:
        # 1. DuckDuckGo Instant Answer
        results = _ddg_search(query, max_results)

        # 2. HTML 搜索 fallback
        if not results:
            results = _ddg_html_search(query, max_results)

        # 3. 加关键词 fallback
        if not results:
            fallback_queries = [
                f"{query} blender tutorial",
                f"{query} blender shader node setup",
                f"{query} blender procedural material",
            ]
            for fq in fallback_queries:
                results = _ddg_html_search(fq, max_results)
                if results:
                    break

        if not results:
            return {
                "success": True,
                "result": f"未找到 '{query}' 的搜索结果。建议：\n"
                          "1. 用英文关键词重试\n"
                          "2. 简化搜索词\n"
                          "3. 尝试 web_fetch 直接抓取已知 URL",
                "error": None,
            }

        formatted = []
        for r in results:
            entry = f"[{r['title']}]\n{r['snippet']}"
            if r.get('url'):
                entry += f"\n链接: {r['url']}"
            formatted.append(entry)

        output = f"搜索 '{query}' 的结果:\n\n" + "\n\n---\n\n".join(formatted)

        try:
            from . import knowledge_base
            knowledge_base.save_search_result(query, results, category="web_search")
        except Exception:
            pass

        return {"success": True, "result": output, "error": None}

    except Exception as e:
        return {"success": False, "result": None, "error": str(e)}


def web_fetch(url: str) -> dict:
    """智能抓取指定网页内容 - 自动识别 bilibili/YouTube/普通网页"""
    try:
        result = _web_fetch_smart(url, max_chars=5000)

        if "error" in result and result.get("source") == "error":
            return {"success": False, "result": None, "error": result["error"]}

        source = result.get("source", "unknown")
        parts = [f"来源类型: {source}", f"URL: {url}"]

        if "title" in result:
            parts.append(f"标题: {result['title']}")
        if "author" in result:
            parts.append(f"作者: {result['author']}")
        if "description" in result:
            parts.append(f"描述: {result['description']}")
        if "keywords" in result:
            parts.append(f"关键词: {result['keywords']}")
        if "parts" in result:
            parts.append(f"分P: {', '.join(result['parts'])}")
        if "related_videos" in result:
            parts.append(f"相关视频: {', '.join(result['related_videos'][:5])}")
        if "content" in result:
            parts.append(f"\n内容:\n{result['content']}")
        if "images" in result:
            parts.append(f"图片描述: {', '.join(result['images'][:5])}")

        output = "\n".join(parts)

        try:
            from . import knowledge_base
            knowledge_base.save_search_result(
                result.get("title", url),
                [{"title": result.get("title", ""), "snippet": output[:500], "url": url}],
                category="web_fetch"
            )
        except Exception:
            pass

        return {"success": True, "result": output, "error": None}

    except Exception as e:
        return {"success": False, "result": None, "error": str(e)}


def web_search_blender(topic: str) -> dict:
    """专门搜索 Blender 相关教程和资料 - 自动组合多个搜索词"""
    try:
        all_results = []
        seen_urls = set()

        search_queries = [
            f"blender {topic} shader nodes tutorial",
            f"blender {topic} procedural material setup",
            f"blender {topic} node graph bpy python",
        ]

        for q in search_queries:
            results = _ddg_html_search(q, 3)
            if not results:
                results = _ddg_search(q, 3)
            for r in results:
                if r.get("url") not in seen_urls:
                    seen_urls.add(r.get("url"))
                    all_results.append(r)

        if not all_results:
            return {
                "success": True,
                "result": f"未找到 Blender '{topic}' 相关资料。建议用英文搜索。",
                "error": None,
            }

        formatted = []
        for r in all_results[:8]:
            entry = f"[{r['title']}]\n{r['snippet']}"
            if r.get('url'):
                entry += f"\n链接: {r['url']}"
            formatted.append(entry)

        output = f"Blender '{topic}' 专题搜索结果:\n\n" + "\n\n---\n\n".join(formatted)

        try:
            from . import knowledge_base
            knowledge_base.save_search_result(
                f"blender_{topic}", all_results, category="blender_search"
            )
        except Exception:
            pass

        return {"success": True, "result": output, "error": None}

    except Exception as e:
        return {"success": False, "result": None, "error": str(e)}


def web_analyze_reference(url: str) -> dict:
    """分析参考链接，提取与 Blender 材质/着色器相关的关键信息"""
    try:
        result = _web_fetch_smart(url, max_chars=6000)

        if "error" in result and result.get("source") == "error":
            return {"success": False, "result": None, "error": result["error"]}

        analysis = {
            "url": url,
            "source_type": result.get("source", "unknown"),
            "title": result.get("title", "未知"),
        }

        # 合并所有文本内容用于分析
        content = ""
        for key in ("description", "content", "keywords"):
            if key in result:
                content += str(result[key]) + " "
        content_lower = content.lower()

        # 检测提到的节点类型
        node_keywords = {
            "Principled BSDF": ["principled", "principled bsdf"],
            "Glass BSDF": ["glass", "glass bsdf", "玻璃"],
            "Noise Texture": ["noise texture", "噪波", "噪声"],
            "Voronoi Texture": ["voronoi", "泰森多边形"],
            "Wave Texture": ["wave texture", "波浪"],
            "ColorRamp": ["colorramp", "color ramp", "颜色渐变"],
            "Bump": ["bump", "凹凸"],
            "Normal Map": ["normal map", "法线"],
            "Displacement": ["displacement", "置换"],
            "Mix Shader": ["mix shader", "混合着色器"],
            "Fresnel": ["fresnel", "菲涅尔"],
            "Layer Weight": ["layer weight", "层权重"],
            "Mapping": ["mapping", "映射"],
            "Math": ["math node", "数学"],
            "Subsurface": ["subsurface", "次表面", "sss"],
            "Transmission": ["transmission", "透射", "折射"],
            "Emission": ["emission", "自发光", "发光"],
            "Volume Absorption": ["volume absorption", "体积吸收"],
            "Volume Scatter": ["volume scatter", "体积散射"],
            "Shader to RGB": ["shader to rgb", "着色器转rgb"],
            "Image Texture": ["image texture", "图像纹理"],
            "Environment Texture": ["environment", "环境纹理", "hdri"],
            "Musgrave": ["musgrave"],
            "Gradient": ["gradient", "渐变"],
            "Checker": ["checker", "棋盘格"],
            "Brick": ["brick", "砖块"],
        }

        detected_nodes = []
        for node_name, keywords in node_keywords.items():
            for kw in keywords:
                if kw in content_lower:
                    detected_nodes.append(node_name)
                    break

        analysis["detected_nodes"] = detected_nodes

        # 检测材质类型
        material_keywords = {
            "水/Water": ["water", "水", "ocean", "海洋", "液体"],
            "玻璃/Glass": ["glass", "玻璃", "透明"],
            "冰/Ice": ["ice", "冰", "冰冻", "frozen"],
            "金属/Metal": ["metal", "金属", "metallic", "钢", "铁", "铜", "金"],
            "木材/Wood": ["wood", "木", "木材", "木纹"],
            "大理石/Marble": ["marble", "大理石"],
            "皮肤/Skin": ["skin", "皮肤", "sss"],
            "布料/Fabric": ["fabric", "cloth", "布", "织物"],
            "火焰/Fire": ["fire", "flame", "火", "火焰"],
            "熔岩/Lava": ["lava", "熔岩", "岩浆"],
            "水晶/Crystal": ["crystal", "水晶", "宝石"],
            "雪/Snow": ["snow", "雪"],
            "卡通/Toon": ["toon", "cartoon", "卡通", "二次元", "npr"],
        }

        detected_materials = []
        for mat_name, keywords in material_keywords.items():
            for kw in keywords:
                if kw in content_lower:
                    detected_materials.append(mat_name)
                    break

        analysis["detected_material_types"] = detected_materials

        # 检测渲染引擎
        if "eevee" in content_lower:
            analysis["render_engine"] = "EEVEE"
        elif "cycles" in content_lower:
            analysis["render_engine"] = "Cycles"
        else:
            analysis["render_engine"] = "未指定"

        # 检测关键参数
        ior_match = re.search(r'IOR[:\s]*([0-9.]+)', content, re.IGNORECASE)
        if ior_match:
            analysis["ior_value"] = float(ior_match.group(1))

        roughness_match = re.search(r'roughness[:\s]*([0-9.]+)', content, re.IGNORECASE)
        if roughness_match:
            analysis["roughness_value"] = float(roughness_match.group(1))

        # 格式化输出
        parts = [
            "=== 参考链接分析 ===",
            f"URL: {url}",
            f"来源: {analysis['source_type']}",
            f"标题: {analysis['title']}",
            f"渲染引擎: {analysis['render_engine']}",
        ]

        if detected_materials:
            parts.append(f"材质类型: {', '.join(detected_materials)}")
        if detected_nodes:
            parts.append(f"涉及节点: {', '.join(detected_nodes)}")
        if "ior_value" in analysis:
            parts.append(f"IOR值: {analysis['ior_value']}")
        if "roughness_value" in analysis:
            parts.append(f"粗糙度: {analysis['roughness_value']}")

        if "description" in result:
            parts.append(f"\n描述: {result['description']}")
        if "content" in result:
            parts.append(f"\n内容摘要: {result['content'][:2000]}")

        output = "\n".join(parts)

        try:
            from . import knowledge_base
            knowledge_base.save_search_result(
                f"ref_analysis_{analysis['title']}",
                [{"title": analysis["title"], "snippet": output[:500], "url": url,
                  "nodes": detected_nodes, "materials": detected_materials}],
                category="reference_analysis"
            )
        except Exception:
            pass

        return {"success": True, "result": output, "error": None}

    except Exception as e:
        return {"success": False, "result": None, "error": str(e)}


# ========== Tool Routing ==========

def execute_web_tool(tool_name: str, arguments: dict) -> dict:
    try:
        if tool_name == "web_search":
            return web_search(**arguments)
        elif tool_name == "web_fetch":
            return web_fetch(**arguments)
        elif tool_name == "web_search_blender":
            return web_search_blender(**arguments)
        elif tool_name == "web_analyze_reference":
            return web_analyze_reference(**arguments)
        return {"success": False, "result": None, "error": f"未知工具: {tool_name}"}
    except Exception as e:
        return {"success": False, "result": None, "error": str(e)}
