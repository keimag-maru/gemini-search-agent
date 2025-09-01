from typing import Callable, Coroutine


class Tool:
    def __init__(self, func: Callable, coroutine: Coroutine, declaration: dict):
        self.func = func
        self.coroutine = coroutine
        self.declaration = declaration

    def invoke(self, **kwargs):
        return self.func(**kwargs)

    async def ainvoke(self, **kwargs):
        return await self.coroutine(**kwargs)

    @property
    def name(self) -> str:
        return self.declaration.get("name", self.func.__name__)

    def __str__(self) -> str:
        return f'<Tool "{self.name}" invoke->{self.func.__name__} ainvoke->{self.coroutine.__name__}'

    def __repr__(self) -> str:
        return f"{self.name} Tool"
