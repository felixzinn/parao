from collections.abc import Callable
from typing import Annotated, Any, Literal

import pytest

from parao.cast import CastError, cast, sigcheck


def test_primitives():
    assert cast("123", int) == 123
    assert cast("1.3", float) == 1.3
    assert cast("1j", complex) == 1j
    assert cast(123, str) == "123"

    # forbidden
    with pytest.raises(CastError):
        cast("y", bool)
    with pytest.raises(CastError):
        cast(None, bool)
    with pytest.raises(CastError):
        cast(123, bytes)
    with pytest.raises(CastError):
        cast([], str)

    # None
    assert cast(None, None) is None
    assert cast(None, type(None)) is None
    with pytest.raises(TypeError):
        cast(True, None)

    assert cast("foo", Literal["foo"]) == "foo"
    with pytest.raises(CastError):
        cast("foo", Literal["bar"])

    # bad type
    with pytest.raises(TypeError):
        cast(..., ...)


def test_containers():
    assert cast(["123"], list[int]) == [123]
    assert cast({"123"}, set[int]) == {123}
    assert cast(frozenset({"123"}), frozenset[int]) == frozenset({123})

    assert cast({"123": 456}, dict[int, str]) == {123: "456"}
    assert cast([("123", 456)], dict[int, str]) == {123: "456"}

    # no str/bytes to sequence
    with pytest.raises(TypeError):
        cast("123", list[int])
    with pytest.raises(TypeError):
        cast(b"123", tuple[int, ...])

    # empty tuple
    assert cast([], tuple[()]) == ()
    with pytest.raises(ValueError):
        cast([1], tuple[()])

    # any tuple
    assert cast([1, 2, 3], tuple) == (1, 2, 3)
    assert cast([1, 2, 3], tuple[Any, ...]) == (1, 2, 3)
    with pytest.raises(TypeError):
        cast([1], tuple[...])  # type: ignore

    # fixed tuple
    assert cast([1, 2, 3], tuple[int, str, float]) == (1, "2", 3.0)
    with pytest.raises(ValueError):
        cast([], tuple[int])


def test_complex():
    with pytest.raises(ValueError):
        cast(1.2, int)
    assert cast("1.2", int | float) == 1.2
    with pytest.raises(TypeError):
        cast("foo", int | float)
    assert cast("123", Annotated[int, str]) == 123

    assert cast(f := lambda: None, Callable[..., None]) is f
    assert cast(f := lambda x: None, Callable[[None], None]) is f
    with pytest.raises(CastError):
        cast(lambda x: None, Callable[[], None])
    with pytest.raises(CastError):
        cast(lambda: None, Callable[[None], None])

    class Foo:
        @classmethod
        def __cast_from__(cls, value, original_type):
            return NotImplemented

    with pytest.raises(TypeError):
        cast(1, Foo)

    class Bar:
        def __cast_to__(self, typ, original_type):
            try:
                return typ(1.2)
            except Exception:
                return NotImplemented

    assert cast(Bar(), int) == 1
    with pytest.raises(TypeError):
        cast(Bar(), list)

    class Boo[T]: ...

    with pytest.raises(TypeError):
        cast(1, Boo[int])


def test_sigcheck():
    sigcheck(1, (), int)

    def foo() -> "str": ...

    sigcheck(foo, (), int)
