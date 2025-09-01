import asyncio
import io
import re
import threading
from enum import Enum
from logging import getLogger
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Union

import httpx
import pydantic
from google import genai
from google.genai import types
from google.genai.errors import ClientError, ServerError

from .tools import DDGSearch, Tool


class GeminiAgent:
    COMMON_SYSTEM_PROMPT: Optional[str] = None
    logger = getLogger("GeminiAgent")

    def __init__(
        self,
        model_name: str = "gemini-2.5-flash",
        tools: List[Tool] = [DDGSearch().tool],
        enable_grounding: bool = False,
        enable_url_context: bool = False,
        system_prompt: Optional[str] = COMMON_SYSTEM_PROMPT,
        default_thinking_budget: Optional[int] = None,
        api_key: Union[str, None] = None,
        retries: int = -1,
        retry_delay: int = -1,
        **kwargs,
    ) -> None:
        """Initialize the GeminiAgent object.

        Args:
            model_name (str, optional): Gemini model name (See: https://ai.google.dev/gemini-api/docs/models). Defaults to "gemini-2.5-flash".
            tools (List[Tool], optional): Tools (functions) that the model can call. Defaults to [DDGSearch().tool].
            enable_grounding (bool, optional): Whether enabling Google search grounding tool. Defaults to False.
                See: https://ai.google.dev/gemini-api/docs/google-search for more details.
            enable_url_context (bool, optional): Whether enabling URL context tool. Defaults to False.
                See: https://ai.google.dev/gemini-api/docs/url-context for more details.
            system_prompt (str, optional): System instructions for the model. Defaults to GeminiAgent.COMMON_SYSTEM_PROMPT.
            default_thinking_budget (int): The number of thinking tokens to use when generating a response. Defaults to None (Use Gemini default value).
                See: https://ai.google.dev/gemini-api/docs/thinking#set-budget for more details.
            api_key (Union[str, None], optional): Gemini API Key. Use "GOOGLE_API_KEY" or "GEMINI_API_KEY" environment variable will be used if None is specified. Defaults to None.
            retries (int, optional): Number of retries before giving up. Retry forever if -1 is specified. Defaults to -1.
            retry_delay (int, optional): Sleep seconds between retries. Follow delay seconds from Google's response if -1 is specified. Defaults to -1.
            **kwargs: Additional keyword arguments passed directly to the `google.genai.Client` constructor.
        """
        self.retries = retries
        self.retry_delay = retry_delay
        kwargs["api_key"] = api_key
        self.client = genai.Client(**kwargs)
        self.model_name = model_name
        self.tool_declarations = [tool.declaration for tool in tools]
        self.tool_functions = {tool.name: tool for tool in tools}

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
        # Conversation history
        self._config = types.GenerateContentConfig()
        if self.tools:
            self._config.tools = [self.tools]
        if system_prompt:
            self._config.system_instruction = system_prompt
        if default_thinking_budget:
            self._config.thinking_config = types.ThinkingConfig(thinking_budget=default_thinking_budget)
        self.chat = self.client.aio.chats.create(model=self.model_name, config=self._config)

    @property
    def system_prompt(self):
        """Get the current chat system prompt."""
        return self._config.system_instruction

    @system_prompt.setter
    def system_prompt(self, prompt: str):
        """Set a new system prompt and recreate chat."""
        self._config.system_instruction = prompt
        self.recreate_chat()

    def recreate_chat(self):
        """Recreate the chat object with the current configuration."""
        self.chat = self.client.aio.chats.create(model=self.model_name, config=self._config)

    # def invoke(
    #     self,
    #     message: str,
    #     files: List[Union[str, Path]] = [],
    #     thinking_budget: Optional[int] = None,
    #     response_schema: Optional[Union[pydantic.BaseModel, Dict, List, Enum, Any]] = None,
    #     output_format: Union[Literal["message"], Literal["raw"]] = "message",
    # ) -> Union[str, genai.types.GenerateContentResponse, Any, None]:
    #     """Call Gemini API and get response.

    #     Args:
    #         message (str): Input message
    #         files (list[str | pathlib.Path]): Filepath or URL of documents (such as PDF and HTML) and images (PNG, JPEG, WebP, HEIC or HEIF) to be attached to the message. Defaults to [] (No file attachment).
    #             See https://ai.google.dev/gemini-api/docs/document-processing and https://ai.google.dev/gemini-api/docs/image-understanding for more details.
    #         thinking_budget (int): The number of thinking tokens to use when generating a response. Defaults to None (Use default_thinking_budget).
    #             See: https://ai.google.dev/gemini-api/docs/thinking#set-budget for more details.
    #         response_schema (pydantic.BaseModel | dict | list | Enum | Any, optional): Schema definition for structured output. Pydantic object, JSON dict, Enum, etc. are supported. Defaults to None (No structured output).
    #             See: https://ai.google.dev/gemini-api/docs/structured-output for more details.
    #         output_format ("message" or "raw", optional): "message" for response message or "raw" for raw Gemini API response. Defaults to "message".

    #     Returns:
    #         response:
    #         String of Gemini response message if "message" is set to output, or GenerateContentResponse of raw Gemini API response if "raw" is set to output.
    #         If failed to get response from Gemini, returns "" (when "message" is set to output) or None (when "raw" is set to output).
    #     """
    #     result, exc = None, None

    #     def runner():
    #         nonlocal result, exc
    #         loop = asyncio.new_event_loop()
    #         asyncio.set_event_loop(loop)
    #         try:
    #             result = loop.run_until_complete(
    #                 self.ainvoke(message, files, thinking_budget, response_schema, output_format)
    #             )
    #         except Exception as e:
    #             exc = e
    #         finally:
    #             loop.close()

    #     t = threading.Thread(target=runner)
    #     t.start()
    #     t.join()
    #     if exc:
    #         raise exc
    #     return result

    async def _call_tool_function_async(self, function_call: types.FunctionCall) -> types.Part:
        """
        Call a tool function asynchronously and return the result.
        """
        function_name = function_call.name if function_call.name else ""
        function_args = dict(function_call.args) if function_call.args else {}

        if function_name not in self.tool_functions:
            self.logger.error(f"Tool {function_name} not found.")
            return types.Part.from_function_response(
                name=function_name,
                response={"error": f"Error: Tool '{function_name}' is not supported."},
            )

        tool_instance = self.tool_functions[function_name]
        try:
            # Tool.ainvoke を呼び出す
            result = await tool_instance.ainvoke(**function_args)
            return types.Part.from_function_response(name=function_name, response={"result": result})
        except Exception as e:
            self.logger.error(f"Error calling tool {function_name} asynchronously: {e.__class__.__name__} {e}")
            return types.Part.from_function_response(
                name=function_name,
                response={"error": f"Error calling tool '{function_name}' asynchronously: {e.__class__.__name__} {e}"},
            )

    async def ainvoke(
        self,
        message: str,
        files: List[Union[str, Path]] = [],
        thinking_budget: Optional[int] = None,
        response_schema: Optional[Union[pydantic.BaseModel, Dict, List, Enum, Any]] = None,
        output_format: Union[Literal["message"], Literal["raw"]] = "message",
    ) -> Union[str, genai.types.GenerateContentResponse, Any, None]:
        """Call Gemini API and get response.

        Args:
            message (str): Input message
            files (list[str | pathlib.Path]): Filepath or URL of documents (such as PDF and HTML) and images (PNG, JPEG, WebP, HEIC or HEIF) to be attached to the message. Defaults to [] (No file attachment).
                See https://ai.google.dev/gemini-api/docs/document-processing and https://ai.google.dev/gemini-api/docs/image-understanding for more details.
            thinking_budget (int): The number of thinking tokens to use when generating a response. Defaults to None (Use default_thinking_budget).
                See: https://ai.google.dev/gemini-api/docs/thinking#set-budget for more details.
            response_schema (pydantic.BaseModel | dict | list | Enum | Any, optional): Schema definition for structured output. Pydantic object, JSON dict, Enum, etc. are supported. Defaults to None (No structured output).
                See: https://ai.google.dev/gemini-api/docs/structured-output for more details.
            output_format ("message" or "raw", optional): "message" for response message or "raw" for raw Gemini API response. Defaults to "message".

        Returns:
            response:
            String of Gemini response message if "message" is set to output, or GenerateContentResponse of raw Gemini API response if "raw" is set to output.
            If failed to get response from Gemini, returns "" (when "message" is set to output) or None (when "raw" is set to output).
        """
        retries = 0
        config = self._config.model_copy()
        if thinking_budget is not None:
            config.thinking_config = types.ThinkingConfig(thinking_budget=thinking_budget)
        if response_schema:
            config.response_schema = response_schema

        # Upload files
        async def upload_file(file: Union[str, Path], client: httpx.AsyncClient):
            if isinstance(file, Path) or not (file.startswith("http://") or file.startswith("https://")):
                return await self.client.aio.files.upload(file=file)
            else:
                res = await client.get(file)
                res.raise_for_status()
                doc_io = io.BytesIO(res.content)
                mime_type = self._guess_filetype(res)
                doc_io.seek(0)
                return await self.client.aio.files.upload(file=doc_io, config=dict(mime_type=mime_type))

        async with httpx.AsyncClient() as client:
            attached_files = await asyncio.gather(*[upload_file(file, client) for file in files])

        # Call Gemini with retries
        while True:
            if self.retries > 0 and retries > self.retries:
                break
            try:
                # ユーザーメッセージを送信
                response = await self.chat.send_message(
                    message=attached_files + [message],
                    config=config,
                )

                # ツール呼び出しがリクエストされた場合
                while response.function_calls:
                    self.logger.info("Function call requested by the model.")
                    tool_responses = []
                    for function_call in response.function_calls:
                        tool_response = await self._call_tool_function_async(function_call)
                        tool_responses.append(tool_response)

                    # ツール実行結果をモデルに送り返す
                    response = await self.chat.send_message(tool_responses, config)

                # 最終的なレスポンスを返す
                if output_format == "message":
                    return response.text
                else:
                    return response

            except ClientError as e:
                if e.details["error"]["code"] == 429:
                    # RESOURCE_EXHAUSTED
                    if self.retry_delay > 0:
                        sleep_sec = self.retry_delay
                    else:
                        sleep_sec = [
                            float(rd.replace("s", ""))
                            for d in e.details["error"]["details"]
                            if (rd := d.get("retryDelay"))
                        ][0]
                    self.logger.info(f"Reached Gemini API Ratelimit. Retrying in {sleep_sec} seconds...")
                    await asyncio.sleep(sleep_sec)
                    self.logger.debug("Retrying...")
                else:
                    self.logger.error(
                        f"Failed to get response because of Gemini {e.details['error']['status']} error: {e.details['error']['message']}"
                    )
                    break
            except ServerError as e:
                self.logger.error(
                    f"Failed to get response because of Gemini {e.details['error']['status']} error: {e.details['error']['message']}\n"
                    "Retrying in 30 seconds..."
                )
                await asyncio.sleep(30)
                self.logger.debug("Retrying...")
            except Exception as e:
                self.logger.error(
                    f"An unexpected error occurred: {e.__class__.__name__} {e}", exc_info=True, stack_info=True
                )
                break
            finally:
                retries += 1

        self.logger.info(f"Failed to get response from Gemini after {retries - 1} retries.")
        return "" if output_format == "message" else None

    def _guess_filetype(self, response: httpx.Response):
        if response.headers.get("Content-Type", ""):
            return response.headers.get["Content-Type"]
        else:
            url = str(response.url).lower()
            if url.endswith(".pdf"):
                mime_type = "application/pdf"
            elif url.endswith(".xml"):
                mime_type = "application/xml"
            elif url.endswith((".html", ".htm")):
                mime_type = "text/html"
            elif url.endswith(".md"):
                mime_type = "text/markdown"
            elif url.endswith(".png"):
                mime_type = "image/png"
            elif url.endswith((".jpeg", ".jpg")):
                mime_type = "image/jpeg"
            elif url.endswith(".webp"):
                mime_type = "image/webp"
            elif url.endswith(".heic"):
                mime_type = "image/heic"
            elif url.endswith(".heif"):
                mime_type = "image/heif"
            else:
                mime_type = "text/plain"
            return mime_type


__all__ = ["GeminiAgent"]
