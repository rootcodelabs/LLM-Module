export interface LLMConnectionData {
  llmConnectionId: number | string;
  llmConnectionName?: string;
  datasetVersion?: string;
  platform?: string;
  model?: boolean;
  isActive?: boolean;
  deploymentEnv?: string;
  budgetStatus?: string;
}

export const mockLLMConnections: LLMConnectionData[] = [
  {
    llmConnectionId: 1,
    llmConnectionName: "OpenAI GPT-4 Connection",
    datasetVersion: "v2.1.0",
    platform: "OpenAI",
    model: true,
    isActive: true,
    deploymentEnv: "Production",
    budgetStatus: "within"
  },
  {
    llmConnectionId: 2,
    llmConnectionName: "Claude 3 Sonnet Integration",
    datasetVersion: "v1.8.5",
    platform: "Anthropic",
    model: true,
    isActive: false,
    deploymentEnv: "Staging",
    budgetStatus: "close"
  },
  {
    llmConnectionId: 3,
    llmConnectionName: "Azure OpenAI Service",
    datasetVersion: "v2.0.3",
    platform: "Microsoft Azure",
    model: true,
    isActive: true,
    deploymentEnv: "Production",
    budgetStatus: "over"
  },
  {
    llmConnectionId: "conn-4",
    llmConnectionName: "Local Llama 2 Model",
    datasetVersion: "v1.5.2",
    platform: "Local",
    model: false,
    isActive: true,
    deploymentEnv: "Development",
    budgetStatus: "within"
  },
  {
    llmConnectionId: 5,
    llmConnectionName: "Google PaLM API",
    datasetVersion: "v1.9.1",
    platform: "Google Cloud",
    model: true,
    isActive: false,
    deploymentEnv: "Testing",
    budgetStatus: "within"
  },
  {
    llmConnectionId: 6,
    llmConnectionName: "Cohere Command Model",
    datasetVersion: "v2.2.0",
    platform: "Cohere",
    model: true,
    isActive: true,
    deploymentEnv: "Production",
    budgetStatus: "close"
  },
  {
    llmConnectionId: "conn-7",
    llmConnectionName: "Hugging Face Transformers",
    datasetVersion: "v1.7.8",
    platform: "Hugging Face",
    model: false,
    isActive: false,
    deploymentEnv: "Development",
    budgetStatus: "within"
  },
  {
    llmConnectionId: 8,
    llmConnectionName: "AWS Bedrock Claude",
    datasetVersion: "v2.0.7",
    platform: "AWS Bedrock",
    model: true,
    isActive: true,
    deploymentEnv: "Production",
    budgetStatus: "over"
  }
];

// Example usage with a single connection
export const singleMockConnection: LLMConnectionData = {
  llmConnectionId: "demo-1",
  llmConnectionName: "Demo LLM Connection",
  datasetVersion: "v1.0.0",
  platform: "Demo Platform",
  model: true,
  isActive: true,
  deploymentEnv: "Demo",
  budgetStatus: "within"
};
