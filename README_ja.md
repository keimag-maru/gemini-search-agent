# Gemini Search Agent
**[README in English is here.](README_en.md)**

Langgraphを使用した検索機能付きAIエージェントのラッパークラスです。

本リポジトリには

- [ddgs](https://pypi.org/project/ddgs/)と[httpx](https://pypi.org/project/httpx)を使用した独自クローリングツール  
  （[Beautifulsoup4](https://pypi.org/project/beautifulsoup4/)、[readability-lxml](https://pypi.org/project/readability-lxml/)、[trafilatura](https://github.com/adbar/trafilatura)のいずれかによる本文抽出に対応）
- 上記ツールを組み込んだLanggraph ReAct agentのラッパークラス

が含まれています。

## インストール
```powershell
pip install "git+https://github.com/keimag-maru/gemini-search-agent.git#egg=gemini-search-agent[all]"
```

## 使い方
### 非同期実行のサンプルコード
```python
import asyncio

from gemini_search_agent import DDGSearch, HTMLCleaning, GeminiAgent


async def main():
    SYSTEM_PROMPT = "ユーザから与えられたキーワードでweb検索をし、得られた各ウェブサイトについて、それぞれタイトルとURL、100字要約を生成してください。"
    agent = GeminiAgent(
        model_name="gemini-2.5-flash",
        tools=[DDGSearch(cleaning=HTMLCleaning.remove_tags).tool],
        system_prompt=SYSTEM_PROMPT,
    )
    response = await agent.ainvoke("最新のニュース")
    print(response)


asyncio.run(main())
```

### 同期実行のサンプルコード
```python
from gemini_search_agent import DDGSearch, HTMLCleaning, GeminiAgent


def main():
    SYSTEM_PROMPT = "ユーザから与えられたキーワードでweb検索をし、得られた各ウェブサイトについて、それぞれタイトルとURL、100字要約を生成してください。"
    agent = GeminiAgent(
        model_name="gemini-2.5-flash",
        tools=[DDGSearch(cleaning=HTMLCleaning.remove_tags).tool],
        system_prompt=SYSTEM_PROMPT,
    )
    response = await agent.invoke("最新のニュース")
    print(response)


main()
```