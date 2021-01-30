from typing import Callable, NamedTuple, Mapping, Any, ContextManager, AsyncContextManager

missing = object()


class Parameter(NamedTuple):
    name: str
    default: Any  # or `missing`
    validator: Callable[[Any], Any]

    def has_default(self) -> bool:
        return self.default is not missing


FactoryParams = Mapping[str, Parameter]


class PreparedSyncImpl(NamedTuple):
    name: str
    params: FactoryParams
    ctx_mgr: Callable[..., ContextManager]


class PreparedAsyncImpl(NamedTuple):
    name: str
    params: FactoryParams
    ctx_mgr: Callable[..., AsyncContextManager]
