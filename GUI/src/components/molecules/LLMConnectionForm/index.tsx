import React, { useEffect, useState } from 'react';
import { useForm, Controller } from 'react-hook-form';
import { useTranslation } from 'react-i18next';
import { useQuery } from '@tanstack/react-query';
import FormInput from 'components/FormElements/FormInput';
import FormSelect from 'components/FormElements/FormSelect';
import Button from 'components/Button';
import Track from 'components/Track';
import { 
  getLLMPlatforms, 
  getLLMModels, 
  getEmbeddingPlatforms, 
  getEmbeddingModels,
  PlatformOption,
  ModelOption 
} from 'services/llmConfigs';
import './LLMConnectionForm.scss';

export type LLMConnectionFormData = {
  llmPlatform: string;
  llmModel: string;
  embeddingModelPlatform: string;
  embeddingModel: string;
  monthlyBudget: string;
  deploymentEnvironment: string;
  // AWS Bedrock credentials
  accessKey?: string;
  secretKey?: string;
  // Azure credentials
  deploymentName?: string;
  targetUri?: string;
  apiKey?: string;
  // Embedding model credentials
  embeddingModelApiKey?: string;
};

type LLMConnectionFormProps = {
  onSubmit: (data: LLMConnectionFormData) => void;
  onCancel: () => void;
  onDelete: () => void;
  defaultValues?: Partial<LLMConnectionFormData>;
  isEditing?: boolean;
  readOnly?: boolean;
};

