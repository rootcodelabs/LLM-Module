How test_dataset.json Works in DeepEval Testing
Dataset Structure
Each test case in test_dataset.json contains:
```bash
{
    "input": "Question/query from user",
    "expected_output": "What the ideal response should be", 
    "retrieval_context": ["Relevant context that should be retrieved"],
    "category": "topic category (pension_information, family_benefits, etc.)",
    "language": "en/et/ru"
}
```

## Evaluation Flow

1. Test Data Loading
- Each test method loads the entire test_dataset.json
- Uses @pytest.mark.parametrize to run each test item as a separate test case
- This means if you have 15 items in the dataset, you get 15 individual test runs per metric

2. Test Case Creation (create_test_case method)
For each dataset item:
```python
# Takes the "input" field from dataset
question = data_item["input"]  # e.g., "How flexible will pensions become in 2021?"

# Calls the system (currently dummy orchestrator)
result = process_query(question=question, provider="anthropic", include_contexts=True)
# Returns: {"response": "AI generated answer", "retrieval_context": ["retrieved docs"]}

# Creates DeepEval test case with:
LLMTestCase(
    input=data_item["input"],                    # Original question
    actual_output=result["response"],            # AI's actual response
    expected_output=data_item["expected_output"], # Ideal response from dataset
    retrieval_context=result["retrieval_context"] # Contexts AI actually retrieved
)
```

3. DeepEval Metrics Evaluation
Each metric compares different aspects:

- Contextual Precision: How well the retrieval system ranks relevant contexts higher
- Contextual Recall: Whether all relevant information was retrieved
- Contextual Relevancy: How relevant the retrieved contexts are to the question
- Answer Relevancy: How relevant the AI's response is to the original question
- Faithfulness: Whether the AI's response is faithful to the retrieved contexts

Key Insights
**The Dataset's Two Roles:**
1. Ground Truth for Answers: expected_output provides the "gold standard" answer
2. Ground Truth for Context: retrieval_context shows what contexts SHOULD be retrieved

**What Gets Compared:**
    - AI's Response vs Expected Response (Answer quality)
    - AI's Retrieved Contexts vs Expected Contexts (Retrieval quality)
    - AI's Response vs AI's Retrieved Contexts (Faithfulness)

**Multi-language Coverage:**
    - Tests Estonian (et), Russian (ru), and English (en) capabilities
    - Covers multiple domains: pensions, family benefits, train services, health cooperation

**Important Note for API Migration:**
When we switch from ```dummy_llm_orchestrator``` to the real API:

1. The dataset stays the same - it's the ground truth
2. Only the system being tested changes - from mock to real API
3. The API must return both:
    - response (the AI's answer)
    - retrieval_context (what contexts were actually retrieved)