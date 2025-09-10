from typing import Dict, Any, List
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from deepeval_tests.standard_tests import run_comprehensive_evaluation


def calculate_average_scores(metric_scores: Dict[str, List[float]]) -> Dict[str, float]:
    """Calculate average scores for each metric."""
    averages: dict[str, float] = {}
    for metric, scores in metric_scores.items():
        if scores:
            averages[metric] = sum(scores) / len(scores)
        else:
            averages[metric] = 0.0
    return averages


def generate_summary_table(results: Dict[str, Any]) -> str:
    """Generate summary table with overall results."""
    total_tests = results["total_tests"]
    passed_tests = results["passed_tests"]
    failed_tests = results["failed_tests"]
    pass_rate = (passed_tests / total_tests * 100) if total_tests > 0 else 0

    avg_scores = calculate_average_scores(results["metric_scores"])

    table = "## DeepEval Test Results Summary\n\n"
    table += "| Metric | Pass Rate | Avg Score | Status |\n"
    table += "|--------|-----------|-----------|--------|\n"

    overall_status = "PASS" if pass_rate >= 70 else "FAIL"
    table += f"| **Overall** | {pass_rate:.1f}% | - | **{overall_status}** |\n"

    metric_names = {
        "contextual_precision": "Contextual Precision",
        "contextual_recall": "Contextual Recall",
        "contextual_relevancy": "Contextual Relevancy",
        "answer_relevancy": "Answer Relevancy",
        "faithfulness": "Faithfulness",
    }

    for metric_key, metric_name in metric_names.items():
        scores = results["metric_scores"][metric_key]
        if scores:
            avg_score = avg_scores[metric_key]
            passed_count = sum(1 for score in scores if score >= 0.7)
            metric_pass_rate = passed_count / len(scores) * 100
            status = "PASS" if metric_pass_rate >= 70 else "FAIL"
            table += f"| {metric_name} | {metric_pass_rate:.1f}% | {avg_score:.3f} | {status} |\n"
        else:
            table += f"| {metric_name} | 0.0% | 0.000 | FAIL |\n"

    table += f"\n**Total Tests:** {total_tests} | **Passed:** {passed_tests} | **Failed:** {failed_tests}\n\n"
    return table


def generate_detailed_results_table(results: Dict[str, Any]) -> str:
    """Generate detailed results table for each test case."""
    table = "## Detailed Test Results\n\n"
    table += "| Test | Language | Category | CP | CR | CRel | AR | Faith | Status |\n"
    table += "|------|----------|----------|----|----|------|----|----- -|--------|\n"

    for result in results["detailed_results"]:
        test_num = result["test_case"]
        category = result["category"]
        language = result.get("language", "en").upper()

        # Get scores for each metric (abbreviated column names)
        cp_score = result["metrics"]["contextual_precision"]["score"]
        cr_score = result["metrics"]["contextual_recall"]["score"]
        crel_score = result["metrics"]["contextual_relevancy"]["score"]
        ar_score = result["metrics"]["answer_relevancy"]["score"]
        faith_score = result["metrics"]["faithfulness"]["score"]

        # Determine overall status for this test case
        all_scores = [cp_score, cr_score, crel_score, ar_score, faith_score]
        passed_metrics = sum(1 for score in all_scores if score >= 0.7)
        test_status = (
            "PASS" if passed_metrics >= 4 else "FAIL"
        )  # 4 out of 5 metrics need to pass

        table += f"| {test_num} | {language} | {category} | {cp_score:.2f} | {cr_score:.2f} | {crel_score:.2f} | {ar_score:.2f} | {faith_score:.2f} | {test_status} |\n"

    table += "\n**Legend:** CP = Contextual Precision, CR = Contextual Recall, CRel = Contextual Relevancy, AR = Answer Relevancy, Faith = Faithfulness\n"
    table += "**Languages:** EN = English, ET = Estonian, RU = Russian\n\n"
    return table


