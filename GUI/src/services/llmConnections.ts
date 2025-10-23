import apiDev from './api-dev';
import { llmConnectionsEndpoints, vaultEndpoints } from 'utils/endpoints';
import { removeCommasFromNumber } from 'utils/commonUtils';
import { maskSensitiveKey } from 'utils/llmConnectionsUtils';

export interface LLMConnection {
  id: number;
  connectionName: string;
  llmPlatform: string;
  llmModel: string;
  embeddingPlatform: string;
  embeddingModel: string;
  monthlyBudget: number;
  warnBudgetThreshold: number;
  stopBudgetThreshold: number;
  disconnectOnBudgetExceed: boolean;
  environment: string;
  connectionStatus: 'active' | 'inactive';
  createdAt: string;
  updatedAt: string;
  totalPages?: number;
  budgetStatus: 'within_budget' | 'over_budget' | 'close_to_exceed';
  usedBudget?: number;
  // Azure credentials
  deploymentName?: string;
  targetUri?: string;
  apiKey?: string;
  // AWS Bedrock credentials
  secretKey?: string;
  accessKey?: string;
  // Embedding model credentials
  embeddingModelApiKey?: string;
}

export interface LLMConnectionsResponse {
  data: LLMConnection[];

}

export interface BudgetStatus {
  used_budget_percentage: number;
  exceeded_stop_budget: boolean;
  exceeded_warn_budget: boolean;
  data: {
    id: number;
    connectionName: string;
    usedBudget: number;
    monthlyBudget: number;
    warnBudgetThreshold: number;
    stopBudgetThreshold: number;
    environment: string;
    connectionStatus: string;
    createdAt: string;
    llmPlatform: string;
    llmModel: string;
    embeddingPlatform: string;
    embeddingModel: string;
  }
}

export interface LLMConnectionFilters {
  pageNumber?: number;
  pageSize?: number;
  sortBy?: string;
  sortOrder?: string;
  llmPlatform?: string;
  llmModel?: string;
  embeddingPlatform?: string;
  environment?: string;
  status?: string;
}

export interface ProductionConnectionFilters {
  llmPlatform?: string;
  llmModel?: string;
  embeddingPlatform?: string;
  embeddingModel?: string;
  connectionStatus?: string;
  sortBy?: string;
  sortOrder?: string;
}
export interface LegacyLLMConnectionFilters {
  page: number;
  pageSize: number;
  sorting?: string;
  llmPlatform?: string;
  embeddingPlatform?: string;
  environment?: string;
  status?: string;
}
export interface LLMConnectionFormData {
  connectionName: string;
  llmPlatform: string;
  llmModel: string;
  embeddingModelPlatform: string;
  embeddingModel: string;
  monthlyBudget: string;
  warnBudget: string;
  stopBudget: string;
  disconnectOnBudgetExceed: boolean;
  deploymentEnvironment: string;
  // Azure credentials
  deploymentName?: string;
  targetUri?: string;
  apiKey?: string;
  // AWS Bedrock credentials
  secretKey?: string;
  accessKey?: string;
  // Embedding model credentials
  embeddingModelApiKey?: string;
}

// Vault secret service functions
async function createVaultSecret(connectionId: string, connectionData: LLMConnectionFormData): Promise<void> {
 
  const payload = {
    connectionId,
    llmPlatform: connectionData.llmPlatform,
    llmModel: connectionData.llmModel,
    embeddingModel: connectionData.embeddingModel,
    embeddingPlatform: connectionData.embeddingModelPlatform,
    deploymentEnvironment: connectionData.deploymentEnvironment.toLowerCase(),
    // AWS credentials
    ...(connectionData.llmPlatform === 'aws' && {
      secretKey: connectionData.secretKey || '',
      accessKey: connectionData.accessKey || '',
    }),
    // Azure credentials  
    ...(connectionData.llmPlatform === 'azure' && {
      deploymentName: connectionData.deploymentName || '',
      targetUrl: connectionData.targetUri || '',
      apiKey: connectionData.apiKey || '',
    }),
    embeddingModelApiKey: connectionData.embeddingModelApiKey || '',
  };

  await apiDev.post(vaultEndpoints.CREATE_VAULT_SECRET(), payload);
}

