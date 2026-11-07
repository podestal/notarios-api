from django.test import SimpleTestCase

from compliance.services.collector_cache import CollectorCache, cached_call, collector_cache_scope


class CollectorCacheTests(SimpleTestCase):
    def test_without_scope_factory_runs_every_time(self):
        calls = {"n": 0}

        def factory():
            calls["n"] += 1
            return calls["n"]

        self.assertEqual(cached_call("uif", "K1", factory), 1)
        self.assertEqual(cached_call("uif", "K1", factory), 2)

    def test_scope_memoizes_per_kind_and_kardex(self):
        calls = {"n": 0}

        def factory():
            calls["n"] += 1
            return {"n": calls["n"]}

        with collector_cache_scope(CollectorCache()):
            first = cached_call("uif", "K1", factory)
            second = cached_call("uif", "K1", factory)
            other = cached_call("pdt", "K1", factory)
        self.assertIs(first, second)
        self.assertEqual(first["n"], 1)
        self.assertEqual(other["n"], 2)
