import asyncio
import time
from enum import Enum
from logging import getLogger
from typing import Callable, Dict, List, Union

import httpx
from ddgs import DDGS
from ddgs.exceptions import DDGSException, RatelimitException
from google.genai import types

from .tool import Tool


class HTMLCleaning(Enum):
    none = 0
    remove_tags = 1
    readability_lxml = 2
    trafilatura = 3


class DDGSearchCache:
    def __init__(self, max_size: int = 50, max_age: int = -1, gc_timing: int = 10) -> None:
        self.data = {}
        self.metadata = []  # [(data-key, create-time)]
        self.max_size = max_size
        self.max_age = max_age
        self.gc_timing = gc_timing
        self.num_of_calling = 0

    def add(self, key, value):
        self.num_of_calling += 1
        self.data[key] = value
        self.metadata.append((key, time.time()))
        if self.gc_timing <= 0 or self.num_of_calling % self.gc_timing == 0:
            self.remove_expired()

    def get(self, key, default=None):
        self.num_of_calling += 1
        if self.gc_timing <= 0 or self.num_of_calling % self.gc_timing == 0:
            self.remove_expired()
        return self.data.get(key, default)

    def remove(self, key):
        self.num_of_calling += 1
        del self.data[key]
        if self.gc_timing <= 0 or self.num_of_calling % self.gc_timing == 0:
            self.remove_expired()

    def clear(self):
        self.num_of_calling = 0
        self.data.clear()
        self.metadata.clear()

    def remove_expired(self):
        """max_sizeになるように古い順に消す。そのあと、max_ageよりも古いものを消す"""
        self.metadata.sort(key=lambda x: x[1])
        if self.max_size >= 0:
            while len(self.data) > self.max_size:
                key, _ = self.metadata.pop(0)
                del self.data[key]
        if self.max_age >= 0:
            while self.metadata and time.time() - self.metadata[-1][1] > self.max_age:
                key, _ = self.metadata.pop()
                del self.data[key]

    def __len__(self):
        return len(self.data)

    def __iter__(self):
        return iter(self.data)

    def __getitem__(self, key):
        self.num_of_calling += 1
        if self.gc_timing <= 0 or self.num_of_calling % self.gc_timing == 0:
            self.remove_expired()
        return self.data[key]

    def __setitem__(self, key, value):
        self.add(key, value)

    def __delitem__(self, key):
        self.remove(key)

    def __contains__(self, key):
        return key in self.data

    def __str__(self):
        return str(self.data)

    def __repr__(self):
        return repr(self.data)


