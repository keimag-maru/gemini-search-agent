import pytest

from gemini_search_agent.tools.ddg_search import DDGSearch


def filter_func(search_results):
    print(f"before: {search_results=}")
    new_search_results = []
    for result in search_results:
        if ".jp" in result.get("href", ""):
            result["contents"] = True
        new_search_results.append(result)
    print(f"after: {new_search_results=}")
    return new_search_results[:2]


def test_search_with_contents():
    ddg_search = DDGSearch(region="ja-jp", num_results=5, filter_func=filter_func)
    result = ddg_search.search_with_contents("今日のニュース")
    print(result)
    assert len(result) <= 2


@pytest.mark.asyncio
async def test_search_with_contents_async():
    ddg_search = DDGSearch(region="ja-jp", num_results=5, filter_func=filter_func)
    result = await ddg_search.search_with_contents_async("今日のニュース")
    print(result)
    assert len(result) <= 2
