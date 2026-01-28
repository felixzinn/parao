import pytest

from parao.misc import ContextValue, PeekableIter, is_subseq, safe_len, safe_repr


def test_context_value_defaults():
    cv = ContextValue("cv")
    sentinel = object()
    assert cv(default=sentinel) is sentinel


def test_misc_safe():
    class Foo:
        def __repr__(self):
            raise RuntimeError()

        def __len__(self):
            raise TypeError()

    with pytest.raises(RuntimeError):
        repr(Foo())
    o = Foo()
    assert safe_repr(o) == object.__repr__(o)

    with pytest.raises(TypeError):
        len(Foo())
    o = object()
    assert safe_len(Foo(), o) is o


def test_peekable():
    tpl = object(), object(), object()
    pi = PeekableIter(tpl)

    assert pi.peek() is tpl[0]
    assert pi.peek() is tpl[0]
    assert pi.more is True
    assert tuple(pi) == tpl
    with pytest.raises(StopIteration):
        pi.peek()
    assert pi.more is False
    assert pi.peek(o := object()) is o


def test_is_subseq():
    assert is_subseq("india", "indonesia")
    assert is_subseq("oman", "romania")
    assert is_subseq("mali", "malawi")
    assert not is_subseq("mali", "banana")
    assert not is_subseq("ais", "indonesia")
    assert not is_subseq("ca", "abc")
