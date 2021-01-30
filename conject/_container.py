from contextlib import ExitStack
from typing import Generic, TypeVar, Dict, Any, Callable, Sequence, Mapping, List, Type

from async_exit_stack import AsyncExitStack

from conject._impl import Impl, FactoryType
from conject._utils import run_coro_synchronously, get_factory_params
from conject._container_config import ContainerConfig, InstanceConfig, DeferredValue
from conject._types import PreparedSyncImpl, PreparedAsyncImpl, Parameter
from conject._validation import ValidationError, make_validator
from conject.utils import SkipTypeCheck

TPreparedImpl = TypeVar('TPreparedImpl', PreparedSyncImpl, PreparedAsyncImpl)
TExitStack = TypeVar('TExitStack', ExitStack, AsyncExitStack)
TGetType = TypeVar('TGetType')


class BaseContainer(Generic[TPreparedImpl, TExitStack]):
    def __init__(
            self, impls: Dict[str, TPreparedImpl], config: ContainerConfig, exit_stack: TExitStack,
    ):
        self._impls: Dict[str, TPreparedImpl] = impls
        self._config = config
        self._exit_stack: TExitStack = exit_stack
        self._instances: Dict[str, Any] = {'container': self}  # TODO: refactorme

    def inject(self, instances: Dict[str, Any]) -> None:
        for name in instances.keys():
            if name in self._instances:
                raise ValueError('instance already exists', name)

        self._instances.update(instances)

    def ensure_constructible(self, name: str) -> None:
        run_coro_synchronously(self._async_get(name, [], dry_run=True))

    _missing = object()
    _initializing = object()

    async def _get_factory_param_vals(self, factory: Callable) -> Mapping[str, Any]:
        params = get_factory_params(Impl(FactoryType.Func, 'factory', factory))

        param_vals = {}
        for param in params.values():
            param_vals[param.name] = await self._get_param_val([], param)

        return param_vals

    async def _get_param_val(
            self, build_stack: List[str],
            param: Parameter,
            configured_value: Any = _missing,
            dry_run: bool = False,
    ) -> Any:

        if configured_value is self._missing and param.has_default():
            configured_value = param.default

        if configured_value is self._missing:
            # Parameter is not configured nor have a default.
            # So lets fetch an instance with the same name.
            param_val = await self._async_get_raw(param.name, build_stack, dry_run)

        elif isinstance(configured_value, DeferredValue):
            resolved_deps = {
                dep_name: await self._async_get(dep_name, build_stack, dry_run=dry_run)
                for dep_name in configured_value.deps
            }
            param_val = None
            if not dry_run:
                # TODO: handle errors
                param_val = configured_value.eval(resolved_deps)

        else:
            param_val = configured_value

        if isinstance(param_val, SkipTypeCheck):
            param_val = param_val.value
        elif not dry_run:
            param_val = param.validator(param_val)

        return param_val

    async def _async_get(
            self, inst_name: str, stack: list,
            *, dry_run: bool = False, check_type: Any = None,
    ) -> Any:

        instance = await self._async_get_raw(inst_name, stack, dry_run)
        if isinstance(instance, SkipTypeCheck):
            instance = instance.value
        elif check_type is not None:
            validator = make_validator(check_type, f'inst__{inst_name}')
            try:
                instance = validator(instance)
            except ValidationError as e:
                raise InvalidInstanceType(inst_name, e.expected_type, e.value) from e

        return instance

    async def _async_get_raw(self, inst_name: str, stack: list, dry_run: bool = False) -> Any:
        stack = stack + [inst_name]

        instance = self._instances.get(inst_name, self._missing)
        if instance is self._initializing:
            raise DependencyCycle(stack)
        if instance is not self._missing:
            return instance

        self._instances[inst_name] = self._initializing

        try:
            inst_config = self._config.instances.get(inst_name, InstanceConfig(inst_name, {}))

            impl = self._impls.get(inst_config.impl_name)
            if impl is None:
                raise MissingValue(stack)

            param_vals = {}
            for param in impl.params.values():
                configured_value = inst_config.parameters.get(param.name, self._missing)

                try:
                    param_vals[param.name] = await self._get_param_val(
                        stack, param, configured_value, dry_run)
                except ValidationError as e:
                    raise InvalidImplParam(inst_name, param.name, e.expected_type, e.value) from e

            instance = None
            if not dry_run:
                instance = await self._run_impl(impl, param_vals)
                self._instances[inst_name] = instance
            else:
                del self._instances[inst_name]
        except BaseException:
            del self._instances[inst_name]
            raise

        return instance

    async def _run_impl(self, impl: TPreparedImpl, params: Dict[str, Any]):
        raise NotImplementedError


