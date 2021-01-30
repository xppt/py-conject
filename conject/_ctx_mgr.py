from functools import wraps
from typing import Callable, AsyncContextManager, ContextManager


def async_context_manager(async_generator: Callable) -> Callable[..., AsyncContextManager]:
    @wraps(async_generator)
    def helper(*args, **kwargs):
        return _AsyncGeneratorContextManager(async_generator, args, kwargs)

    return helper


def context_manager(generator: Callable) -> Callable[..., ContextManager]:
    @wraps(generator)
    def helper(*args, **kwargs):
        return _GeneratorContextManager(generator, args, kwargs)

    return helper


def sync_to_async_ctx_mgr(ctx_mgr):
    @wraps(ctx_mgr)
    async def async_gen_func(*args, **kwargs):
        with ctx_mgr(*args, **kwargs) as value:
            yield value

    return async_context_manager(async_gen_func)


class _AsyncGeneratorContextManager:
    def __init__(self, func, args, kwargs):
        self._func = func
        self._args = args
        self._kwargs = kwargs

    async def __aenter__(self):
        self._it = self._func(*self._args, **self._kwargs)

        try:
            try:
                value = await self._it.__anext__()
            except StopAsyncIteration:
                raise RuntimeError('generator didn\'t yield') from None
        except BaseException:
            await self._it.aclose()
            raise

        return value

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        try:
            try:
                await self._it.__anext__()
            except StopAsyncIteration:
                return False
            else:
                raise RuntimeError('generator didn\'t stop')
        finally:
            await self._it.aclose()


class _GeneratorContextManager:
    def __init__(self, func, args, kwargs):
        self._func = func
        self._args = args
        self._kwargs = kwargs

    def __enter__(self):
        self._it = self._func(*self._args, **self._kwargs)

        try:
            try:
                value = self._it.__next__()
            except StopIteration:
                raise RuntimeError('generator didn\'t yield') from None
        except BaseException:
            self._it.close()
            raise

        return value

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            try:
                self._it.__next__()
            except StopIteration:
                return False
            else:
                raise RuntimeError('generator didn\'t stop')
        finally:
            self._it.close()
