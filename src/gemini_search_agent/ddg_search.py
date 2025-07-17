import asyncio
import time
from enum import Enum
from typing import Dict, List, Union

import httpx
from ddgs import DDGS
from ddgs.exceptions import DDGSException, RatelimitException
from langchain_core.tools import StructuredTool


class HTMLCleaning(Enum):
    none = 0
    remove_tags = 1
    readability_lxml = 2
    trafilatura = 3


class DDGSearch:
    def __init__(
        self,
        headers: Union[Dict[str, str], None] = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36"
        },
        proxy: Union[str, None] = None,
        timeout: Union[int, None] = None,
        verify: bool = True,
        region: str = "us-en",
        safesearch: str = "moderate",
        timelimit: str | None = None,
        num_results: int | None = None,
        page: int = 1,
        backend: str | list[str] = "auto",
        cleaning: HTMLCleaning = HTMLCleaning.none,
        retries: int = 3,
        retry_delay: int = 5,
    ) -> None:
        """Initialize the DDGSearch object.

        All parameters except header, cleaning, retries and retry_delay will be passed to DDGS object.
        headers parameter will be used during scraping each websites contents with httpx.

        Args:
            headers (dict, optional): Dictionary of headers for the HTTP client. Chrome User-Agent is specified on default.
            proxy (str, optional): proxy for the HTTP client, supports http/https/socks5 protocols.
                example: "http://user:pass@example.com:3128". Defaults to None.
            timeout (int, optional): Timeout value for the HTTP client. Defaults to None.
            verify (bool): SSL verification when making the request. Defaults to True.
            region: The region to use for the search (e.g., us-en, uk-en, ru-ru, etc.).
            safesearch: The safesearch setting (e.g., on, moderate, off).
            timelimit: The timelimit for the search (e.g., d, w, m, y).
            num_results: The number of results to return.
            page: The page of results to return.
            backend: A single or list of backends. Defaults to "auto".
                - "all" : all engines are used
                - "auto" : random 3 engines are used
            cleaning (HTMLCleaning, optional): Cleaning method used after scraping each websites contents. Defaults to HTMLCleaning.none.
            retries (int, optional): Number of retries before giving up. Defaults to 3 retries.
            retry_delay (int, optional): Delay seconds between retries. Defaults to 5 seconds.
        """
        self.headers = headers
        self.proxy = proxy
        self.timeout = timeout
        self.verify = verify
        self.region = region
        self.safesearch = safesearch
        self.timelimit = timelimit
        self.backend = backend
        self.num_results = num_results
        self.page = page
        self.cleaning = cleaning
        if cleaning == HTMLCleaning.remove_tags:
            try:
                from bs4 import BeautifulSoup  # noqa: F401
            except ImportError:
                raise ImportError(
                    "Please run `pip install BeautifulSoup4` or try `pip install gemini-search-agent[all]`"
                )
        elif cleaning == HTMLCleaning.readability_lxml:
            try:
                import readability  # noqa: F401
            except ImportError:
                raise ImportError(
                    "Please run `pip install readability-lxml` or try `pip install gemini-search-agent[all]`"
                )
        elif cleaning == HTMLCleaning.trafilatura:
            try:
                import trafilatura  # noqa: F401
            except ImportError:
                raise ImportError(
                    "Please run `pip install trafilatura[all]` or try `pip install gemini-search-agent[all]`"
                )
        self.retries = retries
        self.retry_delay = retry_delay
        self.tool: StructuredTool = StructuredTool.from_function(
            func=self.search_with_contents, coroutine=self.async_search_with_contents
        )

    def search_with_contents(
        self,
        query: str,
    ) -> Union[List[Dict[str, str]], str]:
        """Search keywrods with DuckDuckGo Text Search and return search results with each websites' contents.

        Args:
            query (str): Search Query (Query params: https://duckduckgo.com/params).

        Returns:
            List of dictionaries with search results with each websites' contents,
            or String "Failed to get search results, reason: {reason}" if there was an error.
        """
        with httpx.Client(headers=self.headers, follow_redirects=True) as client:
            search_results: List[Dict[str, str]] = []
            for _ in range(self.retries):
                try:
                    with DDGS(self.proxy, self.timeout, self.verify) as ddgs:
                        search_results = ddgs.text(
                            query=query,
                            region=self.region,
                            safesearch=self.safesearch,
                            timelimit=self.timelimit,
                            num_results=self.num_results,
                            page=self.page,
                            backend=self.backend,
                        )
                except RatelimitException as e:
                    time.sleep(self.retry_delay)
                    continue
                except DDGSException as e:
                    return f"Failed to get search results, reason: {e.__class__.__name__} {e}"
                else:
                    break
            if not search_results:
                return f"Failed to get search results, reason: Empty search results was provided from DuckDuckGo after {self.retries} retries."
            for result in search_results:
                url = result.get("href", "")
                result["content"] = self._get_website_contents(client, url)
            return search_results

    def _get_website_contents(self, client: httpx.Client, url: str) -> str:
        """Get specified website contents.

        Args:
            client (httpx.AsyncClient): httpx syncronous client.
            url (str): Target website url.

        Returns:
            String of website contents HTML (may be cleaned depends on HTMLCleaning parameter),
            or String "Failed to get website contents, reason: {reason}" if there was an error.
        """
        if not url:
            return "Failed to get website contents, reason: No url was provided."
        website_contents = None
        for _ in range(self.retries):
            try:
                resp = client.get(url)
                resp.raise_for_status()
                html = resp.text
                website_contents = self._clean_html(html)
            except httpx.HTTPStatusError as e:
                time.sleep(self.retry_delay)
                continue
            except Exception as e:
                return f"Failed to get website contents, reason: {e.__class__.__name__} {e}"
            else:
                break
        if website_contents:
            return website_contents
        else:
            return f"Failed to get website contents, reason: Empty contents was provided from {url} after {self.retries} retries."

    async def async_search_with_contents(
        self,
        query: str,
    ) -> Union[List[Dict[str, str]], str]:
        """Search keywrods with DuckDuckGo Text Search and return search results with each websites' contents asyncronously.

        Args:
            query (str): Search Query (Query params: https://duckduckgo.com/params).

        Returns:
            List of dictionaries with search results with each websites' contents,
            or String "Failed to get search results, reason: {reason}" if there was an error.
        """
        async with httpx.AsyncClient(headers=self.headers, follow_redirects=True) as client:
            search_results: List[Dict[str, str]] = []
            for _ in range(self.retries):
                try:
                    with DDGS(self.proxy, self.timeout, self.verify) as ddgs:
                        search_results = ddgs.text(
                            query=query,
                            region=self.region,
                            safesearch=self.safesearch,
                            timelimit=self.timelimit,
                            num_results=self.num_results,
                            page=self.page,
                            backend=self.backend,
                        )
                except RatelimitException as e:
                    await asyncio.sleep(self.retry_delay)
                    continue
                except DDGSException as e:
                    return f"Failed to get search results, reason: {e.__class__.__name__} {e}"
                else:
                    break
            if not search_results:
                return f"Failed to get search results, reason: Empty search results was provided from DuckDuckGo after {self.retries} retries."
            urls = [result.get("href", "") for result in search_results]
            tasks = [self._async_get_website_contents(client, url) for url in urls]
            website_contents = await asyncio.gather(*tasks)
            for result, content in zip(search_results, website_contents):
                result["content"] = content
            return search_results

    async def _async_get_website_contents(self, client: httpx.AsyncClient, url: str) -> str:
        """Get specified website contents asyncronously.

        Args:
            client (httpx.AsyncClient): httpx asyncronous client.
            url (str): Target website url.

        Returns:
            String of website contents HTML (may be cleaned depends on HTMLCleaning parameter),
            or String "Failed to get website contents, reason: {reason}" if there was an error.
        """
        if not url:
            return "Failed to get website contents, reason: No url was provided."
        website_contents = None
        for _ in range(self.retries):
            try:
                resp = await client.get(url)
                resp.raise_for_status()
                html = resp.text
                website_contents = self._clean_html(html)
            except httpx.HTTPStatusError as e:
                await asyncio.sleep(self.retry_delay)
                continue
            except Exception as e:
                return f"Failed to get website contents, reason: {e.__class__.__name__} {e}"
            else:
                break
        if website_contents:
            return website_contents
        else:
            return f"Failed to get website contents, reason: Empty contents was provided from {url} after {self.retries} retries."

    def _clean_html(self, html: str):
        if self.cleaning == HTMLCleaning.remove_tags:
            CLEANED_TAGS = ["script", "style", "header", "footer", "nav", "aside", "form"]
            soup = BeautifulSoup(html, "html.parser")  # type: ignore # noqa: F821
            for tag in soup.find_all(CLEANED_TAGS):
                tag.decompose()
            return str(soup)
        elif self.cleaning == HTMLCleaning.readability_lxml:
            return readability.Document(html).summary()  # type: ignore # noqa: F821
        elif self.cleaning == HTMLCleaning.trafilatura:
            return trafilatura.extract(  # type: ignore # noqa: F821
                html,
                output_format="html",
                with_metadata=True,
                include_comments=True,
                include_tables=True,
                include_formatting=True,
            )
        else:
            return html
