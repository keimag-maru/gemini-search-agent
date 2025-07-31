# Gemini Search Agent
**[日本語版READMEはこちら](README_ja.md)**

This is a wrapper class for an AI agent with search functionality using Langgraph.

This repository includes
- A custom crawling tool using [ddgs](https://pypi.org/project/ddgs/) and [httpx](https://pypi.org/project/httpx) and httpx.  
    (Supports text extraction using [Beautifulsoup4](https://pypi.org/project/beautifulsoup4/), [readability-lxml](https://pypi.org/project/readability-lxml/), or [trafilatura](https://github.com/adbar/trafilatura))
- A wrapper class for the Langgraph ReAct agent incorporating the above tools

## Installation
```powershell
pip install "git+https://github.com/keimag-maru/gemini-search-agent.git#egg=gemini-search-agent[all]"
```

## Usage
### Sample code for asynchronous execution
```python
import asyncio

from gemini_search_agent import DDGSearch, HTMLCleaning, GeminiAgent


async def main():
    SYSTEM_PROMPT = "Perform a web search using user-supplied keywords and generate a title, URL, and a 100-character summary for each website found."
    agent = GeminiAgent(
        model_name="gemini-2.5-flash",
        tools=[DDGSearch(cleaning=HTMLCleaning.remove_tags).tool],
        system_prompt=SYSTEM_PROMPT,
    )
    response = await agent.ainvoke("the latest news")
    print(response)


asyncio.run(main())
```

### Sample code for synchronous execution
```python
from gemini_search_agent import DDGSearch, HTMLCleaning, GeminiAgent


def main():
    SYSTEM_PROMPT = "Perform a web search using user-supplied keywords and generate a title, URL, and a 100-character summary for each website found."
    agent = GeminiAgent(
        model_name="gemini-2.5-flash",
        tools=[DDGSearch(cleaning=HTMLCleaning.remove_tags).tool],
        system_prompt=SYSTEM_PROMPT,
    )
    response = await agent.invoke("the latest news")
    print(response)


main()
```