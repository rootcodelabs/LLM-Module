import apiDev from './api-dev';
import { inferenceEndpoints } from 'utils/endpoints';

export interface InferenceRequest {
  llmConnectionId: number;
  message: string;
}

export interface InferenceResponse {
  response: {
    chatId: number;
    llmServiceActive: boolean;
    questionOutOfLlmScope: boolean;
    content: string;
  };
}

export async function viewInferenceResult(request: InferenceRequest): Promise<InferenceResponse> {
  const { data } = await apiDev.post(inferenceEndpoints.VIEW_TEST_INFERENCE_RESULT(), {
    connectionId: request.llmConnectionId,
    message: request.message,
  });
  return data;
}
