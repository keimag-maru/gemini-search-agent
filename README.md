# Gemini Search Agent
**[日本語版READMEはこちら](README_ja.md)**

This is a wrapper class for an AI agent with search functionality using Langgraph.

This repository includes
- A custom crawling tool using duckduckgo-search  
    (Supports text extraction using Beautifulsoup4, readability-lxml, or trafilatura)
- A wrapper class for the Langgraph react agent incorporating the above tools

## Installation
```powershell
pip install "git+https://github.com/keimag-maru/gemini-search-agent.git#egg=gemini-search-agent[all]"
```

## Usage
### Sample code for asyncronous execution
```python
import asyncio

from gemini_search_agent.ddg_search import DDGSearch, HTMLCleaning
from gemini_search_agent.gemini_agent import GeminiAgent


async def main():
    SYSTEM_PROMPT = "Perform a web search using user-supplied keywords and generate a title, URL, and a 100-character summary for each website found."
    agent = GeminiAgent(
        model_name="gemini-2.5-flash-lite",
        tools=[DDGSearch(cleaning=HTMLCleaning.remove_tags).tool],
        system_prompt=SYSTEM_PROMPT,
    )
    response = await agent.ainvoke("the latest news")
    print(response)


asyncio.run(main())
```

### Sample code for syncronous execution
```python
from gemini_search_agent.ddg_search import DDGSearch, HTMLCleaning
from gemini_search_agent.gemini_agent import GeminiAgent


def main():
    SYSTEM_PROMPT = "Perform a web search using user-supplied keywords and generate a title, URL, and a 100-character summary for each website found."
    agent = GeminiAgent(
        model_name="gemini-2.5-flash-lite",
        tools=[DDGSearch(cleaning=HTMLCleaning.remove_tags).tool],
        system_prompt=SYSTEM_PROMPT,
    )
    response = await agent.invoke("the latest news")
    print(response)


main()
```