import json
import pytest
from typing import Dict, Any
from pathlib import Path
import sys
from deepeval.test_case import LLMTestCase
from deepeval.metrics.answer_relevancy.answer_relevancy import AnswerRelevancyMetric
from deepeval.metrics import (
    ContextualPrecisionMetric,
    ContextualRecallMetric,
    ContextualRelevancyMetric,
    FaithfulnessMetric,
)

sys.path.insert(0, str(Path(__file__).parent.parent))
from mocks.dummy_llm_orchestrator import process_query


class TestRAGSystem:
    """Test suite for RAG system evaluation using DeepEval metrics."""

    @classmethod
    def setup_class(cls):
        """Setup test class with metrics and test data."""
        # Initialize all DeepEval metrics
        cls.contextual_precision: ContextualPrecisionMetric = ContextualPrecisionMetric(
            threshold=0.7
        )
        cls.contextual_recall: ContextualRecallMetric = ContextualRecallMetric(
            threshold=0.7
        )
        cls.contextual_relevancy: ContextualRelevancyMetric = ContextualRelevancyMetric(
            threshold=0.7
        )
        cls.answer_relevancy: AnswerRelevancyMetric = AnswerRelevancyMetric(
            threshold=0.7
        )
        cls.faithfulness: FaithfulnessMetric = FaithfulnessMetric(threshold=0.7)

        # Load test dataset
        data_path = Path(__file__).parent.parent / "data" / "test_dataset.json"
        with open(data_path, "r", encoding="utf-8") as f:
            cls.test_data = json.load(f)

    def create_test_case(
        self, data_item: Dict[str, Any], provider: str = "anthropic"
    ) -> LLMTestCase:
        """Create a DeepEval test case from data item."""
        # Generate actual output using the dummy orchestrator
        result = process_query(
            question=data_item["input"], provider=provider, include_contexts=True
        )

        llm_test_case: LLMTestCase = LLMTestCase(
            input=data_item["input"],
            actual_output=result["response"],
            expected_output=data_item["expected_output"],
            retrieval_context=result["retrieval_context"],
        )
        return llm_test_case

    @pytest.mark.parametrize(
        "test_item",
        [
            item
            for item in json.load(
                open(
                    Path(__file__).parent.parent / "data" / "test_dataset.json",
                    "r",
                    encoding="utf-8",
                )
            )
        ],
    )
    def test_contextual_precision(self, test_item: Dict[str, Any]):
        """Test contextual precision - whether reranker ranks relevant nodes higher."""
        test_case: LLMTestCase = self.create_test_case(test_item)
        self.contextual_precision.measure(test_case)
        score: float | None = self.contextual_precision.score
        assert score is not None, "Contextual Precision score is None."
        assert score >= 0.7, (
            f"Contextual Precision failed for query: '{test_item['input']}'. "
            f"Score: {score}, "
            f"Reason: {self.contextual_precision.reason}"
        )

    @pytest.mark.parametrize(
        "test_item",
        [
            item
            for item in json.load(
                open(
                    Path(__file__).parent.parent / "data" / "test_dataset.json",
                    "r",
                    encoding="utf-8",
                )
            )
        ],
    )
    def test_contextual_recall(self, test_item: Dict[str, Any]):
        """Test contextual recall - whether embedding model retrieves relevant information."""
        test_case: LLMTestCase = self.create_test_case(test_item)
        self.contextual_recall.measure(test_case)
        score: float | None = self.contextual_recall.score
        assert score is not None, "Contextual Recall score is None."
        assert score >= 0.7, (
            f"Contextual Recall failed for query: '{test_item['input']}'. "
            f"Score: {score}, "
            f"Reason: {self.contextual_recall.reason}"
        )

    @pytest.mark.parametrize(
        "test_item",
        [
            item
            for item in json.load(
                open(
                    Path(__file__).parent.parent / "data" / "test_dataset.json",
                    "r",
                    encoding="utf-8",
                )
            )
        ],
    )
    def test_contextual_relevancy(self, test_item: Dict[str, Any]):
        """Test contextual relevancy - whether retriever gets right amount of info without irrelevancies."""
        test_case = self.create_test_case(test_item)
        self.contextual_relevancy.measure(test_case)
        score: float | None = self.contextual_relevancy.score
        assert score is not None, "Contextual Relevancy score is None."
        assert score >= 0.7, (
            f"Contextual Relevancy failed for query: '{test_item['input']}'. "
            f"Score: {score}, "
            f"Reason: {self.contextual_relevancy.reason}"
        )

    @pytest.mark.parametrize(
        "test_item",
        [
            item
            for item in json.load(
                open(
                    Path(__file__).parent.parent / "data" / "test_dataset.json",
                    "r",
                    encoding="utf-8",
                )
            )
        ],
    )
    def test_answer_relevancy(self, test_item: Dict[str, Any]):
        """Test answer relevancy - whether LLM outputs relevant responses based on context."""
        test_case: LLMTestCase = self.create_test_case(test_item)
        self.answer_relevancy.measure(test_case)

        score: float | None = self.answer_relevancy.score
        assert score is not None, "Answer Relevancy score is None."
        assert score >= 0.7, (
            f"Answer Relevancy failed for query: '{test_item['input']}'. "
            f"Score: {score}, "
            f"Reason: {self.answer_relevancy.reason}"
        )

    @pytest.mark.parametrize(
        "test_item",
        [
            item
            for item in json.load(
                open(
                    Path(__file__).parent.parent / "data" / "test_dataset.json",
                    "r",
                    encoding="utf-8",
                )
            )
        ],
    )
    def test_faithfulness(self, test_item: Dict[str, Any]):
        """Test faithfulness - whether LLM outputs don't hallucinate or contradict context."""
        test_case: LLMTestCase = self.create_test_case(test_item)
        self.faithfulness.measure(test_case)
        score: float | None = self.faithfulness.score
        assert score is not None, "Faithfulness score is None."
        assert score >= 0.7, (
            f"Faithfulness failed for query: '{test_item['input']}'. "
            f"Score: {score}, "
            f"Reason: {self.faithfulness.reason}"
        )


