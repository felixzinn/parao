import pickle
from operator import attrgetter
from unittest.mock import Mock
from warnings import catch_warnings

import pytest

from parao.core import (
    UNSET,
    Args,
    Const,
    DuplicateParameter,
    Expansion,
    ExpansionGeneratedKeyMissingParameter,
    Fragment,
    Fragments,
    MissingParameterValue,
    OwnParameters,
    Param,
    ParaO,
    Prop,
    TypedAlias,
    Unset,
    UntypedParameter,
    Value,
    _Param,
    eager,
)
from parao.misc import TypedAliasClash, TypedAliasMismatch, TypedAliasRedefined

uniq_object = object()


def test_unset():
    assert isinstance(UNSET, Unset)
    assert UNSET is Unset()
    assert Unset() is Unset()
    assert repr(UNSET) == "<UNSET>"


def test_Value():
    val = Value(uniq_object)
    assert val.val is uniq_object
    assert val.prio == 0
    assert val.position == 0

    assert repr(Value(None, prio=1)) == "Value(None, 1)"
    assert repr(Value(None, position=1)) == "Value(None, 0, 1)"
    assert repr(Value(None, prio=1, position=1)) == "Value(None, 1, 1)"


def test_Fragment():
    key = ("foo", "bar")
    f = Fragment.make(key, Value(uniq_object))
    assert f == Fragment.make(key, uniq_object)
    assert f.param == key[0]
    assert f.types is None
    assert isinstance(f.inner, Fragment)
    i = f.inner
    assert i.param == key[1]
    assert i.types is None
    assert isinstance(i.inner, Value)

    vargs = (uniq_object, 1, 2)
    assert Fragment.make(("key",), *vargs).inner == Value(*vargs)

    assert (
        repr(Fragment.make(key, None))
        == "Fragment('foo', None, Fragment('bar', None, Value(None)))"
    )


def test_Fragments():
    tpl = (1, "foo", uniq_object)  # the are actually bad types ...
    assert Fragments(tpl) == tpl

    assert (
        Fragments(
            [
                Fragment.make(("foo",), uniq_object, 123),
                Fragment.make(("foo", "bar"), uniq_object, 123),
            ]
        )
        == Fragments.from_dict(
            {"foo": uniq_object, ("foo", "bar"): uniq_object},
            prio=123,
        )
        == Fragments.from_dict(
            [
                ("foo", uniq_object),
                (("foo", "bar"), uniq_object),
            ],
            prio=123,
        )
    )

    assert Fragments.from_dict({}) is Fragments.EMPTY
    assert Fragments.from_list([]) is Fragments.EMPTY
    assert Fragments.from_list([a := Fragments()]) is a
    assert Fragments.from_list([Fragment.make(("foo",), uniq_object)]) == Fragments(
        [Fragment.make(("foo",), uniq_object)]
    )

    with pytest.raises(TypeError):
        Fragments(123)

    assert repr(Fragments.make({})) == "Fragments()"
    assert (
        repr(Fragments.make(key=123)) == "Fragments(Fragment('key', None, Value(123)),)"
    )
    assert (
        repr(Fragments.make(foo=123, bar=456))
        == "Fragments(Fragment('foo', None, Value(123)), Fragment('bar', None, Value(456)))"
    )

    sub = Args(bar=uniq_object, boo=None)
    assert Fragment.make(("foo",), sub).inner == (
        Fragment.make(("bar",), uniq_object),
        Fragment.make(("boo",), None),
    )
    assert Fragments.make(foo=sub) == (Fragment.make(("foo",), sub),)

    frag = Fragment.make(("foo",), Args(bar=uniq_object).with_prio(123))
    assert frag.inner[0].inner.prio == 123
    assert frag.value.val is uniq_object

    assert Fragments.make(Args(foo=uniq_object).with_prio(123))[0].inner.prio == 123

    frags = Fragments(
        [
            Fragment.make(("foo",), uniq_object, 1),
            Fragment.make(("foo", "bar"), uniq_object, 2),
            Fragment.make(
                ("boo",),
                Fragments(
                    [
                        Fragment.make(("sub",), uniq_object, 3),
                        Fragment.make(("sub", "bar"), uniq_object, 4),
                    ]
                ),
            ),
            Fragments(
                [
                    Fragment.make(("nest",), uniq_object, 5),
                ]
            ),
        ]
    )
    assert list(frags.enumerate(nested=False, used=True)) == []
    assert list(frags.enumerate(nested=False)) == [
        (frags[0], frags[0].inner),
        (frags[1], frags[1].inner.inner),
    ]
    assert list(frags.enumerate(nested=True)) == [
        (frags[0], frags[0].inner),
        (frags[1], frags[1].inner.inner),
        (frags[2], frags[2].inner[0], frags[2].inner[0].inner),
        (frags[2], frags[2].inner[1], frags[2].inner[1].inner.inner),
        (frags[3][0], frags[3][0].inner),
    ]
    with pytest.raises(ValueError):
        frags[2].value


