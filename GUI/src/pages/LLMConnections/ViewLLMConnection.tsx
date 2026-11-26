import { useState, useEffect } from 'react';
import { useNavigate, useSearchParams, Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useDialog } from 'hooks/useDialog';
import { Button } from 'components';
import { ButtonAppearanceTypes } from 'enums/commonEnums';
import BackArrowButton from 'assets/BackArrowButton';
import LLMConnectionForm, { LLMConnectionFormData } from 'components/molecules/LLMConnectionForm';
import { getLLMConnection, updateLLMConnection, deleteLLMConnection } from 'services/llmConnections';
import { llmConnectionsQueryKeys } from 'utils/queryKeys';
import CircularSpinner from 'components/molecules/CircularSpinner/CircularSpinner';

const ViewLLMConnection = () => {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const { open: openDialog, close: closeDialog } = useDialog();
  const queryClient = useQueryClient();
  const [searchParams] = useSearchParams();
  const isEditing = true;
  const connectionId = searchParams.get('id');

  // Delete mutation
  const deleteConnectionMutation = useMutation({
    mutationFn: () => deleteLLMConnection(connectionId!),
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: llmConnectionsQueryKeys.all()
      });

      navigate('/llm-connections');

      openDialog({
        title: t('llmConnectionForm.viewConnection.deleteSuccessTitle'),
        content: <p>{t('llmConnectionForm.viewConnection.deleteSuccessMessage')}</p>,
        footer: (
          <Button
            appearance={ButtonAppearanceTypes.PRIMARY}
            onClick={() => {
              closeDialog();
            }}
          >
            {t('llmConnectionForm.viewConnection.viewConnectionsButton')}
          </Button>
        ),
      });
    },
    onError: (error: any) => {
      console.error('Error deleting LLM connection:', error);
      openDialog({
        title: t('llmConnectionForm.viewConnection.deleteErrorTitle'),
        content: <p>{t('llmConnectionForm.viewConnection.deleteErrorMessage')}</p>,
        footer: (
          <Button
            appearance={ButtonAppearanceTypes.PRIMARY}
            onClick={closeDialog}
          >
            {t('llmConnectionForm.viewConnection.goBackButton')}
          </Button>
        ),
      });
    },
  });

  // Fetch connection data
  const { data: connectionData, isLoading, error } = useQuery({
    queryKey: llmConnectionsQueryKeys.detail(connectionId!),
    queryFn: () => getLLMConnection(connectionId!),
    enabled: !!connectionId && !deleteConnectionMutation.isLoading,
  });

  // Update mutation
  const updateConnectionMutation = useMutation({
    mutationFn: (data: LLMConnectionFormData) => updateLLMConnection(connectionId!, data),
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: llmConnectionsQueryKeys.all()
      });

      openDialog({
        title: t('llmConnectionForm.viewConnection.updateSuccessTitle'),
        content: <p>{t('llmConnectionForm.viewConnection.updateSuccessMessage')}</p>,
        footer: (
          <Button
            appearance={ButtonAppearanceTypes.PRIMARY}
            onClick={() => {
              closeDialog();
              navigate('/llm-connections');
            }}
          >
            {t('llmConnectionForm.viewConnection.viewConnectionsButton')}
          </Button>
        ),
      });
    },
    onError: (error: any) => {
      console.error('Error updating LLM connection:', error);
      openDialog({
        title: t('llmConnectionForm.viewConnection.updateErrorTitle'),
        content: <p>{t('llmConnectionForm.viewConnection.updateErrorMessage')}</p>,
        footer: (
          <Button
            appearance={ButtonAppearanceTypes.PRIMARY}
            onClick={closeDialog}
          >
            {t('llmConnectionForm.viewConnection.goBackButton')}
          </Button>
        ),
      });
    },
  });


  const handleSubmit = async (data: LLMConnectionFormData) => {
    const isCurrentlyProduction = connectionData?.environment === 'production';
    const isChangingToTesting = data.deploymentEnvironment === 'testing';
    
    if (isCurrentlyProduction && isChangingToTesting) {
      openDialog({
        title: t('llmConnectionForm.viewConnection.confirmEnvironmentChangeTitle'),
        content: (
          <div>
            <p>{t('llmConnectionForm.viewConnection.confirmEnvironmentChangeMessage')}</p>
            <p>{t('llmConnectionForm.viewConnection.confirmEnvironmentChangeWarning')}</p>
          </div>
        ),
        footer: (
          <div className="button-wrapper">
            <Button
              appearance={ButtonAppearanceTypes.SECONDARY}
              onClick={closeDialog}
            >
              {t('llmConnectionForm.viewConnection.cancelButton')}
            </Button>
            <Button
              appearance={ButtonAppearanceTypes.PRIMARY}
              onClick={() => {
                closeDialog();
                updateConnectionMutation.mutate(data);
              }}
              showLoadingIcon={updateConnectionMutation.isLoading}
            >
              {t('llmConnectionForm.viewConnection.confirmChangeButton')}
            </Button>
          </div>
        ),
      });
    } else {
      updateConnectionMutation.mutate(data);
    }
  };

  const handleCancel = () => {
    navigate('/llm-connections');
  };



  const handleDelete = () => {
    const isProductionConnection = connectionData?.environment === 'production';
    
    if (isProductionConnection) {
      openDialog({
        title: t('llmConnectionForm.viewConnection.cannotDeleteProductionTitle'),
        content: (
          <div>
            <p>{t('llmConnectionForm.viewConnection.cannotDeleteProductionMessage')}</p>
            <p>{t('llmConnectionForm.viewConnection.cannotDeleteProductionInstructions')}</p>
          </div>
        ),
        footer: (
          <Button
            appearance={ButtonAppearanceTypes.PRIMARY}
            onClick={closeDialog}
          >
            {t('llmConnectionForm.viewConnection.okButton')}
          </Button>
        ),
      });
    } else {
      openDialog({
        title: t('llmConnectionForm.viewConnection.confirmDeleteTitle'),
        content: <p>{t('llmConnectionForm.viewConnection.confirmDeleteMessage')}</p>,
        footer: (
          <div className="button-wrapper">
            <Button
              appearance={ButtonAppearanceTypes.SECONDARY}
              onClick={closeDialog}
            >
              {t('llmConnectionForm.viewConnection.cancelButton')}
            </Button>
            <Button
              appearance={ButtonAppearanceTypes.ERROR}
              onClick={() => {
                deleteConnectionMutation.mutate();
              }}
              showLoadingIcon={deleteConnectionMutation.isLoading}
            >
              {t('llmConnectionForm.viewConnection.deleteButton')}
            </Button>
          </div>
        ),
      });
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
            <div className="title">{t('llmConnectionForm.viewConnection.connectionNotFoundTitle')}</div>
          </div>
        </div>
        <p>{t('llmConnectionForm.viewConnection.connectionNotFoundMessage')}</p>
      </div>
    );
  }

  // Convert connection data to form format
  const formData: LLMConnectionFormData = {
    connectionName: connectionData.connectionName,
    llmPlatform: connectionData.llmPlatform,
    llmModel: connectionData.llmModel,
    embeddingModelPlatform: connectionData.embeddingPlatform,
    embeddingModel: connectionData.embeddingModel,
    monthlyBudget: connectionData.monthlyBudget.toString(),
    warnBudget: connectionData.warnBudgetThreshold.toString(),
    stopBudget: connectionData.disconnectOnBudgetExceed ? connectionData.stopBudgetThreshold.toString() : '0',
    disconnectOnBudgetExceed: connectionData.disconnectOnBudgetExceed,
    deploymentEnvironment: connectionData.environment,
    // Azure credentials (don't show sensitive data, but include structure)
    deploymentName: connectionData.deploymentName || '',
    targetUri: connectionData.targetUri || '',
    apiKey: connectionData.apiKey || '', // Don't show API keys
    // AWS Bedrock credentials (don't show sensitive data, but include structure)
    secretKey: connectionData.secretKey || '', // Don't show API keys
    accessKey: connectionData.accessKey || '', // Don't show API keys
    // Embedding model credentials (don't show sensitive data, but include structure)
    embeddingModelApiKey: connectionData.embeddingModelApiKey || '', // Don't show API keys
    // Embedding AWS Bedrock credentials
    embeddingAccessKey: connectionData.embeddingAccessKey || '',
    embeddingSecretKey: connectionData.embeddingSecretKey || '',
    // Embedding Azure credentials
    embeddingDeploymentName: connectionData.embeddingDeploymentName || '',
    embeddingTargetUri: connectionData.embeddingTargetUri || '',
    embeddingAzureApiKey: connectionData.embeddingAzureApiKey || '',
  };

  return (
    <div className="container">
      <div className="title_container">
        <div className="flex-grid">
          <Link to={'/llm-connections'}>
            <BackArrowButton />
          </Link>
          <div className="title">
            {connectionData?.connectionName && ` ${connectionData.connectionName}`}
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