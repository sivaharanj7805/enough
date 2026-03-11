"""Tests for the Oracle service — verdict parsing, confidence levels, merging."""

import pytest
from app.services.oracle import PrePublishOracle


class TestParseJsonResponse:
    """Test the JSON response parser used for Claude verdicts."""

    def test_clean_json(self):
        raw = '{"confidence": "high", "verdict": "publish", "reasoning": "Good topic", "recommendation": "Go ahead"}'
        result = PrePublishOracle._parse_json_response(raw)
        assert result["confidence"] == "high"
        assert result["verdict"] == "publish"

    def test_markdown_code_block(self):
        raw = '```json\n{"confidence": "medium", "verdict": "update_existing", "reasoning": "Overlap found", "recommendation": "Merge"}\n```'
        result = PrePublishOracle._parse_json_response(raw)
        assert result["confidence"] == "medium"
        assert result["verdict"] == "update_existing"

    def test_json_with_preamble(self):
        raw = 'Here is my analysis:\n\n{"confidence": "low", "verdict": "skip", "reasoning": "Saturated", "recommendation": "Don\'t publish"}'
        result = PrePublishOracle._parse_json_response(raw)
        assert result["confidence"] == "low"
        assert result["verdict"] == "skip"

    def test_unparseable_returns_fallback(self):
        raw = "This is just text without any JSON"
        result = PrePublishOracle._parse_json_response(raw)
        assert result["confidence"] == "low"
        assert "Manual review" in result["recommendation"]

    def test_empty_string(self):
        result = PrePublishOracle._parse_json_response("")
        assert result["confidence"] == "low"

    def test_partial_json(self):
        raw = '{"confidence": "high", "verdict": "publish"'
        result = PrePublishOracle._parse_json_response(raw)
        # Should fall back since JSON is incomplete
        assert result["confidence"] == "low"


class TestMergeSimilar:
    """Test deduplication and merging of similar post results."""

    def setup_method(self):
        self.oracle = PrePublishOracle.__new__(PrePublishOracle)

    def test_no_duplicates(self):
        embedding = [{"post_id": "aaa", "source": "embedding", "title": "Post A"}]
        keyword = [{"post_id": "bbb", "source": "keyword", "title": "Post B"}]
        result = self.oracle._merge_similar(embedding, keyword)
        assert len(result) == 2

    def test_deduplication(self):
        embedding = [{"post_id": "aaa", "source": "embedding", "title": "Post A"}]
        keyword = [{"post_id": "aaa", "source": "keyword", "title": "Post A", "avg_position": 5.2, "total_clicks": 100}]
        result = self.oracle._merge_similar(embedding, keyword)
        assert len(result) == 1
        assert result[0]["source"] == "both"
        assert result[0]["avg_position"] == 5.2

    def test_empty_inputs(self):
        result = self.oracle._merge_similar([], [])
        assert result == []

    def test_only_embedding(self):
        embedding = [{"post_id": "aaa", "source": "embedding", "title": "A"}]
        result = self.oracle._merge_similar(embedding, [])
        assert len(result) == 1
        assert result[0]["source"] == "embedding"

    def test_only_keyword(self):
        keyword = [{"post_id": "bbb", "source": "keyword", "title": "B"}]
        result = self.oracle._merge_similar([], keyword)
        assert len(result) == 1
        assert result[0]["source"] == "keyword"