def test_param():
    assert Param(type=(o := object())).type is o
    assert Param[o := object()]().type is o
    with pytest.raises(TypeError):
        Param[int, str]

    # missing name - not really triggerable by user
    assert Param()._name(int) is None


def test_typed_alias():
    with pytest.warns(TypedAliasMismatch):

        class WonkyParam[A, B, C](_Param[B]): ...

    WonkyParam[int, str, bool]()

    class Sentinel:
        pass

    class StrangeParam(_Param):
        type = Sentinel

    assert StrangeParam().type is Sentinel

    with pytest.warns(TypedAliasRedefined):

        class RedundantParam[T](_Param[T]):
            TypedAlias.register(T, TypedAlias._typevar2name[T])

    with pytest.raises(TypedAliasClash):

        class ClashingParam[T](_Param[T]):
            TypedAlias.register(T, "not" + TypedAlias._typevar2name[T])

    with pytest.warns(TypedAliasMismatch):

        class MismatchParam[R](_Param[R]): ...


def test_specialized():
    uniq_const = object()
    uniq_aux = object()
    uniq_return = ParaO()
    uniq_override = ParaO()

    class Special(ParaO):
        const = Const(uniq_const)

        prop: ParaO

        @Prop(aux=uniq_aux)
        def prop(self):
            return uniq_return

    with pytest.raises(AttributeError):
        Special.prop._on_prop_attr
    with pytest.raises(AttributeError):
        Special.prop.on_func_attr

    Special.prop.func.on_func_attr = attr = object()
    assert Special.prop.on_func_attr is attr

    assert Special(const=None).const is uniq_const
    assert Special.prop.aux is uniq_aux
    assert Special().prop is uniq_return
    assert Special(prop=uniq_override).prop is uniq_override


def test_create():
    ParaO()

    class Sub(ParaO): ...

    assert isinstance(Sub(), Sub)
    assert isinstance(ParaO({ParaO: Sub}), Sub)
    assert isinstance(ParaO({"__class__": Sub}), Sub)

    # cover some rare branches
    assert isinstance(
        ParaO(
            Fragments(
                (
                    Fragments.from_dict({ParaO: UNSET}),
                    Fragments.EMPTY,
                    Fragments.from_dict({ParaO: Sub}),
                )
            )
        ),
        Sub,
    )

    with pytest.raises(TypeError):
        ParaO({ParaO: 123})

    with (
        catch_warnings(action="ignore", category=OwnParameters.CacheReset),
        pytest.raises(DuplicateParameter),
    ):
        Sub.foo1 = Sub.foo2 = Param()

    assert (
        Sub().__repr__(compact="???") == "tests.test_core:test_create.<locals>.Sub(???)"
    )


def test_own_params():
    class Sub(ParaO):
        foo: int = Param()
        bar: str = Param()

    assert Sub.__own_parameters__ == {"foo": Sub.foo, "bar": Sub.bar}

    with pytest.warns(OwnParameters.CacheReset):
        Sub.boo = Param(type=float)

    assert Sub.__own_parameters__["boo"] == Sub.boo

    with pytest.warns(OwnParameters.CacheReset):
        Sub.boo = Param(type=complex)

    assert Sub.__own_parameters__["boo"] == Sub.boo

    with pytest.warns(OwnParameters.CacheReset):
        del Sub.foo, Sub.bar, Sub.boo

    assert Sub.__own_parameters__ == {}

    with pytest.warns(OwnParameters.CacheReset):
        Sub.boo = None
    del Sub.boo

    Sub.__dunder__ = None
    del Sub.__dunder__


