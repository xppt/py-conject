import importlib
import pkgutil
from typing import Any, NamedTuple


def load_package_recursively(package_name: str) -> None:
    """Recursively import all package's modules. Doesn't handle namespace packages for now."""

    package = importlib.import_module(package_name)
    package_path = package.__path__  # type: ignore

    for _, module_name, _ in pkgutil.walk_packages(package_path, package_name + '.'):
        importlib.import_module(module_name)


class SkipTypeCheck(NamedTuple):
    """Ask conject to assume this value is correct as any param type."""

    value: Any


skip_type_check = SkipTypeCheck
