"""
Tests unitaires — streaming JSON parsing & fan-in merge
=========================================================
Couvre app.infrastructure.llm.multi_worker_extractor._StreamingArrayParser
et app.services.job_matching._merge_async_iterables.
Aucun LLM, aucun mock réseau — logique pure testée en isolation.
"""
import asyncio
import json
import random

import pytest

from app.infrastructure.llm.multi_worker_extractor import _StreamingArrayParser
from app.services.job_matching import _merge_async_iterables

pytestmark = pytest.mark.unit


class TestStreamingArrayParser:
    """_StreamingArrayParser.feed() incrementally parses a JSON array of objects."""

    def test_single_feed_whole_array(self):
        parser = _StreamingArrayParser()
        objs = [{"name": "Alice"}, {"name": "Bob"}]
        result = parser.feed(json.dumps(objs))
        assert result == objs

    def test_char_by_char_streaming(self):
        parser = _StreamingArrayParser()
        objs = [{"a": 1}, {"b": 2}, {"c": 3}]
        raw = json.dumps(objs)
        results = []
        for ch in raw:
            results.extend(parser.feed(ch))
        assert results == objs

    def test_randomized_chunk_boundaries(self):
        """Objects split at arbitrary byte offsets must still parse correctly —
        this is what real LLM token deltas look like (no alignment to object
        boundaries)."""
        sample = [
            {
                "name": "Alice",
                "skills": ["Python", "SQL"],
                "experiences": [{"company": "Acme", "title": "Dev"}],
                "summary": 'A "quoted" bit, and a brace } inside a string.',
            },
            {"name": "Bob", "skills": [], "experiences": []},
            {"name": None, "email": "c@example.com"},
        ]
        raw = json.dumps(sample)
        parser = _StreamingArrayParser()
        results = []
        rng = random.Random(42)
        i = 0
        while i < len(raw):
            step = rng.randint(1, 5)
            results.extend(parser.feed(raw[i:i + step]))
            i += step
        assert results == sample

    def test_markdown_fence_is_ignored(self):
        parser = _StreamingArrayParser()
        sample = [{"x": 1}]
        raw = "```json\n" + json.dumps(sample) + "\n```"
        results = []
        for ch in raw:
            results.extend(parser.feed(ch))
        assert results == sample

    def test_malformed_object_is_skipped_not_raised(self):
        """A single malformed object must not crash the parser or block
        subsequent valid objects — extraction/matching depend on this to
        keep other CVs/candidates in the same batch usable."""
        parser = _StreamingArrayParser()
        raw = '[{"ok": 1}, {"bad": }, {"ok": 2}]'
        results = []
        for ch in raw:
            results.extend(parser.feed(ch))
        assert results == [{"ok": 1}, {"ok": 2}]

    def test_empty_array(self):
        parser = _StreamingArrayParser()
        assert parser.feed("[]") == []

    def test_nested_braces_in_arrays_do_not_break_depth_tracking(self):
        parser = _StreamingArrayParser()
        sample = [{"experiences": [{"a": {"b": {"c": 1}}}, {"d": 2}]}]
        raw = json.dumps(sample)
        results = []
        for ch in raw:
            results.extend(parser.feed(ch))
        assert results == sample


class TestMergeAsyncIterables:
    """_merge_async_iterables fans-in several async generators by arrival order."""

    @pytest.mark.asyncio
    async def test_yields_all_items_from_all_generators(self):
        async def gen(items, delay):
            for item in items:
                await asyncio.sleep(delay)
                yield item

        g1 = gen([1, 2, 3], 0.01)
        g2 = gen([10, 20], 0.02)

        results = [item async for item in _merge_async_iterables([g1, g2])]

        assert sorted(results) == [1, 2, 3, 10, 20]

    @pytest.mark.asyncio
    async def test_faster_generator_items_can_arrive_before_slower_ones(self):
        async def fast():
            yield "fast-1"
            await asyncio.sleep(0.05)
            yield "fast-2"

        async def slow():
            await asyncio.sleep(0.2)
            yield "slow-1"

        results = [item async for item in _merge_async_iterables([slow(), fast()])]

        # Both fast items should be observed before the single slow item —
        # this is the actual "progressive reveal" behavior the feature exists for.
        assert results.index("fast-1") < results.index("slow-1")
        assert results.index("fast-2") < results.index("slow-1")

    @pytest.mark.asyncio
    async def test_empty_generator_list(self):
        results = [item async for item in _merge_async_iterables([])]
        assert results == []

    @pytest.mark.asyncio
    async def test_single_generator_behaves_like_passthrough(self):
        async def gen():
            yield 1
            yield 2
            yield 3

        results = [item async for item in _merge_async_iterables([gen()])]
        assert results == [1, 2, 3]

    @pytest.mark.asyncio
    async def test_generator_that_raises_does_not_hang_the_merge(self):
        async def bad():
            yield "before-error"
            raise RuntimeError("boom")

        async def good():
            await asyncio.sleep(0.02)
            yield "good-item"

        results = [item async for item in _merge_async_iterables([bad(), good()])]

        # The failing generator's item before the raise is still delivered,
        # and the other generator's item must not be lost.
        assert "before-error" in results
        assert "good-item" in results
