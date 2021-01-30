from contextlib import contextmanager, ExitStack
from typing import (
    Dict, Any, Optional, TypeVar, AsyncContextManager, ContextManager, Generic, Tuple, Callable,
    Sequence, List,
)

from async_exit_stack import AsyncExitStack
from async_generator import asynccontextmanager

from conject._impl import Impl, FactoryType
from conject._utils import prepare_async_impl, prepare_sync_impl, generate_name, probe_impl_factory
from conject._container import Container, AsyncContainer
from conject._container_config import load_container_config, ContainerConfig, check_container_config
from conject._types import PreparedSyncImpl, PreparedAsyncImpl

TPreparedImpl = TypeVar('TPreparedImpl', PreparedSyncImpl, PreparedAsyncImpl)
TContainer = TypeVar('TContainer', Container, AsyncContainer)
TExitStack = TypeVar('TExitStack', ExitStack, AsyncExitStack)
TFactory = TypeVar('TFactory')  # Factory or AsyncFactory

_StartContainerParams = Tuple[Dict[str, TPreparedImpl], ContainerConfig]


class _BaseDepSpec(Generic[TPreparedImpl, TContainer, TExitStack]):
    def __init__(self, impls: Sequence[Impl] = ()):
        self._impls: Dict[str, Impl] = {}
        self._prepared_impls: Dict[str, TPreparedImpl] = {}
        self.add_many(impls)

    def add(
            self, ftype: FactoryType, name: str, factory: Any,
            params: Optional[Dict[str, Any]] = None,
    ) -> None:

        self.add_many((
            Impl(ftype, name, factory, params),
        ))

    def add_many(self, impls: Sequence[Impl]) -> None:
        prepared_impls: Dict[str, TPreparedImpl] = {}

        for impl in impls:
            try:
                name = impl.name
                if name in prepared_impls or name in self._impls:
                    raise ValueError(f'Multiple implementations named {name}')

                probe_impl_factory(impl)
                prepared_impls[name] = self._prepare_impl(impl)
            except Exception as e:
                raise ValueError(f'Error adding {impl.name!r}') from e

        self._prepared_impls.update(prepared_impls)
        self._impls.update({
            impl.name: impl for impl in impls
        })

    def decorate(
            self, ftype: FactoryType, name: Optional[str] = None,
    ) -> Callable[[TFactory], TFactory]:

        def register(factory: TFactory) -> TFactory:
            impl_name = generate_name(factory) if name is None else name
            self.add(ftype, impl_name, factory)
            return factory

        return register

    def get_list(self) -> List[Impl]:
        return list(self._impls.values())

    Value = FactoryType.Value
    Class = FactoryType.Class
    Func = FactoryType.Func
    GenFunc = FactoryType.GenFunc
    CtxMgr = FactoryType.CtxMgr
    AFunc = FactoryType.AFunc
    AGenFunc = FactoryType.AGenFunc
    ACtxMgr = FactoryType.ACtxMgr

    def _prepare_impl(self, impl: Impl) -> TPreparedImpl:
        raise NotImplementedError

    def _before_start(self, config: Any) -> _StartContainerParams[TPreparedImpl]:
        container_config = load_container_config(config)
        check_container_config(container_config, self._prepared_impls)
        # noinspection PyTypeChecker
        return self._prepared_impls.copy(), container_config


class DepSpec(_BaseDepSpec[PreparedSyncImpl, Container, ExitStack]):
    def start_container(self, config: Any) -> ContextManager[Container]:
        return self._start_container(config)

    @contextmanager
    def _start_container(self, config: Any):
        # noinspection PyTupleAssignmentBalance
        impls, container_config = self._before_start(config)

        with ExitStack() as exit_stack:
            yield Container(
                impls=impls,
                config=container_config,
                exit_stack=exit_stack,
            )

    def _prepare_impl(self, impl: Impl) -> PreparedSyncImpl:
        return prepare_sync_impl(impl)


class AsyncDepSpec(_BaseDepSpec[PreparedAsyncImpl, AsyncContainer, AsyncExitStack]):
    def start_container(self, config: Any) -> AsyncContextManager[AsyncContainer]:
        return self._start_container(config)

    @asynccontextmanager
    async def _start_container(self, config: Any):
        # noinspection PyTupleAssignmentBalance
        impls, container_config = self._before_start(config)

        async with AsyncExitStack() as exit_stack:
            yield AsyncContainer(
                impls=impls,
                config=container_config,
                exit_stack=exit_stack,
            )

    def _prepare_impl(self, impl: Impl) -> PreparedAsyncImpl:
        return prepare_async_impl(impl)
