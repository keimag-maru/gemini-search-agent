# Gemini Search Agent
**[README in English is here.](README.md)**

Langgraphを使用した検索機能付きAIエージェントのラッパークラスです。

本リポジトリには

- duckduckgo-search使用した独自クローリングツール  
  （Beautifulsoup4、readability-lxml、trafilaturaのいずれかによる本文抽出に対応）
- 上記ツールを組み込んだLanggraph react agentのラッパークラス

が含まれています。

## インストール
```powershell
pip install "git+https://github.com/keimag-maru/gemini-search-agent.git#egg=gemini-search-agent[all]"
```

## 使い方
### 非同期実行のサンプルコード
```python
import asyncio

from gemini_search_agent.ddg_search import DDGSearch, HTMLCleaning
from gemini_search_agent.gemini_agent import GeminiAgent


async def main():
    SYSTEM_PROMPT = "ユーザから与えられたキーワードでweb検索をし、得られた各ウェブサイトについて、それぞれタイトルとURL、100字要約を生成してください。"
    agent = GeminiAgent(
        model_name="gemini-2.5-flash-lite",
        tools=[DDGSearch(cleaning=HTMLCleaning.remove_tags).tool],
        system_prompt=SYSTEM_PROMPT,
    )
    response = await agent.ainvoke("最新のニュース")
    print(response)


asyncio.run(main())
```

### 同期実行のサンプルコード
```python
from gemini_search_agent.ddg_search import DDGSearch, HTMLCleaning
from gemini_search_agent.gemini_agent import GeminiAgent


def main():
    SYSTEM_PROMPT = "ユーザから与えられたキーワードでweb検索をし、得られた各ウェブサイトについて、それぞれタイトルとURL、100字要約を生成してください。"
    agent = GeminiAgent(
        model_name="gemini-2.5-flash-lite",
        tools=[DDGSearch(cleaning=HTMLCleaning.remove_tags).tool],
        system_prompt=SYSTEM_PROMPT,
    )
    response = await agent.invoke("最新のニュース")
    print(response)


main()
```