class Container(BaseContainer[PreparedSyncImpl, ExitStack]):
    def get(self, name: str, check_type: Type[TGetType] = None) -> TGetType:
        """
        :raises InstanceError
        """

        coro = self._async_get(name, [], check_type=check_type)
        return run_coro_synchronously(coro)

    def get_params(self, factory: Callable) -> Mapping[str, Any]:
        """
        :raises InstanceError
        """

        coro = self._get_factory_param_vals(factory)
        return run_coro_synchronously(coro)

    async def _run_impl(self, impl: PreparedSyncImpl, params: Dict[str, Any]):
        instance = self._exit_stack.enter_context(impl.ctx_mgr(**params))
        return instance


class AsyncContainer(BaseContainer[PreparedAsyncImpl, AsyncExitStack]):
    async def get(self, name: str, check_type: Type[TGetType] = None) -> TGetType:
        """
        :raises InstanceError
        """

        return await self._async_get(name, [], check_type=check_type)

    async def get_params(self, factory: Callable) -> Mapping[str, Any]:
        """
        :raises InstanceError
        """

        return await self._get_factory_param_vals(factory)

    async def _run_impl(self, impl: PreparedAsyncImpl, params: Dict[str, Any]):
        instance = await self._exit_stack.enter_async_context(impl.ctx_mgr(**params))
        return instance


class InstanceError(Exception):
    pass


class MissingValue(InstanceError):
    def __init__(self, instance_stack: Sequence[str]):
        assert len(instance_stack)
        self._instance_stack = instance_stack

    def __str__(self) -> str:
        if len(self._instance_stack) == 1:
            instance, = self._instance_stack
            return f'Neither instance nor impl exists {instance!r}'
        else:
            *rest, instance, param = self._instance_stack
            build_chain = ' -> '.join(repr(item) for item in rest)
            return (
                f'Parameter {param!r} of instance {instance!r} is not configured '
                f'(while building {build_chain} -> {instance!r})'
            )


class DependencyCycle(InstanceError):
    def __init__(self, instances: Sequence[str]):
        assert(len(instances))
        self._instances = instances

    def __str__(self) -> str:
        build_chain = ' -> '.join(repr(item) for item in self._instances)
        return f'Instance {self._instances[0]!r} is depending on itself: {build_chain}'


class InvalidImplParam(InstanceError):
    def __init__(self, inst_name: str, param_name: str, expected_type: Type, value: Any):
        self.inst_name = inst_name
        self.param_name = param_name
        self.expected_type = expected_type
        self.value = value

    def __str__(self) -> str:
        return (
            f'Invalid param value for {self.inst_name}.{self.param_name}.'
            f' Expected of type {self.expected_type}, got {self.value!r}'
        )


class InvalidInstanceType(InstanceError):
    def __init__(self, inst_name: str, expected_type: Type, value: Any):
        self.inst_name = inst_name
        self.expected_type = expected_type
        self.value = value

    def __str__(self) -> str:
        return (
            f'Invalid {self.inst_name!r} type.'
            f' Expected of type {self.expected_type}, got {self.value!r}'
        )