async function deleteVaultSecret(connectionId: string, connectionData: Partial<LLMConnectionFormData>): Promise<void> {
  
  const payload = {
    connectionId,
    llmPlatform: connectionData.llmPlatform || '',
    llmModel: connectionData.llmModel || '',
    embeddingModel: connectionData.embeddingModel || '', 
    embeddingPlatform: connectionData.embeddingModelPlatform || '',
    deploymentEnvironment: connectionData.deploymentEnvironment?.toLowerCase() || '',
  };

  await apiDev.post(vaultEndpoints.DELETE_VAULT_SECRET(), payload);
}

export async function fetchLLMConnectionsPaginated(filters: LLMConnectionFilters): Promise<LLMConnection[]> {
  const queryParams = new URLSearchParams();

  if (filters.pageNumber) queryParams.append('pageNumber', filters.pageNumber.toString());
  if (filters.pageSize) queryParams.append('pageSize', filters.pageSize.toString());
  if (filters.sortBy) queryParams.append('sortBy', filters.sortBy);
  if (filters.sortOrder) queryParams.append('sortOrder', filters.sortOrder);
  if (filters.llmPlatform) queryParams.append('llmPlatform', filters.llmPlatform);
  if (filters.llmModel) queryParams.append('llmModel', filters.llmModel);
  if (filters.environment) queryParams.append('environment', filters.environment);

  const url = `${llmConnectionsEndpoints.FETCH_LLM_CONNECTIONS_PAGINATED()}?${queryParams.toString()}`;
  const { data } = await apiDev.get(url);
  return data?.response;
}

export async function getLLMConnection(id: string | number): Promise<LLMConnection> {
  const { data } = await apiDev.post(llmConnectionsEndpoints.GET_LLM_CONNECTION(), {
    connection_id: id,
  });
  return data?.response;
}

export async function getProductionConnection(filters?: ProductionConnectionFilters): Promise<LLMConnection | null> {
  const queryParams = new URLSearchParams();

  if (filters?.llmPlatform) queryParams.append('llmPlatform', filters.llmPlatform);
  if (filters?.llmModel) queryParams.append('llmModel', filters.llmModel);
  if (filters?.embeddingPlatform) queryParams.append('embeddingPlatform', filters.embeddingPlatform);
  if (filters?.embeddingModel) queryParams.append('embeddingModel', filters.embeddingModel);
  if (filters?.connectionStatus) queryParams.append('connectionStatus', filters.connectionStatus);
  if (filters?.sortBy) queryParams.append('sortBy', filters.sortBy);
  if (filters?.sortOrder) queryParams.append('sortOrder', filters.sortOrder);

  const url = queryParams.toString() 
    ? `${llmConnectionsEndpoints.GET_PRODUCTION_CONNECTION()}?${queryParams.toString()}`
    : llmConnectionsEndpoints.GET_PRODUCTION_CONNECTION();
    
  const { data } = await apiDev.get(url);
  return data?.response?.[0] || null;
}


export async function createLLMConnection(connectionData: LLMConnectionFormData): Promise<LLMConnection> {
  const { data } = await apiDev.post(llmConnectionsEndpoints.CREATE_LLM_CONNECTION(), {
    connection_name: connectionData.connectionName,
    llm_platform: connectionData.llmPlatform,
    llm_model: connectionData.llmModel,
    embedding_platform: connectionData.embeddingModelPlatform,
    embedding_model: connectionData.embeddingModel,
    monthly_budget: parseFloat(removeCommasFromNumber(connectionData.monthlyBudget)),
    warn_budget_threshold: parseInt(connectionData.warnBudget),
    stop_budget_threshold: connectionData.disconnectOnBudgetExceed ? parseInt(connectionData.stopBudget) : 0,
    disconnect_on_budget_exceed: connectionData.disconnectOnBudgetExceed,
    deployment_environment: connectionData.deploymentEnvironment.toLowerCase(),
    // Azure credentials
    deployment_name: connectionData.deploymentName || "",
    target_uri: connectionData.targetUri || "",
    api_key: maskSensitiveKey(connectionData.apiKey) || "",
    // AWS Bedrock credentials
    secret_key: maskSensitiveKey(connectionData.secretKey) || "",
    access_key: maskSensitiveKey(connectionData.accessKey) || "",
    // Embedding model credentials
    embedding_model_api_key: maskSensitiveKey(connectionData.embeddingModelApiKey) || "",
  });
  
  const connection = data?.response;
  
  // After successful database creation, store secrets in vault
  if (connection && connection.id) {
    try {
      await createVaultSecret(connection.id.toString(), connectionData);
    } catch (vaultError) {
      console.error('Failed to store secrets in vault:', vaultError);
      // Note: We don't throw here to avoid breaking the connection creation flow
      // The connection is already created in the database
    }
  }
  
  return connection;
}

