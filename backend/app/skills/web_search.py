import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


def search_web(query: str, max_results: int = 5) -> str:
    if settings.tavily_api_key:
        return _search_tavily(query, max_results)
    if settings.web_search_provider == "duckduckgo":
        return _search_duckduckgo(query)
    return (
        f"No web search API configured for query: '{query}'.\n"
        "Set TAVILY_API_KEY in .env (https://tavily.com) or WEB_SEARCH_PROVIDER=duckduckgo."
    )


def _search_tavily(query: str, max_results: int) -> str:
    try:
        resp = httpx.post(
            "https://api.tavily.com/search",
            json={
                "api_key": settings.tavily_api_key,
                "query": query,
                "max_results": max_results,
                "include_answer": True,
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        lines = [f"Web search results for: {query}\n"]
        if data.get("answer"):
            lines.append(f"Summary: {data['answer']}\n")

        for i, result in enumerate(data.get("results", []), 1):
            title = result.get("title", "Untitled")
            url = result.get("url", "")
            content = result.get("content", "")
            lines.append(f"{i}. **{title}**")
            lines.append(f"   URL: {url}")
            lines.append(f"   {content[:300]}")
            lines.append("")

        return "\n".join(lines) if len(lines) > 1 else f"No results found for: {query}"
    except Exception as e:
        logger.error("Tavily search failed: %s", e)
        return f"Tavily search error: {e}. Falling back to DuckDuckGo.\n{_search_duckduckgo(query)}"


def _search_duckduckgo(query: str) -> str:
    try:
        resp = httpx.get(
            "https://api.duckduckgo.com/",
            params={"q": query, "format": "json", "no_html": 1, "skip_disambig": 1},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()

        lines = [f"DuckDuckGo results for: {query}\n"]
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
        logger.error("DuckDuckGo search failed: %s", e)
        return f"Web search failed: {e}"
