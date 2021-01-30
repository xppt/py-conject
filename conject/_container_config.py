from types import SimpleNamespace
from typing import NamedTuple, Any, Dict, Union, Set, cast

from conject._expressions import expr_dependencies
from conject._types import PreparedSyncImpl, PreparedAsyncImpl

_impl_keyword = '-impl'
_ref_keyword = '-ref'
_expr_keyword = '-expr'
ref_holder_name = 'refs'


class InstanceConfig(NamedTuple):
    impl_name: str
    parameters: Dict[str, Any]


class ContainerConfig(NamedTuple):
    instances: Dict[str, InstanceConfig]


class DeferredValue:
    @property
    def deps(self) -> Set[str]:
        raise NotImplementedError

    def eval(self, deps: Dict[str, Any]) -> Any:
        raise NotImplementedError


class ExpressionValue(DeferredValue):
    def __init__(self, code: str):
        self._code = code
        self._deps = expr_dependencies(self._code, ref_holder_name)

    @property
    def deps(self) -> Set[str]:
        return self._deps

    def eval(self, deps: Dict[str, Any]) -> Any:
        expr_globals = {
            ref_holder_name: SimpleNamespace(**deps),
        }
        # TODO: handle errors
        return eval(self._code, expr_globals, expr_globals)


class DictValue(DeferredValue):
    def __init__(self, conf_dict: dict):
        self._conf_dict = conf_dict
        # TODO: cycles?
        self._deps = cast(Set[str], set()).union(*(
            value.deps
            for value in self._conf_dict.values()
            if isinstance(value, DeferredValue)
        ))

    @property
    def deps(self) -> Set[str]:
        return self._deps

    def eval(self, deps: Dict[str, Any]) -> Any:
        # TODO: cycles?
        return {
            key: (value.eval(deps) if isinstance(value, DeferredValue) else value)
            for key, value in self._conf_dict.items()
        }


class ListValue(DeferredValue):
    def __init__(self, conf_list: list):
        self._conf_list = conf_list
        # TODO: cycles?
        self._deps = cast(Set[str], set()).union(*(
            item.deps
            for item in self._conf_list
            if isinstance(item, DeferredValue)
        ))

    @property
    def deps(self) -> Set[str]:
        return self._deps

    def eval(self, deps: Dict[str, Any]) -> Any:
        # TODO: cycles?
        return [
            item.eval(deps) if isinstance(item, DeferredValue) else item
            for item in self._conf_list
        ]


class RefValue(DeferredValue):
    def __init__(self, name: str):
        self._name = name

    @property
    def deps(self) -> Set[str]:
        return {self._name}

    def eval(self, deps: Dict[str, Any]) -> Any:
        return deps[self._name]


def load_container_config(value: Any) -> ContainerConfig:
    if not isinstance(value, dict):
        raise TypeError('container config should be dict', type(value))

    result = ContainerConfig(
        instances={
            inst_name: _load_instance_config(inst_name, inst_conf)
            for inst_name, inst_conf in value.items()
        },
    )

    return result


def check_container_config(
        config: ContainerConfig,
        impls: Union[Dict[str, PreparedSyncImpl], Dict[str, PreparedAsyncImpl]],
) -> None:

    for name, instance_config in config.instances.items():
        impl = impls.get(instance_config.impl_name)
        if impl is None:
            raise ValueError('impl doesn\'t exist', name, instance_config.impl_name)

        for param_name, param_value in instance_config.parameters.items():
            if param_name not in impl.params:
                raise ValueError(
                    'impl doesn\'t have specified param',
                    instance_config.impl_name, param_name)


def defer_value(config: Any) -> Any:
    return _load_param_value(config)


def _load_instance_config(instance_name: str, params_value: Any) -> InstanceConfig:
    if not isinstance(params_value, dict):
        raise TypeError('instance description should be dict', instance_name, type(params_value))

    params_value = params_value.copy()
    impl_name = params_value.pop(_impl_keyword, instance_name)
    parameters = {
        param_name: _load_param_value(param_value)
        for param_name, param_value in params_value.items()
    }
    return InstanceConfig(impl_name=impl_name, parameters=parameters)


_sentinel = object()


def _load_param_value(value: Any) -> Any:
    # TODO: support keyword escaping

    if isinstance(value, list):
        return ListValue([_load_param_value(item) for item in value])

    if not isinstance(value, dict):
        return value

    value = value.copy()

    instance_name = value.pop(_ref_keyword, _sentinel)
    if instance_name is not _sentinel:
        if value:
            raise ValueError(f'{_ref_keyword} should be the only property')
        if not isinstance(instance_name, str):
            raise TypeError(f'{_ref_keyword} should be str')

        return RefValue(instance_name)

    expression_code = value.pop(_expr_keyword, _sentinel)
    if expression_code is not _sentinel:
        if value:
            raise ValueError(f'{_expr_keyword} should be the only property')
        if not isinstance(expression_code, str):
            raise TypeError(f'{_expr_keyword} should be str')

        try:
            compile(expression_code, '<config>', 'eval')
        except SyntaxError as e:
            raise ValueError(f'{_expr_keyword} is malformed', expression_code) from e

        return ExpressionValue(expression_code)

    return DictValue({
        key: _load_param_value(val)
        for key, val in value.items()
    })