def test_resolution_simple():
    class Sub(ParaO):
        foo: int = Param()
        bar = Param(None, type=str)
        boo = Param[bool]()
        notyp = Param(None)

    assert Sub.boo.type is bool

    with pytest.raises(MissingParameterValue):
        Sub().foo
    with pytest.warns(UntypedParameter):
        Sub().notyp

    assert Sub({"foo": 123}).foo == 123
    assert Sub({Sub.foo: 123}).foo == 123
    assert Sub({(Sub, "foo"): 123}).foo == 123
    assert Sub({(Sub, Sub, "foo"): 123}).foo == 123
    assert Sub({(Sub, Sub.foo): 123}).foo == 123

    assert Sub().bar is None
    assert Sub(bar=123).bar == "123"

    assert Sub({("foo", "N_A"): 123, "N_A": "", "foo": 321}).foo == 321


def test_resolution_complex():
    class Sub(ParaO):
        foo: int = Param()
        bar: str = Param(None)

    class Sub2(Sub):
        boo: bool = Param()

    assert Sub({Sub: Sub2, "boo": True}).boo is True

    class Wrap(ParaO):
        one: Sub = Param()
        other: Sub2 = Param()

    class More(ParaO):
        inner: Wrap = Param()

    for addr in [("one", "bar"), (Wrap.one, Sub.bar), (Wrap.one, Sub, "bar")]:
        assert Wrap({addr: 123}).one.bar == "123"
        assert Wrap({addr: 123}).other.bar is None

    # providing a dict
    assert Wrap(one=dict(foo=123)).one.foo == 123

    # using instance's Fragments
    assert Wrap(one=Sub2(foo=123)).one.foo == 123
    assert Wrap(one=Sub2(foo=123).__fragments__).one.foo == 123

    # direct instance providing
    assert Wrap(one=Sub(foo=123)).one.foo == 123
    assert Wrap(one=(s := Sub())).one is s

    obj = Wrap({(Sub, "foo"): 123})
    assert obj.one.foo == 123
    assert obj.other.foo == 123

    # late commons
    assert Wrap({"foo": 321}, {("one", "N_A"): 123, "foo": 123}).one.foo == 123

    assert (
        Wrap(
            {("one", "bar"): "boo"},
            Fragments.make({(Sub, "foo"): 2}),
        ).one.foo
        == 2
    )


def test_remain():
    class Drain(ParaO):
        foo = Param[int]()
        bar = Param[str]()

    class Shared(ParaO):
        drain = Param[Drain]()

    class Low(Shared): ...

    class High(Shared):
        low = Param[Low]()

    h = High({("drain", "foo"): 0, (ParaO, "drain", "foo"): 1})

    assert h.drain.foo == 1
    assert h.low.drain.foo == 1


def test_gatekeeper():
    class Sub(ParaO):
        foo = Param[int]()
        bar = Param[str](None)

    class Wrap(ParaO):
        main = Param[Sub]()
        gated = Param[Sub](gatekeeper=True)

    w = Wrap(foo=123, bar="boo")
    assert w.main.foo == 123
    assert w.main.bar == "boo"
    with pytest.raises(MissingParameterValue):
        w.gated.foo
    assert w.gated.bar is None

    w2 = Wrap(gated=Fragments.make(foo=321), foo=123)
    assert w2.main.foo == 123
    assert w2.gated.foo == 321

    w3 = Wrap({(Sub, "foo"): 123})
    assert w3.main.foo == 123
    assert w3.gated.foo == 123

    # triggers "late commons" sub append skip
    w4 = Wrap({("gated", "foo"): 321, "foo": 123})
    assert w4.main.foo == 123
    assert w4.gated.foo == 321


def test_common_base():
    class Base(ParaO):
        foo = Param[int](0)

    class Ext1(Base):
        pass

    class Ext2(Base):
        ext1 = Param[Ext1]()

    ext2 = Ext2(foo=1)
    assert ext2.foo == 1
    assert ext2.ext1.foo == 0


def test_non_eager_parameter():
    class Foo(ParaO):
        bar = Param[int](eager=False)

    with eager(True):
        foo = Foo()
    with pytest.raises(MissingParameterValue):
        foo.bar


def test_expansion():
    class Foo(ParaO):
        bar = Param[int]()

    with eager(False):
        f = Foo(bar=[1, 2, 3])
        # raises on access
        with pytest.raises(Expansion):
            f.bar

    with eager(True):
        with pytest.raises(Expansion):
            Foo(bar=[1, 2, 3])
        try:
            Foo(Fragments.from_dict({"unused": 1}), bar=[1, 2, 3])
        except Expansion as exp:
            assert exp.param == Foo.bar
            assert exp.param_name == "bar"
            assert exp.values == (1, 2, 3)

    assert repr(Expansion([1, 2, 3])) == "Expansion(<3 values>)"


