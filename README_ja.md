# Gemini Search Agent
**[README in English is here.](README_en.md)**

検索機能付きGemini AIエージェントです。

本リポジトリには

- [ddgs](https://pypi.org/project/ddgs/)と[httpx](https://pypi.org/project/httpx)を使用した独自クローリングツール  
  （[Beautifulsoup4](https://pypi.org/project/beautifulsoup4/)、[readability-lxml](https://pypi.org/project/readability-lxml/)、[trafilatura](https://github.com/adbar/trafilatura)のいずれかによる本文抽出に対応）
- 上記ツールを組み込んだ[`google-genai` SDK](https://ai.google.dev/gemini-api/docs/libraries?hl=ja)のラッパークラス

が含まれています。


>[!CAUTION] 破壊的変更
>version 2.0.0以降では、langchainとlanggraphの使用を止め、`google-genai`での実装に切り替えました。  
>これにより、パッケージサイズの縮小やGeminiの最新仕様への追従が可能になりました。  
>**version2.0.0時点では、GeminiAgentの`invoke`メソッドが未実装**なほか、
>これまで使用できていた**オプションパラメータや機能が廃止、変更されている**ので、注意してください。  
>**version 1.xx から移行する場合には[こちら](https://github.com/keimag-maru/gemini-search-agent/releases/tag/v2.0.0)をご確認いただき、コードの修正をお願いします。**


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
    SYSTEM_PROMPT = "ユーザから与えられたキーワードでweb検索をし、得られた各ウェブサイトについて、それぞれタイトルとURL、100字要約を生成してください。必要であれば添付した2つのPDFファイルを参照しても構いません。"
    agent = GeminiAgent(
        model_name="gemini-2.5-flash",
        tools=[DDGSearch(cleaning=HTMLCleaning.remove_tags).tool],
        system_prompt=SYSTEM_PROMPT,
        files = ["local.pdf", "https://example.com/network.pdf"]
    )
    response = await agent.ainvoke("最新のニュース")
    print(response)


asyncio.run(main())
```

### ~~同期実行のサンプルコード~~
>[!NOTE]
>同期実行はversion2の大幅な改変により、現在未実装です。

<!-- ```python
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
``` -->