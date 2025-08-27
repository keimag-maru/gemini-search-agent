import asyncio
import io
import re
import time
from logging import getLogger
from typing import Any, Dict, List, Literal, Union

import httpx
from google import genai
from google.genai.errors import 
from google.api_core.exceptions import ResourceExhausted
from google.genai import types
from langchain_core.tools import BaseTool
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.prebuilt import create_react_agent
from pathlib import Path

from .tools.ddg_search import DDGSearch


class GeminiAgent:
    COMMON_SYSTEM_PROMPT = ""
    logger = getLogger("GeminiAgent")

    def __init__(
        self,
        model_name: str = "gemini-2.5-flash",
        tools: List[genai.types.FunctionDeclaration] = [DDGSearch().tool],
        enable_grounding: bool = False,
        enable_url_context: bool = False,
        system_prompt: str = COMMON_SYSTEM_PROMPT,
        api_key: Union[str, None] = None,
        retries: int = -1,
        retry_delay: int = -1,
        **kwargs,
    ) -> None:
        """Initialize the GeminiAgent object.

        Args:
            model_name (str, optional): Gemini model name (See: https://ai.google.dev/gemini-api/docs/models). Defaults to "gemini-2.5-flash".
            tools (List[BaseTool], optional): Functions used by Gemini. Defaults to [DDGSearch().tool].
            system_prompt (str, optional): . Defaults to GeminiAgent.COMMON_SYSTEM_PROMPT.
            google_api_key (Union[str, None], optional): Gemini API Key. Use "GOOGLE_API_KEY" environment variable will be used if None is specified. Defaults to None.
            retries (int, optional): Number of retries before giving up. Retry forever if -1 is specified. Defaults to -1.
            retry_delay (int, optional): Sleep seconds between retries. Follow delay seconds from Google's response if -1 is specified. Defaults to -1.
            **kwargs: Additional keyword arguments passed directly to the `langchain_google_genai.ChatGoogleGenerativeAI` constructor.
        """
        self.client = genai.Client(api_key=api_key)
        if tools or enable_grounding or enable_url_context:
            self.tools = genai.types.Tool(function_declarations=tools)
            if enable_grounding:
                if re.match("gemini-(exp|1.5).*", model_name):
                    self.tools.google_search_retrieval = genai.types.GoogleSearchRetrieval()
                else:
                    self.tools.google_search = genai.types.GoogleSearch()
            if enable_url_context:
                self.tools.url_context = genai.types.UrlContext()
        else:
            self.tools = None
        # -----
        self.retries = retries
        self.retry_delay = retry_delay
        if system_prompt:
            self.messages = [{"role": "system", "content": system_prompt}]
        else:
            self.messages = []

    @property
    def system_prompt(self):
        if self.messages:
            for message in reversed(self.messages):
                if message.get("role", "") == "system":
                    return message["content"]
        return ""

    @system_prompt.setter
    def system_prompt(self, prompt_message: str):
        if self.messages:
            if self.messages[0].get("role", "") == "system":
                self.messages[0]["content"] = prompt_message
            else:
                self.messages.insert(0, {"role": "system", "content": prompt_message})
        else:
            self.messages = [{"role": "system", "content": prompt_message}]

    def invoke(
        self,
        message: str,
        file: Union[str, Path, None] = None,
        role: str = "user",
        output: Union[Literal["message"], Literal["raw"]] = "message",
        add_to_history: bool = True,
    ) -> Union[str, Dict[str, Any], None]:
        """Invoke Gemini ReAct agent and get response.

        Args:
            message (str): Input message
            role (str): Role of message
            output ("message" or "raw") (Literal, optional): "message" for response message or "raw" for raw Gemini API response. Defaults to "message".
            add_to_history (bool): Whether to append the response to `self.messages` to preserve context. Defaults to True.

        Returns:
            String of Gemini response message if "message" is set to output, or Dict of raw Gemini API response if "raw" is set to output.
            If failed to get response from Gemini, returns "" (when "message" is set to output) or None (when "raw" is set to output).
        """
        if add_to_history:
            messages = self.messages
        else:
            messages = self.messages.copy()
        messages.append(
            {"role": role, "content": message}
        )  # if add_to_history is True, this means self.messages.append, otherwise just appending local variable
        retries = 0
        while True:
            if self.retries > 0 and retries > self.retries:
                break
            try:
                response = self.agent_executor.invoke({"messages": messages})
                if not response or "messages" not in response:
                    # Retry
                    if self.retry_delay > 0:
                        sleep_sec = self.retry_delay
                    else:
                        sleep_sec = 2
                    self.logger.info(f"Gemini did not return any response. Retrying in {sleep_sec} seconds...")
                    time.sleep(sleep_sec)
                    self.logger.debug("Retrying...")
                    continue
                message = response["messages"][-1].content
                messages.append(
                    {"role": "ai", "content": message}
                )  # if add_to_history is True, this means self.messages.append, otherwise just appending local variable
                if output == "message":
                    return message
                else:
                    return response
            except ResourceExhausted as e:
                if self.retry_delay > 0:
                    sleep_sec = self.retry_delay
                else:
                    sleep_sec = self._extract_retry_delay(e)
                self.logger.info(f"Reached Gemini API Ratelimit. Retrying in {sleep_sec} seconds...")
                time.sleep(sleep_sec)
                self.logger.debug("Retrying...")
            finally:
                retries += 1
        # Failed after self.retries retries
        self.logger.info(f"Failed to get response from Gemini after {retries - 1} retries.")
        if output == "message":
            return ""
        else:
            return None

    async def ainvoke(
        self,
        message: str,
        role: str = "user",
        output: Union[Literal["message"], Literal["raw"]] = "message",
        add_to_history: bool = True,
    ) -> Union[str, Dict[str, Any], None]:
        """Invoke Gemini ReAct agent and get response asynchronously.

        Args:
            user_message (str): Input message
            role (str): Role of message
            output ("message" or "raw") (Literal, optional): "message" for response message or "raw" for raw Gemini API response. Defaults to "message".
            add_to_history (bool): Whether to append the response to `self.messages` to preserve context. Defaults to True.

        Returns:
            String of Gemini response message if "message" is set to output, or Dict of raw Gemini API response if "raw" is set to output.
            If failed to get response from Gemini, returns "" (when "message" is set to output) or None (when "raw" is set to output).
        """
        if add_to_history:
            messages = self.messages
        else:
            messages = self.messages.copy()
        messages.append(
            {"role": role, "content": message}
        )  # if add_to_history is True, this means self.messages.append, otherwise just appending local variable
        retries = 0
        while True:
            if self.retries > 0 and retries > self.retries:
                break
            try:
                response = await self.agent_executor.ainvoke({"messages": messages})
                if not response or "messages" not in response:
                    # Retry
                    if self.retry_delay > 0:
                        sleep_sec = self.retry_delay
                    else:
                        sleep_sec = 2
                    self.logger.info(f"Gemini did not return any response. Retrying in {sleep_sec} seconds...")
                    await asyncio.sleep(sleep_sec)
                    self.logger.debug("Retrying...")
                    continue
                message = response["messages"][-1].content
                messages.append(
                    {"role": "ai", "content": message}
                )  # if add_to_history is True, this means self.messages.append, otherwise just appending local variable
                if output == "message":
                    return message
                else:
                    return response
            except ResourceExhausted as e:
                if self.retry_delay > 0:
                    sleep_sec = self.retry_delay
                else:
                    sleep_sec = self._extract_retry_delay(e)
                self.logger.info(f"Reached Gemini API Ratelimit. Retrying in {sleep_sec} seconds...")
                await asyncio.sleep(sleep_sec)
                self.logger.debug("Retrying...")
            finally:
                retries += 1
        # Failed after self.retries retries
        self.logger.info(f"Failed to get response from Gemini after {retries - 1} retries.")
        if output == "message":
            return ""
        else:
            return None

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
