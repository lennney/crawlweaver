"""Tests for LLM cost tracking."""
from llm import CostRecord


def test_cost_record():
    """CostRecord should track tokens and cost."""
    cr = CostRecord(step="rewrite", input_tokens=500, output_tokens=2000, model="deepseek-chat")
    assert cr.step == "rewrite"
    assert cr.input_tokens == 500
    assert cr.output_tokens == 2000
    assert cr.total_tokens == 2500
    assert cr.cost_usd >= 0  # cost calculated from pricing


def test_cost_record_from_usage():
    """Should create CostRecord from OpenAI usage dict."""
    usage = {"prompt_tokens": 300, "completion_tokens": 1500}
    cr = CostRecord.from_usage(step="seo", usage=usage, model="deepseek-chat")
    assert cr.input_tokens == 300
    assert cr.output_tokens == 1500
    assert cr.total_tokens == 1800
    assert cr.cost_usd > 0  # deepseek-chat has pricing


def test_cost_record_local_model():
    """Local models should have zero cost."""
    usage = {"prompt_tokens": 100, "completion_tokens": 500}
    cr = CostRecord.from_usage(step="rewrite", usage=usage, model="qwen2.5:7b")
    assert cr.cost_usd == 0.0


def test_cost_record_unknown_model():
    """Unknown models should have zero cost."""
    usage = {"prompt_tokens": 100, "completion_tokens": 500}
    cr = CostRecord.from_usage(step="rewrite", usage=usage, model="gpt-4o")
    assert cr.cost_usd == 0.0


def test_cost_record_missing_usage():
    """Should handle missing token fields gracefully."""
    usage = {}
    cr = CostRecord.from_usage(step="verify", usage=usage, model="deepseek-chat")
    assert cr.input_tokens == 0
    assert cr.output_tokens == 0
    assert cr.total_tokens == 0
    assert cr.cost_usd == 0.0


def test_llm_last_cost_init():
    """LLM should initialize with last_cost=None."""
    from llm import LLM
    llm = LLM()
    assert llm.last_cost is None