class DDGSearch:
    logger = getLogger("DDGSearch")

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
        timelimit: Union[str, None] = None,
        num_results: Union[int, None] = None,
        page: int = 1,
        backend: Union[str, List[str]] = "auto",
        cleaning: Union[HTMLCleaning, Callable] = HTMLCleaning.none,
        filter_func: Union[Callable, None] = None,
        cache: Union[DDGSearchCache, None] = DDGSearchCache(),
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
            safesearch: The safe-search setting (e.g., on, moderate, off).
            timelimit: The time limit for the search (e.g., d, w, m, y).
            num_results: The number of results to return.
            page: The page of results to return.
            backend: A single or list of backends. Defaults to "auto".
                - "all" : all engines are used
                - "auto" : random 3 engines are used
            cleaning (HTMLCleaning | Callable, optional): Cleaning method used after scraping each websites contents. Defaults to HTMLCleaning.none.
            filter_func (Callable, optional): A function or method filtering search results to determine which sites to scrape and returns.
                - **input**: DDGS result dict.
                - **output**: DDGS result dict. (You can edit DDGS result dict on your own. Website contents will be added to only results where "contents" key is included.)
                - [**Caution**] Please be careful not to remove "href" key, otherwise error will be occurred in _get_website_contents method.
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
                    "This feature requires additional dependency. Please run `pip install BeautifulSoup4`."
                )
        elif cleaning == HTMLCleaning.readability_lxml:
            try:
                import readability  # noqa: F401
            except ImportError:
                raise ImportError(
                    "This feature requires additional dependency. Please run `pip install readability-lxml`."
                )
        elif cleaning == HTMLCleaning.trafilatura:
            try:
                import trafilatura  # noqa: F401
            except ImportError:
                raise ImportError(
                    "This feature requires additional dependency. Please run `pip install trafilatura[all]`."
                )
        self.cache = cache
        self.retries = retries
        self.retry_delay = retry_delay
        self.filter_func = filter_func

    @property
    def tool(self) -> Tool:
        return Tool(
            func=self.search_with_contents,
            coroutine=self.search_with_contents_async,
            declaration={
                "name": "search_with_contents",
                "description": "Search keywords with DuckDuckGo Text Search and return search results with each websites' contents.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query (general search commands are available such as `-{excludeword}`, `site:{website}` and `filetype:{filetype}`), e.g. 今日の天気 site:tenki.jp",
                        }
                    },
                    "required": ["query"],
                },
            },
        )

    def search_with_contents(
        self,
        query: str,
    ) -> Union[List[Dict[str, str]], str]:
        """Search keywords with DuckDuckGo Text Search and return search results with each websites' contents.

        Args:
            query (str): Search query (Query params: https://duckduckgo.com/params).

        Returns:
            List of dictionaries with search results with each websites' contents,
            or String "Failed to get search results, reason: {reason}" if there was an error.
        """
        self.logger.info(f"search_with_contents({query=})")
        with httpx.Client(
            headers=self.headers, verify=self.verify, timeout=self.timeout, follow_redirects=True
        ) as client:
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
                        if not search_results:
                            time.sleep(self.retry_delay)
                            continue
                        if self.num_results and len(search_results) > self.num_results:
                            search_results = search_results[: self.num_results]
                except RatelimitException:
                    time.sleep(self.retry_delay)
                    continue
                except DDGSException as e:
                    self.logger.error(
                        f"search_with_contents: Failed to get search results, reason: {e.__class__.__name__} {e}"
                    )
                    return f"Failed to get search results, reason: {e.__class__.__name__} {e}"
                else:
                    break
            if not search_results:
                self.logger.error(
                    f"search_with_contents: Failed to get search results, reason: Empty search results was provided from DuckDuckGo after {self.retries} retries."
                )
                return f"Failed to get search results, reason: Empty search results was provided from DuckDuckGo after {self.retries} retries."
            if self.filter_func:
                search_results = self.filter_func(search_results)
            for result in search_results:
                if (not self.filter_func) or ("contents" in result):
                    url = result.get("href", "")
                    result["contents"] = self._get_website_contents(client, url)
            self.logger.debug(f"search_with_contents: {search_results=}")
            return search_results

    def _get_website_contents(self, client: httpx.Client, url: str) -> str:
        """Get specified website contents.

        Args:
            client (httpx.AsyncClient): httpx synchronous client.
            url (str): Target website url.

        Returns:
            String of website contents HTML (may be cleaned depends on HTMLCleaning parameter),
            or String "Failed to get website contents, reason: {reason}" if there was an error.
        """
        self.logger.debug(f"_get_website_contents({client=}, {url=})")
        if not url:
            return "Failed to get website contents, reason: No url was provided."
        if self.cache:
            self.logger.debug(f"Data for {url} was found in cache.")
            website_contents = self.cache.get(url, None)
        else:
            website_contents = None
            for _ in range(self.retries):
                try:
                    resp = client.get(url)
                    resp.raise_for_status()
                    html = resp.text
                    website_contents = self._clean_html(html)
                    if not website_contents:
                        time.sleep(self.retry_delay)
                        continue
                except httpx.HTTPStatusError as e:
                    self.logger.debug(
                        f"_get_website_contents: HTTPStatusError {e}, Retrying in {self.retry_delay} seconds..."
                    )
                    time.sleep(self.retry_delay)
                    continue
                except Exception as e:
                    self.logger.error(
                        f"_get_website_contents: Failed to get website contents, reason: {e.__class__.__name__} {e}"
                    )
                    return f"Failed to get website contents, reason: {e.__class__.__name__} {e}"
                else:
                    if self.cache:
                        self.cache.add(url, website_contents)
                    break
        if website_contents:
            return website_contents
        else:
            self.logger.error(
                f"_get_website_contents: Failed to get website contents, reason: Empty contents was provided from {url} after {self.retries} retries."
            )
            return f"Failed to get website contents, reason: Empty contents was provided from {url} after {self.retries} retries."

    async def search_with_contents_async(
        self,
        query: str,
    ) -> Union[List[Dict[str, str]], str]:
        """Search keywords with DuckDuckGo Text Search and return search results with each websites' contents asynchronously.

        Args:
            query (str): Search Query (Query params: https://duckduckgo.com/params).

        Returns:
            List of dictionaries with search results with each websites' contents,
            or String "Failed to get search results, reason: {reason}" if there was an error.
        """
        self.logger.info(f"search_with_contents_async({query=})")
        async with httpx.AsyncClient(
            headers=self.headers, verify=self.verify, timeout=self.timeout, follow_redirects=True
        ) as client:
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
                        if not search_results:
                            await asyncio.sleep(self.retry_delay)
                            continue
                        if self.num_results and len(search_results) > self.num_results:
                            search_results = search_results[: self.num_results]
                except RatelimitException:
                    await asyncio.sleep(self.retry_delay)
                    continue
                except DDGSException as e:
                    self.logger.error(
                        f"async_search_with_contents: Failed to get search results, reason: {e.__class__.__name__} {e}"
                    )
                    return f"Failed to get search results, reason: {e.__class__.__name__} {e}"
                else:
                    break
            if not search_results:
                self.logger.error(
                    f"async_search_with_contents: Failed to get search results, reason: Empty search results was provided from DuckDuckGo after {self.retries} retries."
                )
                return f"Failed to get search results, reason: Empty search results was provided from DuckDuckGo after {self.retries} retries."
            if self.filter_func:
                search_results = self.filter_func(search_results)
            urls = [
                (i, result.get("href", ""))
                for i, result in enumerate(search_results)
                if (not self.filter_func) or ("contents" in result)
            ]  # (index, url)
            tasks = [self._get_website_contents_async(client, url[1]) for url in urls]
            website_contents = await asyncio.gather(*tasks)
            for (i, _), contents in zip(urls, website_contents):
                search_results[i]["contents"] = contents
            self.logger.debug(f"search_with_contents_async: {search_results=}")
            return search_results

    async def _get_website_contents_async(self, client: httpx.AsyncClient, url: str) -> str:
        """Get specified website contents asynchronously.

        Args:
            client (httpx.AsyncClient): httpx asynchronous client.
            url (str): Target website url.

        Returns:
            String of website contents HTML (may be cleaned depends on HTMLCleaning parameter),
            or String "Failed to get website contents, reason: {reason}" if there was an error.
        """
        self.logger.debug(f"_get_website_contents_async({client=}, {url=})")
        if not url:
            return "Failed to get website contents, reason: No url was provided."
        if self.cache:
            self.logger.debug(f"Data for {url} was found in cache.")
            website_contents = self.cache.get(url, None)
        else:
            website_contents = None
            for _ in range(self.retries):
                try:
                    resp = await client.get(url)
                    resp.raise_for_status()
                    html = resp.text
                    website_contents = self._clean_html(html)
                    if not website_contents:
                        await asyncio.sleep(self.retry_delay)
                        continue
                except httpx.HTTPStatusError as e:
                    self.logger.debug(
                        f"_async_get_website_contents: HTTPStatusError {e}, Retrying in {self.retry_delay} seconds..."
                    )
                    await asyncio.sleep(self.retry_delay)
                    continue
                except Exception as e:
                    self.logger.error(
                        f"_async_get_website_contents: Failed to get website contents, reason: {e.__class__.__name__} {e}"
                    )
                    return f"Failed to get website contents, reason: {e.__class__.__name__} {e}"
                else:
                    if self.cache:
                        self.cache.add(url, website_contents)
                    break
        if website_contents:
            return website_contents
        else:
            self.logger.error(
                f"_async_get_website_contents: Failed to get website contents, reason: Empty contents was provided from {url} after {self.retries} retries."
            )
            return f"Failed to get website contents, reason: Empty contents was provided from {url} after {self.retries} retries."

    def _clean_html(self, html: str):
        if not html:
            return html
        try:
            if self.cleaning == HTMLCleaning.remove_tags:
                from bs4 import BeautifulSoup
                # may use from cache because this has been already imported in __init__ with error handling.

                CLEANED_TAGS = ["script", "style", "header", "footer", "nav", "aside", "form"]
                soup = BeautifulSoup(html, "html.parser")  # type: ignore # noqa: F821
                for tag in soup.find_all(CLEANED_TAGS):
                    tag.decompose()
                return str(soup)
            elif self.cleaning == HTMLCleaning.readability_lxml:
                import readability  # may use from cache because this has been already imported in __init__ with error handling.

                return readability.Document(html).summary()  # type: ignore # noqa: F821
            elif self.cleaning == HTMLCleaning.trafilatura:
                import trafilatura  # may use from cache because this has been already imported in __init__ with error handling.

                return trafilatura.extract(  # type: ignore # noqa: F821
                    html,
                    output_format="html",
                    with_metadata=False,  # avoid TypeError
                    include_comments=True,
                    include_tables=True,
                    include_formatting=True,
                )
            elif isinstance(self.cleaning, Callable):
                return self.cleaning(html)
            else:
                return html
        except Exception as e:
            self.logger.error(
                f"_clean_html: Failed to clean HTML, reason: {e.__class__.__name__} {e}. Cleaning did not applied.",
                exc_info=True,
            )
            return html


__all__ = ["HTMLCleaning", "DDGSearch", "DDGSearchCache"]