const LLMConnectionForm: React.FC<LLMConnectionFormProps> = ({
  onSubmit,
  onCancel,
  onDelete,
  defaultValues,
  isEditing = false,
  readOnly = false,
}) => {
  const { t } = useTranslation();
  const {
    control,
    handleSubmit,
    watch,
    setValue,
    formState: { errors, isDirty, isValid },
  } = useForm<LLMConnectionFormData>({
    defaultValues: {
      llmPlatform: '',
      llmModel: '',
      embeddingModelPlatform: '',
      embeddingModel: '',
      embeddingModelApiKey: '',
      monthlyBudget: '',
      deploymentEnvironment: 'testing',
      // AWS Bedrock credentials
      accessKey: '',
      secretKey: '',
      // Azure credentials
      deploymentName: '',
      targetUri: '',
      apiKey: '',
      // Embedding model credentials
      ...defaultValues,
    },
    mode: 'onChange',
  });

  const selectedLLMPlatform = watch('llmPlatform');
  const selectedEmbeddingPlatform = watch('embeddingModelPlatform');

  // Fetch platform and model options from API
  const { data: llmPlatformsData = [], isLoading: llmPlatformsLoading, error: llmPlatformsError } = useQuery({
    queryKey: ['llm-platforms'],
    queryFn: getLLMPlatforms,
    retry: 2,
    staleTime: 5 * 60 * 1000, // 5 minutes
  });

  const { data: embeddingPlatformsData = [], isLoading: embeddingPlatformsLoading, error: embeddingPlatformsError } = useQuery({
    queryKey: ['embedding-platforms'],
    queryFn: getEmbeddingPlatforms,
    retry: 2,
    staleTime: 5 * 60 * 1000, // 5 minutes
  });

  const { data: llmModelsData = [], isLoading: llmModelsLoading, error: llmModelsError } = useQuery({
    queryKey: ['llm-models', selectedLLMPlatform],
    queryFn: () => getLLMModels(selectedLLMPlatform),
    enabled: !!selectedLLMPlatform,
    retry: 2,
    staleTime: 2 * 60 * 1000, // 2 minutes
  });

  const { data: embeddingModelsData = [], isLoading: embeddingModelsLoading, error: embeddingModelsError } = useQuery({
    queryKey: ['embedding-models', selectedEmbeddingPlatform],
    queryFn: () => getEmbeddingModels(selectedEmbeddingPlatform),
    enabled: !!selectedEmbeddingPlatform,
    retry: 2,
    staleTime: 2 * 60 * 1000, // 2 minutes
  });

  // Convert API data to option format
  const llmPlatformOptions = llmPlatformsData?.map((platform: PlatformOption) => ({
    label: platform.label,
    value: platform.value,
  }));

  const embeddingPlatformOptions = embeddingPlatformsData?.map((platform: PlatformOption) => ({
    label: platform.label,
    value: platform.value,
  }));

  const llmModelOptions = llmModelsData?.map((model: ModelOption) => ({
    label: model.label,
    value: model.value,
  }));

  const embeddingModelOptions = embeddingModelsData?.map((model: ModelOption) => ({
    label: model.label,
    value: model.value,
  }));

  const [replaceApiKey, setReplaceApiKey] = React.useState(false);
  const [replaceSecretKey, setReplaceSecretKey] = React.useState(false);
  const [replaceAccessKey, setReplaceAccessKey] = React.useState(false);
  const [replaceEmbeddingModelApiKey, setReplaceEmbeddingModelApiKey] = React.useState(false);

  // State to track if API key fields should be in replace mode (readonly with replace button)
  const [apiKeyReplaceMode, setApiKeyReplaceMode] = React.useState(isEditing);
  const [secretKeyReplaceMode, setSecretKeyReplaceMode] = React.useState(isEditing);
  const [accessKeyReplaceMode, setAccessKeyReplaceMode] = React.useState(isEditing);
  const [embeddingApiKeyReplaceMode, setEmbeddingApiKeyReplaceMode] = React.useState(isEditing);

  const resetLLMCredentialFields = () => {
    setValue('accessKey', '');
    setValue('secretKey', '');
    setValue('deploymentName', '');
    setValue('targetUri', '');
    setValue('apiKey', '');
    setValue('llmModel', '');
    
    // Reset replace mode states when platform changes
    setApiKeyReplaceMode(false);
    setSecretKeyReplaceMode(false);
    setAccessKeyReplaceMode(false);
  };

   const resetEmbeddingModelCredentialFields = () => {
    setValue('embeddingModelApiKey', '');
    setValue('embeddingModel', '');
    
    // Reset replace mode state when platform changes
    setEmbeddingApiKeyReplaceMode(false);
  };
  // Model options based on selected platform
  const getLLMModelOptions = () => {
    return llmModelOptions;
  };

  const getEmbeddingModelOptions = () => {
    return embeddingModelOptions;
  };

  const deploymentEnvironments = [
    { label: 'Testing', value: 'testing' },
    { label: 'Production', value: 'production' },
  ];

  const renderPlatformSpecificFields = () => {
    switch (selectedLLMPlatform) {
      case 'aws':
        return (
          <>
            <div className="form-row">
              <p className='form-label'>Access Key</p>
              <p className='form-description'>AWS Access Key for Bedrock service</p>
              <Controller
                name="accessKey"
                control={control}
                rules={{ required: 'Access Key is required for AWS Bedrock' }}
                render={({ field }) => (
                  <FormInput
                    label=""
                    type={isEditing ? 'text' : 'password'}
                    placeholder="Enter AWS Access Key"
                    error={errors.accessKey?.message}
                    readOnly={accessKeyReplaceMode}
                    showEndButton={accessKeyReplaceMode}
                    onEndButtonClick={() => {
                      setAccessKeyReplaceMode(false);
                      setValue('accessKey', '');
                    }}
                    endButtonText="Change"
                    {...field}
                  />
                )}
              />
            </div>
            <div className="form-row">
              <p className='form-label'>Secret Key</p>
              <p className='form-description'>AWS Secret Key for Bedrock service</p>
              <Controller
                name="secretKey"
                control={control}
                rules={{ required: 'Secret Key is required for AWS Bedrock' }}
                render={({ field }) => (
                  <FormInput
                    label=""
                    type={isEditing ? 'text' : 'password'}
                    placeholder="Enter AWS Secret Key"
                    error={errors.secretKey?.message}
                    readOnly={secretKeyReplaceMode}
                    showEndButton={secretKeyReplaceMode}
                    onEndButtonClick={() => {
                      setSecretKeyReplaceMode(false);
                      setValue('secretKey', '');
                    }}
                    endButtonText="Change"
                    {...field}
                  />
                )}
              />
            </div>
          </>
        );
      case 'azure':
        return (
          <>
            <div className="form-row">
              <p className='form-label'>Deployment Name</p>
              <p className='form-description'>Azure OpenAI deployment name</p>
              <Controller
                name="deploymentName"
                control={control}
                rules={{ required: 'Deployment Name is required for Azure OpenAI' }}
                render={({ field }) => (
                  <FormInput
                    label=""
                    placeholder="Enter deployment name"
                    error={errors.deploymentName?.message}
                    {...field}
                  />
                )}
              />
            </div>
            <div className="form-row">
              <p className='form-label'>Endpoint / Target URI</p>
              <p className='form-description'>Azure OpenAI service endpoint URL</p>
              <Controller
                name="targetUri"
                control={control}
                rules={{ 
                  required: 'Endpoint is required for Azure OpenAI',
                  pattern: {
                    value: /^https?:\/\/.+/,
                    message: 'Please enter a valid URL starting with http:// or https://'
                  }
                }}
                render={({ field }) => (
                  <FormInput
                    label=""
                    placeholder="https://your-resource.openai.azure.com/"
                    error={errors.targetUri?.message}
                    {...field}
                  />
                )}
              />
            </div>
            <div className="form-row">
              <p className='form-label'>API Key</p>
              <p className='form-description'>Azure OpenAI API key</p>

              <Controller
                name="apiKey"
                control={control}
                rules={{ required: 'API Key is required for Azure OpenAI' }}
                render={({ field }) => (
                  <FormInput
                    label=""
                    type={isEditing ? 'text' : 'password'}
                    placeholder="Enter Azure OpenAI API key"
                    error={errors.apiKey?.message}
                    readOnly={apiKeyReplaceMode}
                    showEndButton={apiKeyReplaceMode}
                    onEndButtonClick={() => {
                      setApiKeyReplaceMode(false);
                      setValue('apiKey', '');
                    }}
                    endButtonText="Change"
                    {...field}
                  />
                )}
              />
            </div>
          </>
        );
      
      default:
        return (
          <div className="form-row">
            <p className='form-label'>LLM API Key</p>
            <p className='form-description'>The API key of the LLM model</p>
            <Controller
              name="apiKey"
              control={control}
              rules={{ required: 'LLM API Key is required' }}
              render={({ field }) => (
                <FormInput
                  label=""
                  type={isEditing ? 'text' : 'password'}
                  placeholder="Enter your LLM API key"
                  error={errors.apiKey?.message}
                  {...field}
                />
              )}
            />
          </div>
        );
    }
  };

  const handleFormSubmit = (data: LLMConnectionFormData) => {
    const cleanedData = {
      ...data,
      monthlyBudget: data.monthlyBudget.replace(/,/g, ''),
    };
    onSubmit(cleanedData);
  };

  return (
    <div className="llm-connection-form">
      <form onSubmit={handleSubmit(handleFormSubmit)}>
        <div className="form-section">
          <h3 className="form-section-title">LLM Configuration</h3>

          <div className="form-row">
            <p className='form-label'>LLM Platform</p>
            <p className='form-description'> Cloud / local platform in which your model is hosted</p>
            <Controller
              name="llmPlatform"
              control={control}
              rules={{ required: 'LLM Platform is required' }}
              render={({ field }) => (
                <FormSelect
                  label=""
                  options={llmPlatformOptions}
                  placeholder={
                    llmPlatformsLoading 
                      ? "Loading platforms..." 
                      : llmPlatformsError 
                        ? "Error loading platforms" 
                        : "Select LLM Platform"
                  }
                  error={errors.llmPlatform?.message || (llmPlatformsError ? "Failed to load platforms" : undefined)}
                  disabled={readOnly || llmPlatformsLoading}
                  onSelectionChange={(selected) => {
                    field.onChange(selected?.value || '');
                    resetLLMCredentialFields();
                  }}
                  defaultValue={field.value}
                  {...field}
                />
              )}
            />
          </div>

          <div className="form-row">
            <p className='form-label'>LLM Model</p>
            <p className='form-description'>The LLM model that you want to use</p>

            <Controller
              name="llmModel"
              control={control}
              rules={{ required: 'LLM Model is required' }}
              render={({ field }) => (
                <FormSelect
                  label=""
                  options={getLLMModelOptions()}
                  placeholder={
                    llmModelsLoading 
                      ? "Loading models..." 
                      : llmModelsError 
                        ? "Error loading models" 
                        : !selectedLLMPlatform 
                          ? "Select a platform first"
                          : "Select LLM Model"
                  }
                  error={errors.llmModel?.message || (llmModelsError ? "Failed to load models" : undefined)}
                  disabled={!selectedLLMPlatform || readOnly || llmModelsLoading}
                  onSelectionChange={(selected) => {
                    field.onChange(selected?.value || '');
                  }}
                  defaultValue={field.value}
                  {...field}
                />
              )}
            />
          </div>

          {/* Platform-specific fields */}
          {renderPlatformSpecificFields()}
        </div>

        <div className="form-section">
          <h3 className="form-section-title">Embedding Model Configuration</h3>

          <div className="form-row">
            <p className='form-label'>Embedding Model Platform</p>
            <p className='form-description'>This is the cloud / local platform in which your embedding model is hosted</p>

            <Controller
              name="embeddingModelPlatform"
              control={control}
              rules={{ required: 'Embedding Model Platform is required' }}
              render={({ field }) => (
                <FormSelect
                  label=""
                  options={embeddingPlatformOptions}
                  placeholder={
                    embeddingPlatformsLoading 
                      ? "Loading platforms..." 
                      : embeddingPlatformsError 
                        ? "Error loading platforms" 
                        : "Select Embedding Platform"
                  }
                  error={errors.embeddingModelPlatform?.message || (embeddingPlatformsError ? "Failed to load platforms" : undefined)}
                  disabled={embeddingPlatformsLoading}
                  onSelectionChange={(selected) => {
                    field.onChange(selected?.value || '');
                    resetEmbeddingModelCredentialFields();
                  }}
                  defaultValue={field.value}
                  {...field}
                />
              )}
            />
          </div>

          <div className="form-row">
            <p className='form-label'>Embedding Model</p>
            <p className='form-description'>The embedding model that will be used for searching your knowledge base</p>

            <Controller
              name="embeddingModel"
              control={control}
              rules={{ required: 'Embedding Model is required' }}
              render={({ field }) => (
                <FormSelect
                  label=""
                  options={getEmbeddingModelOptions()}
                  placeholder={
                    embeddingModelsLoading 
                      ? "Loading models..." 
                      : embeddingModelsError 
                        ? "Error loading models" 
                        : !selectedEmbeddingPlatform 
                          ? "Select a platform first"
                          : "Select Embedding Model"
                  }
                  error={errors.embeddingModel?.message || (embeddingModelsError ? "Failed to load models" : undefined)}
                  disabled={!selectedEmbeddingPlatform || embeddingModelsLoading}
                  onSelectionChange={(selected) => {
                    field.onChange(selected?.value || '');
                  }}
                  defaultValue={field.value}
                  {...field}
                />
              )}
            />
          </div>

          <div className="form-row">
            <p className='form-label'>Embedding Model API Key</p>
            <p className='form-description'>API key of your embedding model</p>

            <Controller
              name="embeddingModelApiKey"
              control={control}
              rules={{ required: 'Embedding API Key is required' }}
              render={({ field }) => (
                <FormInput
                  label=""
                  type={isEditing ? 'text' : 'password'}
                  placeholder="Enter your Embedding API key"
                  error={errors.embeddingModelApiKey?.message}
                  readOnly={embeddingApiKeyReplaceMode}
                  showEndButton={embeddingApiKeyReplaceMode}
                  onEndButtonClick={() => {
                    setEmbeddingApiKeyReplaceMode(false);
                    setValue('embeddingModelApiKey', '');
                  }}
                  endButtonText="Change"
                  {...field}
                />
              )}
            />
          </div>
        </div>

        <div className="form-section">
          <h3 className="form-section-title">Budget & Deployment</h3>

          <div className="form-row">
            <p className='form-label'>Monthly Budget</p>
            <p className='form-description'>Total monthly budget including embedding model and LLM model. If the LLM integration usage cost exceeds the below
              budget, the LLM will respond with an “inactive” status</p>

            <Controller
              name="monthlyBudget"
              control={control}
              rules={{
                required: 'Monthly Budget is required',
                pattern: {
                  value: /^[\d,]+(\.\d{1,2})?$/,
                  message: 'Please enter a valid budget amount'
                },
                validate: value => {
                  const numericValue = value.replace(/,/g, '');
                  return Number(numericValue) > 0 || 'Monthly Budget must be a positive number';
                }
              }}
              render={({ field }) => (
                <FormInput
                  label=""
                  placeholder="Enter monthly budget"
                  error={errors.monthlyBudget?.message}
                  {...field}
                  prefix='€'
                  formatAsNumber={true}
                />
              )}
            />
          </div>

          <div className="form-row">
            <Controller
              name="deploymentEnvironment"
              control={control}
              rules={{ required: 'Deployment Environment is required' }}
              render={({ field }) => (
                <div className="radio-group">
                  <label className="radio-group-label">Deployment Environment</label>
                  <div className="radio-options">
                    {deploymentEnvironments?.map((env) => (
                      <label key={env.value} className="radio-option">
                        <input
                          type="radio"
                          value={env.value}
                          checked={field.value === env.value}
                          onChange={(e) => field.onChange(e.target.value)}
                          className="radio-input"
                        />
                        <span className="radio-label">{env.label}</span>
                      </label>
                    ))}
                  </div>
                  {errors.deploymentEnvironment && (
                    <p className="input__inline_error">{errors.deploymentEnvironment.message}</p>
                  )}
                </div>
              )}
            />
          </div>
          <Track className="form-footer" gap={16} justify="end">
            <div className="flex-grid">
              <Button
                appearance="secondary"
                onClick={onCancel}
                type="button"
              >
                {t('global.cancel') || 'Cancel'}
              </Button>
              {isEditing && (<Button
                appearance="error"
                onClick={onDelete}
                type='button'
              >
                Delete Connection
              </Button>)}
              <Button
                type="submit"
                disabled={!isDirty || !isValid}
                appearance="primary"
              >
                {isEditing ? ('Update Connection') : ('Create Connection')}
              </Button>
            </div>
          </Track>
        </div>

      </form>
    </div>
  );
};

export default LLMConnectionForm;
