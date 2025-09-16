import { useState, useEffect } from 'react';
import { useNavigate, useSearchParams, Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useToast } from 'hooks/useToast';
import BackArrowButton from 'assets/BackArrowButton';
import LLMConnectionForm, { LLMConnectionFormData } from 'components/molecules/LLMConnectionForm';
import { getLLMConnection, updateLLMConnection, deleteLLMConnection } from 'services/llmConnections';
import { llmConnectionsQueryKeys } from 'utils/queryKeys';
import { ToastTypes } from 'enums/commonEnums';
import CircularSpinner from 'components/molecules/CircularSpinner/CircularSpinner';

const ViewLLMConnection = () => {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const toast = useToast();
  const queryClient = useQueryClient();
  const [searchParams] = useSearchParams();
  const isEditing = true;
  const connectionId = searchParams.get('id');

  // Fetch connection data
  const { data: connectionData, isLoading, error } = useQuery({
    queryKey: llmConnectionsQueryKeys.detail(connectionId!),
    queryFn: () => getLLMConnection(connectionId!),
    enabled: !!connectionId,
  });

  // Update mutation
  const updateConnectionMutation = useMutation({
    mutationFn: (data: LLMConnectionFormData) => updateLLMConnection(connectionId!, data),
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: llmConnectionsQueryKeys.all()
      });

      toast.open({
        type: ToastTypes.SUCCESS,
        title: 'Success',
        message: 'LLM connection updated successfully!',
      });
      navigate('/llm-connections');
    },
    onError: (error: any) => {
      console.error('Error updating LLM connection:', error);
      toast.open({
        type: ToastTypes.ERROR,
        title: 'Error',
        message: error?.message || 'Failed to update LLM connection. Please try again.',
      });
    },
  });

  // Delete mutation
  const deleteConnectionMutation = useMutation({
    mutationFn: () => deleteLLMConnection(connectionId!),
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: llmConnectionsQueryKeys.all()
      });

      toast.open({
        type: ToastTypes.SUCCESS,
        title: 'Success',
        message: 'LLM connection deleted successfully!',
      });

      navigate('/llm-connections');
    },
    onError: (error: any) => {
      console.error('Error deleting LLM connection:', error);
      toast.open({
        type: ToastTypes.ERROR,
        title: 'Error',
        message: error?.message || 'Failed to delete LLM connection. Please try again.',
      });
    },
  });

  const handleSubmit = async (data: LLMConnectionFormData) => {
    updateConnectionMutation.mutate(data);
  };

  const handleCancel = () => {
    navigate('/llm-connections');
  };



  const handleDelete = () => {
    if (window.confirm('Are you sure you want to delete this LLM connection?')) {
      deleteConnectionMutation.mutate();
    }
  };

  if (isLoading) {
    return (
      <div className="container">
        <CircularSpinner />
      </div>
    );
  }

  if (error || !connectionData) {
    return (
      <div className="container">
        <div className="title_container">
          <div className="flex-grid">
            <Link to={'/llm-connections'}>
              <BackArrowButton />
            </Link>
            <div className="title">Connection Not Found</div>
          </div>
        </div>
        <p>The requested LLM connection could not be found.</p>
      </div>
    );
  }

  // Convert connection data to form format
  const formData: LLMConnectionFormData = {
    llmPlatform: connectionData.llmPlatform,
    llmModel: connectionData.llmModel,
    embeddingModelPlatform: connectionData.embeddingPlatform,
    embeddingModel: connectionData.embeddingModel,
    llmApiKey: '', // Don't show API keys
    embeddingApiKey: '', // Don't show API keys
    monthlyBudget: connectionData.monthlyBudget.toString(),
    deploymentEnvironment: connectionData.environment,
  };

  return (
    <div className="container">
      <div className="title_container">
        <div className="flex-grid">
          <Link to={'/llm-connections'}>
            <BackArrowButton />
          </Link>
          <div className="title">
            {isEditing ? 'Edit LLM Connection' : ''}
            {/* {connectionData?.llmConnectionName && ` ${connectionData.llmConnectionName}`} */}
          </div>
        </div>

      </div>

      <LLMConnectionForm
        onSubmit={handleSubmit}
        onCancel={handleCancel}
        onDelete={handleDelete}
        defaultValues={formData}
        isEditing={isEditing}
      />
    </div>
  );
};

export default ViewLLMConnection;