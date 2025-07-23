from gemini_search_agent.ddg_search import DDGSearch, HTMLCleaning
from gemini_search_agent.gemini_agent import GeminiAgent


def test_agent_search():
    SYSTEM_PROMPT = "ユーザから与えられたキーワードでweb検索をし、得られた各ウェブサイトについて、それぞれタイトルとURL、100字要約を生成してください。"
    agent = GeminiAgent(
        model_name="gemini-2.5-flash-lite-preview-06-17",
        tools=[DDGSearch(cleaning=HTMLCleaning.none).tool],
        system_prompt=SYSTEM_PROMPT,
    )
    response = agent.invoke("最新のニュース")
    assert response is not None
    print("メソッド: ", HTMLCleaning.none)
    print("レスポンス:", response)


def test_agent_search_remove_tags():
    SYSTEM_PROMPT = "ユーザから与えられたキーワードでweb検索をし、得られた各ウェブサイトについて、それぞれタイトルとURL、100字要約を生成してください。"
    agent = GeminiAgent(
        model_name="gemini-2.5-flash-lite-preview-06-17",
        tools=[DDGSearch(cleaning=HTMLCleaning.remove_tags).tool],
        system_prompt=SYSTEM_PROMPT,
    )
    response = agent.invoke("最新のニュース")
    assert response is not None
    print("メソッド: ", HTMLCleaning.none)
    print("レスポンス:", response)


def test_agent_search_readability_lxml():
    SYSTEM_PROMPT = "ユーザから与えられたキーワードでweb検索をし、得られた各ウェブサイトについて、それぞれタイトルとURL、100字要約を生成してください。"
    agent = GeminiAgent(
        model_name="gemini-2.5-flash-lite-preview-06-17",
        tools=[DDGSearch(cleaning=HTMLCleaning.readability_lxml).tool],
        system_prompt=SYSTEM_PROMPT,
    )
    response = agent.invoke("最新のニュース")
    assert response is not None
    print("メソッド: ", HTMLCleaning.none)
    print("レスポンス:", response)


def test_agent_search_trafilatura():
    SYSTEM_PROMPT = "ユーザから与えられたキーワードでweb検索をし、得られた各ウェブサイトについて、それぞれタイトルとURL、100字要約を生成してください。"
    agent = GeminiAgent(
        model_name="gemini-2.5-flash-lite-preview-06-17",
        tools=[DDGSearch(cleaning=HTMLCleaning.trafilatura).tool],
        system_prompt=SYSTEM_PROMPT,
    )
    response = agent.invoke("最新のニュース")
    assert response is not None
    print("メソッド: ", HTMLCleaning.none)
    print("レスポンス:", response)