export async function updateLLMConnection(
  id: string | number,
  connectionData: LLMConnectionFormData
): Promise<LLMConnection> {
  const { data } = await apiDev.post(llmConnectionsEndpoints.UPDATE_LLM_CONNECTION(), {
    connection_id: id,
    connection_name: connectionData.connectionName,
    llm_platform: connectionData.llmPlatform,
    llm_model: connectionData.llmModel,
    embedding_platform: connectionData.embeddingModelPlatform,
    embedding_model: connectionData.embeddingModel,
    monthly_budget: parseFloat(removeCommasFromNumber(connectionData.monthlyBudget)),
    warn_budget_threshold: parseInt(connectionData.warnBudget),
    stop_budget_threshold: connectionData.disconnectOnBudgetExceed ? parseInt(connectionData.stopBudget) : 0,
    disconnect_on_budget_exceed: connectionData.disconnectOnBudgetExceed,
    deployment_environment: connectionData.deploymentEnvironment.toLowerCase(),
    // Azure credentials
    deployment_name: connectionData.deploymentName || "",
    target_uri: connectionData.targetUri || "",
    api_key: maskSensitiveKey(connectionData.apiKey) || "",
    // AWS Bedrock credentials
    secret_key: maskSensitiveKey(connectionData.secretKey) || "",
    access_key: maskSensitiveKey(connectionData.accessKey) || "",
    // Embedding model credentials
    embedding_model_api_key: maskSensitiveKey(connectionData.embeddingModelApiKey) || "",
  });
  
  const connection = data?.response;
  
  // After successful database update, update secrets in vault
  if (connection) {
    try {
      await createVaultSecret(id.toString(), connectionData);
    } catch (vaultError) {
      console.error('Failed to update secrets in vault:', vaultError);
      // Note: We don't throw here to avoid breaking the connection update flow
      // The connection is already updated in the database
    }
  }
  
  return connection;
}

export async function deleteLLMConnection(id: string | number): Promise<void> {
  // First, get the connection data to extract vault deletion parameters
  let connectionToDelete: LLMConnection | null = null;
  try {
    connectionToDelete = await getLLMConnection(id);
  } catch (error) {
    console.error('Failed to get connection data before deletion:', error);
  }
  
  // Delete from database
  await apiDev.post(llmConnectionsEndpoints.DELETE_LLM_CONNECTION(), {
    connection_id: id,
  });
  
  // After successful database deletion, delete secrets from vault
  if (connectionToDelete) {
    try {
      await deleteVaultSecret(id.toString(), {
        llmPlatform: connectionToDelete.llmPlatform,
        llmModel: connectionToDelete.llmModel,
        embeddingModel: connectionToDelete.embeddingModel,
        embeddingModelPlatform: connectionToDelete.embeddingPlatform,
        deploymentEnvironment: connectionToDelete.environment,
      });
    } catch (vaultError) {
      console.error('Failed to delete secrets from vault:', vaultError);
      // Note: We don't throw here as the database deletion has already succeeded
      // This is logged for monitoring/debugging purposes
    }
  }
}

export async function checkBudgetStatus(): Promise<BudgetStatus | null> {
  try {
    const { data } = await apiDev.get(llmConnectionsEndpoints.CHECK_BUDGET_STATUS());
    return data?.response as BudgetStatus;
  } catch (error) {
    // Return null if no production connection found (404) or other errors
    return null;
  }
}
  
export async function updateLLMConnectionStatus(
  id: string | number, 
  status: 'active' | 'inactive'
): Promise<LLMConnection> {
  const { data } = await apiDev.post(llmConnectionsEndpoints.UPDATE_LLM_CONNECTION_STATUS(), {
    connection_id: id,
    connection_status: status,
  });
  return data?.response;
}
