from typing import Any

import asynctest

from conject import AsyncDepSpec, DepSpec, Impl, InvalidImplParam, InvalidInstanceType
from conject.utils import SkipTypeCheck


class ConjectTestCase(asynctest.TestCase):
    def _make_spec(self, cls: Any = DepSpec):
        spec = cls()

        @spec.decorate(spec.Func)
        def return_sum(first: int, second: int = 10) -> int:
            return first + second

        @spec.decorate(spec.Class, 'cls')
        class Cls:
            def __init__(self, param: int):
                pass

        def return_7() -> int:
            return 7

        spec.add_many([
            Impl(spec.Func, 'return_7', return_7),
        ])

        return spec

    def _basic_config(self):
        return {
            'sum_inst': {
                '-impl': 'return_sum',
                'first': {'-ref': 'first_arg'},
                'second': 1,
            },
            'first_arg': {'-impl': 'return_7'},
        }

    def test_basic(self):
        with self._make_spec()._start_container(self._basic_config()) as container:
            container.ensure_constructible('sum_inst')
            self.assertEqual(container.get('sum_inst'), 8)
            self.assertEqual(container.get_params(lambda sum_inst: None), {'sum_inst': 8})

    async def test_basic_async(self):
        spec = self._make_spec(AsyncDepSpec)

        @spec.decorate(spec.AFunc)
        async def async_provider():
            return 'async-value'

        conf = self._basic_config()
        conf['async_inst'] = {'-impl': 'async_provider'}

        async with spec.start_container(conf) as container:
            container.ensure_constructible('sum_inst')
            self.assertEqual(await container.get('sum_inst'), 8)
            self.assertEqual(await container.get('async_inst'), 'async-value')
            self.assertEqual(await container.get_params(lambda sum_inst: None), {'sum_inst': 8})

    def test_default_factory_param(self):
        config = {
            'sum_inst': {
                '-impl': 'return_sum',
                'first': {'-expr': '123'},
            },
        }

        with self._make_spec().start_container(config) as container:
            self.assertEqual(container.get('sum_inst'), 133)

    def test_auto_impl(self):
        config = {
            'return_7': {},
        }

        with self._make_spec().start_container(config) as container:
            self.assertEqual(container.get('return_7'), 7)

    def test_auto_dep(self):
        config = {
            'sum_inst': {'-impl': 'return_sum'},
            'first': {'-impl': 'return_7'},
            'second': {'-impl': 'return_7'},
        }

        with self._make_spec().start_container(config) as container:
            self.assertEqual(container.get('sum_inst'), 17)

    def test_auto_instance(self):
        config = {'first': {'-impl': 'return_7'}}
        with self._make_spec().start_container(config) as container:
            self.assertEqual(container.get('return_sum'), 17)

    def test_type_check(self):
        config = {
            'sum_inst': {
                '-impl': 'return_sum',
                'first': 2,
                'second': 'two',
            },
            'cls_inst': {
                '-impl': 'cls',
                'param': 'str',
            },
            'sum_inst_2': {
                '-impl': 'return_sum',
                'first': 1,
                'second': 2,
            },
        }
        with self._make_spec().start_container(config) as container:
            # unfortunately not checking type at the moment
            container.ensure_constructible('sum_inst')

            with self.assertRaises(InvalidImplParam):
                container.get('sum_inst')
            with self.assertRaises(InvalidImplParam):
                container.get('cls_inst')

            container.get('sum_inst_2', int)
            with self.assertRaises(InvalidInstanceType):
                container.get('sum_inst_2', dict)

    def test_skip_type_check(self):
        config = {
            'sum_inst': {
                '-impl': 'return_sum',
                'first': SkipTypeCheck('one'),
                'second': SkipTypeCheck('two'),
            },
        }
        with self._make_spec().start_container(config) as container:
            container.ensure_constructible('sum_inst')
            self.assertEqual(container.get('sum_inst'), 'onetwo')

    def test_sync_factories(self):
        call_log = []

        impls = _get_sync_impls(call_log)
        spec = DepSpec()
        spec.add_many(impls)
        with spec.start_container({}) as container:
            for impl in impls:
                self.assertEqual(container.get(impl.name), impl.name)

            call_log.append('close container')

        self.assertEqual(call_log, [
            'impl_gen_func: before',
            'impl_ctx_mgr: before',
            'close container',
            'impl_ctx_mgr: after',
            'impl_gen_func: after',
        ])

    async def test_async_factories(self):
        call_log = []

        impls = _get_sync_impls(call_log) + _get_async_impls(call_log)
        spec = AsyncDepSpec()
        spec.add_many(impls)
        async with spec.start_container({}) as container:
            for impl in impls:
                self.assertEqual(await container.get(impl.name), impl.name)

            call_log.append('close container')

        self.assertEqual(call_log, [
            'impl_gen_func: before',
            'impl_ctx_mgr: before',
            'impl_async_gen_func: before',
            'impl_async_ctx_mgr: before',
            'close container',
            'impl_async_ctx_mgr: after',
            'impl_async_gen_func: after',
            'impl_ctx_mgr: after',
            'impl_gen_func: after',
        ])


def _get_sync_impls(call_log):
    spec = DepSpec()
    spec.add(spec.Value, 'impl_value', 'impl_value')

    @spec.decorate(spec.Func)
    def impl_func():
        return 'impl_func'

    @spec.decorate(spec.GenFunc)
    def impl_gen_func():
        call_log.append('impl_gen_func: before')
        yield 'impl_gen_func'
        call_log.append('impl_gen_func: after')

    @spec.decorate(spec.Class, 'impl_class')
    class ImplClass:
        def __init__(self):
            self.prop = 'impl_class'

        def __eq__(self, other):
            return self.prop == other

    @spec.decorate(spec.CtxMgr, 'impl_ctx_mgr')
    class ImplCtxMgr:
        def __enter__(self):
            call_log.append('impl_ctx_mgr: before')
            return 'impl_ctx_mgr'

        def __exit__(self, exc_type, exc_val, exc_tb):
            call_log.append('impl_ctx_mgr: after')

    return spec.get_list()


def _get_async_impls(call_log):
    spec = AsyncDepSpec()

    @spec.decorate(spec.AFunc)
    async def impl_async_func():
        return 'impl_async_func'

    @spec.decorate(spec.AGenFunc)
    async def impl_async_gen_func():
        call_log.append('impl_async_gen_func: before')
        yield 'impl_async_gen_func'
        call_log.append('impl_async_gen_func: after')

    @spec.decorate(spec.ACtxMgr, 'impl_async_ctx_mgr')
    class ImplAsyncCtxMgr:
        async def __aenter__(self):
            call_log.append('impl_async_ctx_mgr: before')
            return 'impl_async_ctx_mgr'

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            call_log.append('impl_async_ctx_mgr: after')

    return spec.get_list()
