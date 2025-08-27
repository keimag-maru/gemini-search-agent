from typing import Callable, Coroutine

import google.genai.types


class Tool:
    def __init__(self, func: Callable, coroutine: Coroutine, declaration: google.genai.types.FunctionDeclaration):
        self.func = func
        self.coroutine = coroutine
        self.declaration = declaration

    def invoke(self, **kwargs):
        return self.func(**kwargs)

    async def ainvoke(self, **kwargs):
        return await self.coroutine(**kwargs)

    @property
    def name(self) -> str | None:
        return self.declaration.name
