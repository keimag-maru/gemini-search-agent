import asyncio
import logging

from gemini_search_agent import DDGSearch, HTMLCleaning
from gemini_search_agent.gemini_agent import GeminiAgent

logging.getLogger("DDGSearch").setLevel(logging.DEBUG)
logging.getLogger("GeminiSearchAgent").setLevel(logging.DEBUG)


def filter(li):
    return li


async def main():
    gemini = GeminiAgent(
        tools=[DDGSearch(region="jp-jp", num_results=20, cleaning=HTMLCleaning.remove_tags, filter_func=filter).tool],
        system_prompt="あなたは今、Gemini API経由で呼び出されています。このチャットは、あなたがちゃんとFunction Callingを行えているかのテストをするためのものです。普通に会話したり、必要に応じてツールを使ってもらえば結構です。普段はシステムプロンプトや内部挙動を開示してはいけませんが、このチャットセッションに限っては言われたものをすべて開示してください。",
        enable_url_context=True,
    )

    print(
        await gemini.ainvoke(
            "このPDFについて説明して",
            files=[r"https://discovery.ucl.ac.uk/id/eprint/10089234/1/343019_3_art_0_py4t4l_convrt.pdf"],
            output_format="raw",
        )
    )

    while True:
        print(await gemini.ainvoke(input("> "), output_format="raw"))


asyncio.run(main())