def run_comprehensive_evaluation() -> Dict[str, Any]:
    """
    Run comprehensive evaluation of all metrics and return summary results.
    Used by the report generator for GitHub Actions output.
    """
    test_instance = TestRAGSystem()
    test_instance.setup_class()

    results: dict[str, Any] = {
        "total_tests": 0,
        "passed_tests": 0,
        "failed_tests": 0,
        "metric_scores": {
            "contextual_precision": [],
            "contextual_recall": [],
            "contextual_relevancy": [],
            "answer_relevancy": [],
            "faithfulness": [],
        },
        "detailed_results": [],
    }

    # Run evaluation on all test cases
    for i, test_item in enumerate(test_instance.test_data):
        test_case: LLMTestCase = test_instance.create_test_case(test_item)

        # Evaluate with all metrics
        metrics: list[tuple[str, Any]] = [
            ("contextual_precision", test_instance.contextual_precision),
            ("contextual_recall", test_instance.contextual_recall),
            ("contextual_relevancy", test_instance.contextual_relevancy),
            ("answer_relevancy", test_instance.answer_relevancy),
            ("faithfulness", test_instance.faithfulness),
        ]

        test_result: dict[str, Any] = {
            "test_case": i + 1,
            "input": test_item["input"],
            "category": test_item["category"],
            "language": test_item.get("language", "en"),
            "metrics": {},
        }

        for metric_name, metric in metrics:
            try:
                metric.measure(test_case)
                score = metric.score
                passed = score >= 0.7

                results["metric_scores"][metric_name].append(score)
                results["total_tests"] += 1
                if passed:
                    results["passed_tests"] += 1
                else:
                    results["failed_tests"] += 1

                test_result["metrics"][metric_name] = {
                    "score": score,
                    "passed": passed,
                    "reason": metric.reason,
                }
            except Exception as e:
                test_result["metrics"][metric_name] = {
                    "score": 0.0,
                    "passed": False,
                    "reason": f"Error: {str(e)}",
                }
                results["total_tests"] += 1
                results["failed_tests"] += 1

        results["detailed_results"].append(test_result)

    return results
