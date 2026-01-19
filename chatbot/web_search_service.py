import logging
from tavily import TavilyClient

logger = logging.getLogger(__name__)


class TavilyWebSearchService:
    def __init__(self, api_key: str):
        self.client = TavilyClient(api_key=api_key)

    def search(self, query: str, max_results: int = 5) -> dict:
        if not query or not isinstance(query, str) or len(query) > 400:
            return {
                "success": False,
                "results": [],
                "error": "Query invalid or exceeds 400 characters"
            }

        try:
            response = self.client.search(query=query, max_results=max_results)
            results = [
                {
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "content": item.get("content", "")
                }
                for item in response.get("results", [])[:max_results]
            ]
            return {"success": True, "results": results, "error": None}
        except Exception as e:
            logger.error(f"Web search error: {e}")
            return {"success": False, "results": [], "error": str(e)}
