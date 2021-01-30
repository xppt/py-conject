import enum
from typing import Any, Optional, Mapping


@enum.unique
class FactoryType(enum.IntEnum):
    """
    Describes factory type to ensure correct component initialization [and deinitialization].

    `Value` - just value.
    `Func` - function returning implementation.
    `Class` - implementation-class.
    `GenFunc` - function generating implementation that can finalize it afterwards.
    `CtxMgr` - implementation context manager.
    `AFunc` - like `Func`, but async.
    `AGenFunc` - like `GenFunc`, but async.
    `ACtxMgr` - like `CtxMgr`, but async.
    """

    Value = enum.auto()
    Class = enum.auto()
    Func = enum.auto()
    GenFunc = enum.auto()
    CtxMgr = enum.auto()
    AFunc = enum.auto()
    AGenFunc = enum.auto()
    ACtxMgr = enum.auto()


class Impl:
    """
    Describes specific implementation.

    :param params: Bind default values for some factory params.
    """

    def __init__(
            self, ftype: FactoryType, name: str, factory: Any,
            params: Optional[Mapping[str, Any]] = None,
    ):
        self._ftype = ftype
        self._name = name
        self._factory = factory
        self._params = params

    @property
    def ftype(self) -> FactoryType:
        return self._ftype

    @property
    def name(self) -> str:
        return self._name

    @property
    def factory(self) -> Any:
        return self._factory

    @property
    def params(self) -> Optional[Mapping[str, Any]]:
        return self._params

    # FactoryType shortcuts
    Value = FactoryType.Value
    Class = FactoryType.Class
    Func = FactoryType.Func
    GenFunc = FactoryType.GenFunc
    CtxMgr = FactoryType.CtxMgr
    AFunc = FactoryType.AFunc
    AGenFunc = FactoryType.AGenFunc
    ACtxMgr = FactoryType.ACtxMgr
