import asyncio
import re
import time
from logging import getLogger
from typing import Any, Dict, List, Union

from google.api_core.exceptions import ResourceExhausted
from langchain_core.tools import BaseTool
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.prebuilt import create_react_agent

from .ddg_search import DDGSearch


class GeminiAgent:
    COMMON_SYSTEM_PROMPT = ""
    logger = getLogger("GeminiAgent")

    def __init__(
        self,
        model_name: str = "gemini-2.5-flash",
        tools: List[BaseTool] = [DDGSearch().tool],
        system_prompt: str = COMMON_SYSTEM_PROMPT,
        google_api_key: Union[str, None] = None,
        retries: int = -1,
        retry_delay: int = -1,
        **kwargs,
    ) -> None:
        """Initialize the GeminiAgent object.

        Args:
            model_name (str, optional): Gemini model name (See: https://ai.google.dev/gemini-api/docs/models). Defaults to "gemini-2.5-flash".
            tools (List[BaseTool], optional): _description_. Defaults to [DDGSearch().tool].
            system_prompt (str, optional): . Defaults to GeminiAgent.COMMON_SYSTEM_PROMPT.
            google_api_key (Union[str, None], optional): Gemini API Key. Use "GOOGLE_API_KEY" environment variable will be used if None is specified. Defaults to None.
            retries (int, optional): Number of retries before giving up. Retry forever if -1 is specified. Defaults to -1.
            retry_delay (int, optional): Sleep seconds between retries. Follow delay seconds from Google's response if -1 is specified. Defaults to -1.
        """
        self.retries = retries
        self.retry_delay = retry_delay
        kwargs["model"] = model_name
        kwargs["max_retries"] = 0
        if google_api_key:
            kwargs["google_api_key"] = google_api_key
        model = ChatGoogleGenerativeAI(**kwargs)
        self.agent_executor = create_react_agent(model, tools)
        self.messages = [{"role": "system", "content": system_prompt}]

    def invoke(self, user_message: str, output="message") -> str | Dict[str, Any] | None:
        """Invoke Gemini ReAct agent and get response.

        Args:
            user_message (str): Input message as User (will be stored for later use)
            output (str, optional): "message" for response message or "raw" for raw Gemini API response. Defaults to "message".

        Returns:
            String of Gemini response message if "message" is set to output, or Dict of raw Gemini API response if "raw" is set to output.
            If failed to get response from Gemini, returns "" (when "message" is set to output) or None (when "raw" is set to output).
        """
        self.messages.append({"role": "user", "content": user_message})
        retries = 0
        while True:
            if self.retries > 0 and retries > self.retries:
                break
            try:
                response = self.agent_executor.invoke({"messages": self.messages})
                if not response or "messages" not in response:
                    # Retry
                    if self.retry_delay > 0:
                        sleep_sec = self.retry_delay
                    else:
                        sleep_sec = self._extract_retry_delay(e)
                    self.logger.info(f"Gemini did not return any response. Retrying in {sleep_sec} seconds...")
                    time.sleep(sleep_sec)
                    self.logger.debug("Retrying...")
                    continue
                message = response["messages"][-1].content
                self.messages.append({"role": "ai", "message": message})
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

    async def ainvoke(self, user_message: str, output="message") -> str | Dict[str, Any] | None:
        """Invoke Gemini ReAct agent and get response asyncronously.

        Args:
            user_message (str): Input message as User (will be stored for later use)
            output (str, optional): "message" for response message or "raw" for raw Gemini API response. Defaults to "message".

        Returns:
            String of Gemini response message if "message" is set to output, or Dict of raw Gemini API response if "raw" is set to output.
            If failed to get response from Gemini, returns "" (when "message" is set to output) or None (when "raw" is set to output).
        """
        self.messages.append({"role": "user", "content": user_message})
        retries = 0
        while True:
            if self.retries > 0 and retries > self.retries:
                break
            try:
                response = await self.agent_executor.ainvoke({"messages": self.messages})
                if not response or "messages" not in response:
                    # Retry
                    if self.retry_delay > 0:
                        sleep_sec = self.retry_delay
                    else:
                        sleep_sec = self._extract_retry_delay(e)
                    self.logger.info(f"Gemini did not return any response. Retrying in {sleep_sec} seconds...")
                    await asyncio.sleep(sleep_sec)
                    self.logger.debug("Retrying...")
                    continue
                message = response["messages"][-1].content
                self.messages.append({"role": "ai", "message": message})
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
            self.logger.debug(
                "_extract_retry_delay: Could not extract retry delay from error message. Defaulting to 5 seconds."
            )
            return 5
