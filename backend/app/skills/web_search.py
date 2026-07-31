import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


def search_web(query: str, max_results: int = 5) -> str:
    """Search the web using the configured provider with automatic fallback."""
    provider = settings.web_search_provider.lower().strip()

    providers = {
        "tavily": _search_tavily,
        "serpapi": _search_serpapi,
        "duckduckgo": _search_ddgs,
    }

    if provider in providers:
        if provider == "tavily" and not settings.tavily_api_key:
            logger.warning("Tavily selected but TAVILY_API_KEY is empty, falling back to DuckDuckGo")
        elif provider == "serpapi" and not settings.serpapi_api_key:
            logger.warning("SerpAPI selected but SERPAPI_API_KEY is empty, falling back to DuckDuckGo")
        else:
            result = providers[provider](query, max_results)
            if not result.startswith("Web search failed"):
                return result

    if settings.tavily_api_key:
        result = _search_tavily(query, max_results)
        if not result.startswith("Tavily search error"):
            return result

    if settings.serpapi_api_key:
        result = _search_serpapi(query, max_results)
        if not result.startswith("SerpAPI search error"):
            return result

    return _search_ddgs(query, max_results)


def _format_results(query: str, provider: str, items: list[dict]) -> str:
    lines = [f"Web search results for: {query} (via {provider})\n"]
    for i, item in enumerate(items, 1):
        title = item.get("title", "Untitled")
        url = item.get("url", "")
        content = item.get("content", item.get("snippet", ""))
        lines.append(f"{i}. **{title}**")
        if url:
            lines.append(f"   URL: {url}")
        if content:
            lines.append(f"   {content[:400]}")
        lines.append("")
    return "\n".join(lines) if len(lines) > 1 else f"No results found for: {query}"


def _search_tavily(query: str, max_results: int) -> str:
    try:
        resp = httpx.post(
            "https://api.tavily.com/search",
            json={
                "api_key": settings.tavily_api_key,
                "query": query,
                "max_results": max_results,
                "include_answer": True,
                "search_depth": "basic",
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        lines = [f"Web search results for: {query} (via Tavily)\n"]
        if data.get("answer"):
            lines.append(f"**AI Summary:** {data['answer']}\n")

        items = [
            {
                "title": r.get("title", "Untitled"),
                "url": r.get("url", ""),
                "content": r.get("content", ""),
            }
            for r in data.get("results", [])
        ]
        if items:
            lines.append(_format_results(query, "Tavily", items).split("\n", 1)[-1])
            return "\n".join(lines)

        return f"No Tavily results for: {query}"
    except Exception as e:
        logger.error("Tavily search failed: %s", e)
        return f"Tavily search error: {e}"


def _search_serpapi(query: str, max_results: int) -> str:
    try:
        resp = httpx.get(
            "https://serpapi.com/search",
            params={
                "q": query,
                "api_key": settings.serpapi_api_key,
                "engine": "google",
                "num": max_results,
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        items = []
        if data.get("answer_box", {}).get("answer"):
            items.append({
                "title": "Direct Answer",
                "url": data["answer_box"].get("link", ""),
                "content": data["answer_box"]["answer"],
            })

        for r in data.get("organic_results", [])[:max_results]:
            items.append({
                "title": r.get("title", "Untitled"),
                "url": r.get("link", ""),
                "content": r.get("snippet", ""),
            })

        return _format_results(query, "SerpAPI/Google", items) if items else f"No SerpAPI results for: {query}"
    except Exception as e:
        logger.error("SerpAPI search failed: %s", e)
        return f"SerpAPI search error: {e}"


def _search_ddgs(query: str, max_results: int) -> str:
    try:
        from ddgs import DDGS

        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))

        if not results:
            return _search_duckduckgo_instant(query)

        items = [
            {
                "title": r.get("title", "Untitled"),
                "url": r.get("href", r.get("link", "")),
                "content": r.get("body", r.get("snippet", "")),
            }
            for r in results
        ]
        return _format_results(query, "DuckDuckGo", items)
    except ImportError:
        logger.warning("ddgs not installed, using instant answer API")
        return _search_duckduckgo_instant(query)
    except Exception as e:
        logger.error("DDGS search failed: %s", e)
        return f"Web search failed: {e}\n{_search_duckduckgo_instant(query)}"


def _search_duckduckgo_instant(query: str) -> str:
    """Legacy DuckDuckGo instant answer API (limited but no extra deps)."""
    try:
        resp = httpx.get(
            "https://api.duckduckgo.com/",
            params={"q": query, "format": "json", "no_html": 1, "skip_disambig": 1},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()

        lines = [f"DuckDuckGo instant results for: {query}\n"]
        if data.get("AbstractText"):
            lines.append(f"Summary: {data['AbstractText']}")
            if data.get("AbstractURL"):
                lines.append(f"Source: {data['AbstractURL']}")
            lines.append("")

        for topic in data.get("RelatedTopics", [])[:5]:
            if isinstance(topic, dict) and topic.get("Text"):
                lines.append(f"- {topic['Text']}")
                if topic.get("FirstURL"):
                    lines.append(f"  {topic['FirstURL']}")

        return "\n".join(lines) if len(lines) > 1 else f"No DuckDuckGo results for: {query}"
    except Exception as e:
        logger.error("DuckDuckGo instant search failed: %s", e)
        return f"Web search failed: {e}"
