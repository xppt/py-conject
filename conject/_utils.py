import inspect
import typing
from functools import wraps
from types import SimpleNamespace
from typing import Callable, Any, ContextManager, Mapping

from conject._ctx_mgr import async_context_manager, context_manager, sync_to_async_ctx_mgr
from conject._impl import Impl, FactoryType
from conject._types import FactoryParams, Parameter, missing, PreparedAsyncImpl, PreparedSyncImpl
from conject._validation import make_validator


def run_coro_synchronously(coro):
    try:
        coro.send(None)
    except StopIteration as e:
        return e.value

    raise RuntimeError('internal error - sync function yielded something')


def generate_name(factory: Any) -> str:
    if not inspect.isfunction(factory) and not inspect.isclass(factory):
        raise ValueError('Unable to automatically generate impl name', factory)

    return factory.__name__.strip('_')


def get_factory_params(impl: Impl) -> FactoryParams:
    # parameter kinds:
    #   POSITIONAL_ONLY
    #   POSITIONAL_OR_KEYWORD
    #   VAR_POSITIONAL
    #   KEYWORD_ONLY
    #   VAR_KEYWORD

    if impl.ftype == FactoryType.Value:
        return {}

    if not callable(impl.factory):
        raise ValueError(f'Factory should be callable: {impl.name}')

    allowed_kinds = (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)

    signature = inspect.signature(impl.factory)
    types = _get_type_hints(impl.factory, signature)

    def parse_param(parameter: inspect.Parameter) -> Parameter:
        name = parameter.name

        if parameter.kind not in allowed_kinds:
            raise ValueError(f'Unsupported parameter kind {impl.name}.{name}')

        default = missing
        if impl.params is not None and name in impl.params:
            default = impl.params[name]
        elif parameter.default is not inspect.Parameter.empty:
            default = parameter.default

        validator = make_validator(types.get(name, Any), f'{impl.name}__{name}')

        return Parameter(
            parameter.name,
            default=default,
            validator=validator,
        )

    factory_params: FactoryParams = {
        name: parse_param(parameter)
        for name, parameter in signature.parameters.items()
    }

    return factory_params


def _get_type_hints(factory: Any, signature: inspect.Signature) -> Mapping[str, Any]:
    # Yeah, this is a bit hacky. It is necessary to support
    # funcs/classes/NameTuples/dataclasses/partials/etc.

    annotated = SimpleNamespace(
        __annotations__={
            name: parameter.annotation
            for name, parameter in signature.parameters.items()
            if parameter.annotation is not inspect.Signature.empty
        },
    )

    return typing.get_type_hints(
        typing.cast(Any, annotated), globalns=getattr(factory, '__globals__', {}),
    )


def make_sync_ctx_mgr(ftype: FactoryType, factory: Any) -> Callable[..., ContextManager]:
    if ftype == FactoryType.CtxMgr:
        return factory

    factory_gen: Callable
    if ftype == FactoryType.Value:
        def factory_gen():
            yield factory

    elif ftype in (FactoryType.Class, FactoryType.Func):
        def factory_gen(*args, **kwargs):
            yield factory(*args, **kwargs)

    elif ftype == FactoryType.GenFunc:
        factory_gen = factory

    else:
        raise ValueError(f'Unsupported factory type: {ftype}')

    ctx_mgr = context_manager(factory_gen)
    return ctx_mgr


def make_async_ctx_mgr(ftype: FactoryType, factory: Any):
    if ftype == FactoryType.AGenFunc:
        ctx_mgr = async_context_manager(factory)

    elif ftype == FactoryType.AFunc:
        @wraps(factory)
        async def gen_func(*args, **kwargs):
            instance = await factory(*args, **kwargs)
            yield instance

        ctx_mgr = async_context_manager(gen_func)

    elif ftype == FactoryType.ACtxMgr:
        ctx_mgr = factory

    else:
        ctx_mgr = sync_to_async_ctx_mgr(make_sync_ctx_mgr(ftype, factory))

    return ctx_mgr


def prepare_sync_impl(impl: Impl) -> PreparedSyncImpl:
    return PreparedSyncImpl(
        name=impl.name,
        params=get_factory_params(impl),
        ctx_mgr=make_sync_ctx_mgr(impl.ftype, impl.factory),
    )


def prepare_async_impl(impl: Impl) -> PreparedAsyncImpl:
    return PreparedAsyncImpl(
        name=impl.name,
        params=get_factory_params(impl),
        ctx_mgr=make_async_ctx_mgr(impl.ftype, impl.factory),
    )


def probe_impl_factory(impl: Impl) -> None:
    """Use heuristics to prevent some user typos."""

    ftype = impl.ftype
    factory = impl.factory

    if inspect.iscoroutinefunction(factory) and ftype == FactoryType.Func:
        raise ValueError(
            f'Factory {impl.name!r} is an async function, but factory type set to {ftype}'
        )
