import ast
from typing import Set


def expr_dependencies(expr: str, holder_name: str) -> Set[str]:
    """
    >>> expr_dependencies('i.dep1 + i.dep2', 'i') == {'dep1', 'dep2'}
    """

    # Very basic implementation, but should be okay for now.

    node = ast.parse(expr, '<config>', 'eval')

    finder = _ExprDepsFinder(holder_name)
    finder.visit(node)
    return finder.deps


class _ExprDepsFinder(ast.NodeVisitor):
    def __init__(self, holder_name: str):
        self.deps: Set[str] = set()

        self._holder_name = holder_name

    def visit_Attribute(self, node: ast.Attribute):
        value = node.value
        if isinstance(value, ast.Name) and value.id == self._holder_name:
            self.deps.add(node.attr)

        return self.generic_visit(node)