def generate_failure_analysis(results: Dict[str, Any]) -> str:
    """Generate analysis of failed tests."""
    failed_results: list[dict[str, Any]] = []

    for result in results["detailed_results"]:
        for metric_name, metric_result in result["metrics"].items():
            if not metric_result["passed"]:
                failed_results.append(
                    {
                        "test_case": result["test_case"],
                        "input": result["input"],
                        "category": result["category"],
                        "metric": metric_name,
                        "score": metric_result["score"],
                        "reason": metric_result["reason"],
                    }
                )

    if not failed_results:
        return (
            "## Analysis\n\nAll tests passed successfully! No failures to analyze.\n\n"
        )

    analysis = "## Failed Test Analysis\n\n"
    analysis += "| Test | Query | Metric | Score | Issue |\n"
    analysis += "|------|--------|--------|-------|-------|\n"

    for failure in failed_results[:10]:  # Limit to first 10 failures
        query_preview = (
            failure["input"][:50] + "..."
            if len(failure["input"]) > 50
            else failure["input"]
        )
        reason_preview = (
            failure["reason"][:100] + "..."
            if len(failure["reason"]) > 100
            else failure["reason"]
        )

        analysis += f"| {failure['test_case']} | {query_preview} | {failure['metric']} | {failure['score']:.2f} | {reason_preview} |\n"

    if len(failed_results) > 10:
        analysis += f"\n*({len(failed_results) - 10} additional failures not shown)*\n"

    analysis += "\n"
    return analysis


def generate_recommendations(results: Dict[str, Any]) -> str:
    """Generate recommendations based on test results."""
    recommendations = "## Recommendations\n\n"

    avg_scores = calculate_average_scores(results["metric_scores"])
    low_performing_metrics = [
        (metric, score) for metric, score in avg_scores.items() if score < 0.7
    ]

    if not low_performing_metrics:
        recommendations += (
            "All metrics are performing well above the threshold of 0.7. Great job!\n\n"
        )
        return recommendations

    metric_recommendations = {
        "contextual_precision": "Consider improving your reranking model or adjusting reranking parameters to better prioritize relevant documents.",
        "contextual_recall": "Review your embedding model choice and vector search parameters. Consider domain-specific embeddings.",
        "contextual_relevancy": "Optimize chunk size and top-K retrieval parameters to reduce noise in retrieved contexts.",
        "answer_relevancy": "Review your prompt template and LLM parameters to improve response relevance to the input query.",
        "faithfulness": "Strengthen hallucination detection and ensure the LLM stays grounded in the provided context.",
    }

    for metric, score in low_performing_metrics:
        metric_name = metric.replace("_", " ").title()
        recommendations += f"**{metric_name}** (Score: {score:.3f}): {metric_recommendations[metric]}\n\n"

    return recommendations


def generate_full_report(results: Dict[str, Any]) -> str:
    """Generate complete report for GitHub Actions comment."""
    report = "# RAG System Evaluation Report\n\n"

    # Add summary
    report += generate_summary_table(results)

    # Add detailed results
    report += generate_detailed_results_table(results)

    # Add failure analysis
    report += generate_failure_analysis(results)

    # Add recommendations
    report += generate_recommendations(results)

    report += "---\n"
    report += "*Generated by DeepEval automated testing pipeline*\n"

    return report


def save_report_to_file(
    results: Dict[str, Any], output_path: str = "test_report.md"
) -> str:
    """Save the report to a markdown file and return the content."""
    report_content = generate_full_report(results)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report_content)

    return report_content


def main():
    """Main function to run evaluation and generate report."""
    print("Running comprehensive DeepEval evaluation...")

    try:
        results = run_comprehensive_evaluation()
        report_content = save_report_to_file(results)

        print("Evaluation completed successfully!")
        print("Report saved to test_report.md")
        print("\nSummary:")
        print(f"Total Tests: {results['total_tests']}")
        print(f"Passed: {results['passed_tests']}")
        print(f"Failed: {results['failed_tests']}")

        return report_content

    except Exception as e:
        error_report = f"# RAG System Evaluation Report\n\n## Error\n\nEvaluation failed with error: {str(e)}\n\n"
        with open("test_report.md", "w", encoding="utf-8") as f:
            f.write(error_report)
        print(f"Evaluation failed: {str(e)}")
        return error_report


if __name__ == "__main__":
    main()