def test_collect():
    class Foo(ParaO):
        bar = Param[int]()

    # function based
    func = Mock(return_value=True)

    class Wrap(ParaO):
        foo = Param[Foo](collect=func)

    with eager(True):
        inst = Wrap(bar=[1, 2, 3])
    exp = inst.foo
    func.assert_called_once_with(exp, inst)
    assert isinstance(exp.source, Foo)
    assert isinstance(exp, Expansion)
    assert exp.make_key() == ("bar",)
    assert exp.make_key(False) == (Foo, "bar")
    assert exp.make_key(False, use_cls=False) == ("bar",)
    assert exp.make_key(False, use_name=False) == (Foo, Foo.bar)
    with pytest.warns(ExpansionGeneratedKeyMissingParameter):
        assert exp.make_key(False, use_param=False) == (Foo, "bar")
    with pytest.warns(ExpansionGeneratedKeyMissingParameter):
        assert exp.make_key(False, want=(Foo,), use_name=False) == (Foo, Foo.bar)
    assert exp.make_key(False, want=(Foo.bar,)) == ("bar",)
    assert isinstance(repr(exp), str)

    # bare argument based
    items = [[Foo], [Foo.bar], ["bar"]]
    for coll in items + [[it] for it in items]:
        with eager(True):
            Wrap.foo.collect = coll
            assert isinstance(Wrap(bar=[1, 2, 3]).foo, Expansion)


def test_expand():
    # uses two level expandable scenario

    class Foo(ParaO):
        bar = Param[int]()

    class Mid(ParaO):
        boo = Param[int](0)
        foo = Param[Foo]()

    class Wrap2(ParaO):
        mid = Param[Mid](collect=Mock(return_value=True))

    with eager(True):
        assert Wrap2(bar=[1, 2, 3]).mid.make_key() == ("bar",)
        assert Wrap2({("foo", "bar"): [1, 2, 3]}).mid.make_key() == ("foo", "bar")
        assert Wrap2(foo=dict(bar=[1, 2, 3])).mid.make_key() == (Mid, "foo", "bar")
        assert list(map(attrgetter("foo.bar"), Wrap2(bar=[1, 2, 3]).mid.expand())) == [
            1,
            2,
            3,
        ]
        assert list(
            map(
                attrgetter("foo.bar"),
                Wrap2({("foo", "bar"): [1, 2, 3]}).mid.expand(),
            )
        ) == [1, 2, 3]
        assert list(
            map(
                attrgetter("foo.bar"),
                Wrap2({("mid", "foo", "bar"): [1, 2, 3]}).mid.expand(),
            )
        ) == [1, 2, 3]
        assert list(
            map(
                attrgetter("boo", "foo.bar"),
                Wrap2(boo=[1, -1], bar=[1, 2, 3]).mid.expand(),
            )
        ) == [
            (1, 1),
            (1, 2),
            (1, 3),
            (-1, 1),
            (-1, 2),
            (-1, 3),
        ]


def test_inner():
    out1 = Out()
    assert tuple(out1.__inner__) == (out1.in1, *out1.in2, out1.in3u, out1.in3u)

    out2 = Out(in2=[In(), In()])
    assert tuple(out2.__inner__) == (out2.in1, *out2.in2, out2.in3u, out2.in3u)

    with eager(True):
        out3 = Out({("in1", "exp"): [1, 2]})
    inner = tuple(out3.__inner__)
    assert inner[0].exp == 1
    assert inner[1].exp == 2
    assert inner[2:] == (out3.in3u, out3.in3u)


def test_pickle():
    pre = Out({(In, In.exp): 1, "in2": [In(exp=2, uniq=3)], "uniq": -1})
    post = pickle.loads(pickle.dumps(pre))
    assert pre == post
    with pytest.raises(pickle.PicklingError):
        pickle.dumps(bare_param)


class In(ParaO):
    exp = Param[int](0)

    @Prop
    def uniq(self) -> int:
        return id(self)


class Out(ParaO):
    in1 = Param[In](collect=[In.exp])
    in2 = Param[list[In]]([])

    in3u = Param[In](significant=False)

    @Prop
    def in3(self) -> dict:
        return {
            "deep": [
                "nested",
                ("structure", {"with", frozenset({"some", (self.in3u,) * 2})}),
            ]
        }


bare_param = Param[str]()
