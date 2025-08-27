import asyncio
import re
import time
from logging import getLogger
from typing import Any, Dict, List, Literal, Union

from google import genai
from google.genai import types
from google.genai.errors import APIError

from gemini_search_agent.tools.tool import Tool
from gemini_search_agent.tools.ddg_search import DDGSearch


class GeminiAgent:
    COMMON_SYSTEM_PROMPT = ""
    logger = getLogger("GeminiAgent")

    def __init__(
        self,
        model_name: str = "gemini-2.5-flash",
        tools: List[Tool] = [DDGSearch().tool],
        enable_grounding: bool = False,
        enable_url_context: bool = False,
        system_prompt: str = COMMON_SYSTEM_PROMPT,
        google_api_key: Union[str, None] = None,
        retries: int = -1,
        retry_delay: int = -1,
        **kwargs,
    ) -> None:
        """Initialize the GeminiAgent object.

        Args:
            model_name (str, optional): Gemini model name (See: https://ai.google.dev/gemini-api/docs/models). Defaults to "gemini-2.5-flash".
            tools (List[Tool], optional): Tools (functions) that the model can call. Defaults to [DDGSearch().tool].
            system_prompt (str, optional): System instructions for the model. Defaults to GeminiAgent.COMMON_SYSTEM_PROMPT.
            google_api_key (Union[str, None], optional): Gemini API Key. Use "GEMINI_API_KEY" environment variable will be used if None is specified. Defaults to None.
            retries (int, optional): Number of retries before giving up. Retry forever if -1 is specified. Defaults to -1.
            retry_delay (int, optional): Sleep seconds between retries. Follow delay seconds from Google's response if -1 is specified. Defaults to -1.
            **kwargs: Additional keyword arguments passed directly to the `genai.Client` constructor.
        """
        self.retries = retries
        self.retry_delay = retry_delay
        kwargs
        self.client = genai.Client(api_key=google_api_key)
        self.model_name = model_name

        # Tool インスタンスを直接格納
        self.tools = tools
        self.tool_declarations = [tool.declaration for tool in self.tools]
        self.tool_functions = {tool.declaration.name: tool for tool in self.tools}

        if tools or enable_grounding or enable_url_context:
            self.tools = genai.types.Tool(function_declarations=[tool.declaration for tool in tools])
            if enable_grounding:
                if re.match("gemini-(exp|1.5).*", model_name):
                    self.tools.google_search_retrieval = genai.types.GoogleSearchRetrieval()
                else:
                    self.tools.google_search = genai.types.GoogleSearch()
            if enable_url_context:
                self.tools.url_context = genai.types.UrlContext()
        else:
            self.tools = None

        # チャットインスタンスを作成し、会話履歴を管理
        self.chat = self.client.chats.create(model=self.model_name)
        if system_prompt:
            self.system_prompt = system_prompt

    @property
    def system_prompt(self):
        """Get the current system prompt."""
        return (
            self.chat.get_history()[0].parts[0].text
            if self.chat.get_history() and self.chat.get_history()[0].role == "system"
            else ""
        )

    @system_prompt.setter
    def system_prompt(self, prompt_message: str):
        """Set the system prompt."""
        self.chat.system_instruction = prompt_message

    def _call_tool_function(self, function_call: types.FunctionCall) -> types.Part:
        """
        Call a tool function based on the model's request and return the result.
        """
        function_name = function_call.name
        function_args = dict(function_call.args)

        if function_name not in self.tool_functions:
            self.logger.error(f"Tool {function_name} not found.")
            return types.Part.from_tool_response(
                tool_name=function_name,
                response=f"Error: Tool '{function_name}' is not supported.",
            )

        tool_instance = self.tool_functions[function_name]
        try:
            # Tool.invoke を呼び出す
            result = tool_instance.invoke(**function_args)
            return types.Part.from_tool_response(tool_name=function_name, response=result)
        except Exception as e:
            self.logger.error(f"Error calling tool {function_name}: {e}")
            return types.Part.from_tool_response(
                tool_name=function_name,
                response=f"Error calling tool '{function_name}': {e}",
            )

    def invoke(
        self,
        message: str,
        role: str = "user",
        output: Union[Literal["message"], Literal["raw"]] = "message",
        add_to_history: bool = True,
    ) -> Union[str, Dict[str, Any], None]:
        """Invoke Gemini Function Calling agent and get response."""
        retries = 0
        current_chat = (
            self.chat
            if add_to_history
            else self.client.chats.create(model=self.model_name, system_instruction=self.system_prompt)
        )

        while True:
            if self.retries > 0 and retries > self.retries:
                break
            try:
                # ユーザーメッセージを送信
                response = current_chat.send_message(
                    message,
                    config=types.GenerateContentConfig(tools=self.tool_declarations),
                    stream=False,
                )

                # ツール呼び出しがリクエストされた場合
                if response.function_calls:
                    self.logger.info("Function call requested by the model.")
                    tool_responses = []
                    for function_call in response.function_calls:
                        tool_response = self._call_tool_function(function_call)
                        tool_responses.append(tool_response)

                    # ツール実行結果をモデルに送り返す
                    response = current_chat.send_message(tool_responses)

                # 最終的なレスポンスを返す
                if output == "message":
                    return response.text
                else:
                    return response

            except APIError as e:
                if "ResourceExhausted" in str(e):
                    if self.retry_delay > 0:
                        sleep_sec = self.retry_delay
                    else:
                        sleep_sec = self._extract_retry_delay(e)
                    self.logger.info(f"Reached Gemini API Ratelimit. Retrying in {sleep_sec} seconds...")
                    time.sleep(sleep_sec)
                    self.logger.debug("Retrying...")
                else:
                    self.logger.error(f"Failed to get response from Gemini: {e}")
                    break
            except Exception as e:
                self.logger.error(f"An unexpected error occurred: {e}")
                break
            finally:
                retries += 1

        self.logger.info(f"Failed to get response from Gemini after {retries - 1} retries.")
        return "" if output == "message" else None

    async def _call_tool_function_async(self, function_call: types.FunctionCall) -> types.Part:
        """
        Call a tool function asynchronously and return the result.
        """
        function_name = function_call.name
        function_args = dict(function_call.args)

        if function_name not in self.tool_functions:
            self.logger.error(f"Tool {function_name} not found.")
            return types.Part.from_tool_response(
                tool_name=function_name,
                response=f"Error: Tool '{function_name}' is not supported.",
            )

        tool_instance = self.tool_functions[function_name]
        try:
            # Tool.ainvoke を呼び出す
            result = await tool_instance.ainvoke(**function_args)
            return types.Part.from_tool_response(tool_name=function_name, response=result)
        except Exception as e:
            self.logger.error(f"Error calling tool {function_name} asynchronously: {e}")
            return types.Part.from_tool_response(
                tool_name=function_name,
                response=f"Error calling tool '{function_name}' asynchronously: {e}",
            )

    async def ainvoke(
        self,
        message: str,
        role: str = "user",
        output: Union[Literal["message"], Literal["raw"]] = "message",
        add_to_history: bool = True,
    ) -> Union[str, Dict[str, Any], None]:
        """Invoke Gemini Function Calling agent and get response asynchronously."""
        retries = 0
        current_chat = (
            self.chat
            if add_to_history
            else self.client.chats.create(model=self.model_name, system_instruction=self.system_prompt)
        )

        while True:
            if self.retries > 0 and retries > self.retries:
                break
            try:
                # ユーザーメッセージを非同期で送信
                response = await current_chat.send_message_async(
                    message,
                    config=types.GenerateContentConfig(tools=self.tool_declarations),
                    stream=False,
                )

                # ツール呼び出しがリクエストされた場合
                if response.function_calls:
                    self.logger.info("Function call requested by the model.")
                    tool_responses = await asyncio.gather(
                        *[self._call_tool_function_async(fc) for fc in response.function_calls]
                    )

                    # ツール実行結果を非同期でモデルに送り返す
                    response = await current_chat.send_message_async(tool_responses)

                # 最終的なレスポンスを返す
                if output == "message":
                    return response.text
                else:
                    return response

            except APIError as e:
                if "ResourceExhausted" in str(e):
                    if self.retry_delay > 0:
                        sleep_sec = self.retry_delay
                    else:
                        sleep_sec = self._extract_retry_delay(e)
                    self.logger.info(f"Reached Gemini API Ratelimit. Retrying in {sleep_sec} seconds...")
                    await asyncio.sleep(sleep_sec)
                    self.logger.debug("Retrying...")
                else:
                    self.logger.error(f"Failed to get response from Gemini: {e}")
                    break
            except Exception as e:
                self.logger.error(f"An unexpected error occurred: {e}")
                break
            finally:
                retries += 1

        self.logger.info(f"Failed to get response from Gemini after {retries - 1} retries.")
        return "" if output == "message" else None

    def _extract_retry_delay(self, error_message):
        retry_delay = re.search(r"retry_delay\s*{\s*seconds:\s*(\d+)", str(error_message))
        if retry_delay:
            return int(retry_delay.group(1))
        else:
            self.logger.info(
                "_extract_retry_delay: Could not extract retry delay from error message. Defaulting to 2 seconds."
            )
            return 2


__all__ = ["GeminiAgent"]
