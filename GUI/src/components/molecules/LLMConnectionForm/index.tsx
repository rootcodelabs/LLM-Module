import React, { useEffect, useState } from 'react';
import { useForm, Controller } from 'react-hook-form';
import { useTranslation } from 'react-i18next';
import { useQuery } from '@tanstack/react-query';
import FormInput from 'components/FormElements/FormInput';
import FormSelect from 'components/FormElements/FormSelect';
import FormCheckbox from 'components/FormElements/FormCheckbox';
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
import { toOptions } from 'utils/commonUtils';

export type LLMConnectionFormData = {
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
  // AWS Bedrock credentials
  accessKey?: string;
  secretKey?: string;
  // Azure credentials
  deploymentName?: string;
  targetUri?: string;
  apiKey?: string;
  // Embedding model credentials
  embeddingModelApiKey?: string;
  // Embedding AWS Bedrock credentials
  embeddingAccessKey?: string;
  embeddingSecretKey?: string;
  // Embedding Azure credentials
  embeddingDeploymentName?: string;
  embeddingTargetUri?: string;
  embeddingAzureApiKey?: string;
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
      connectionName: '',
      llmPlatform: '',
      llmModel: '',
      embeddingModelPlatform: '',
      embeddingModel: '',
      monthlyBudget: '',
      warnBudget: '',
      stopBudget: '',
      disconnectOnBudgetExceed: false,
      deploymentEnvironment: '',
      // AWS Bedrock credentials
      accessKey: '',
      secretKey: '',
      // Azure credentials
      deploymentName: '',
      targetUri: '',
      apiKey: '',
      // Embedding model credentials
      embeddingModelApiKey: '',
      // Embedding AWS Bedrock credentials
      embeddingAccessKey: '',
      embeddingSecretKey: '',
      // Embedding Azure credentials
      embeddingDeploymentName: '',
      embeddingTargetUri: '',
      embeddingAzureApiKey: '',
      ...defaultValues,
    },
    mode: 'onChange',
  });

  const selectedLLMPlatform = watch('llmPlatform');
  const selectedEmbeddingPlatform = watch('embeddingModelPlatform');
  const disconnectOnBudgetExceed = watch('disconnectOnBudgetExceed');

  // Fetch platform and model options from API
  const { data: llmPlatformsData = [], isLoading: llmPlatformsLoading, error: llmPlatformsError } = useQuery({
    queryKey: ['llm-platforms'],
    queryFn: getLLMPlatforms
  });

  const { data: embeddingPlatformsData = [], isLoading: embeddingPlatformsLoading, error: embeddingPlatformsError } = useQuery({
    queryKey: ['embedding-platforms'],
    queryFn: getEmbeddingPlatforms
  });

  const { data: llmModelsData = [], isLoading: llmModelsLoading, error: llmModelsError } = useQuery({
    queryKey: ['llm-models', selectedLLMPlatform],
    queryFn: () => getLLMModels(selectedLLMPlatform),
    enabled: !!selectedLLMPlatform,
  });

  const { data: embeddingModelsData = [], isLoading: embeddingModelsLoading, error: embeddingModelsError } = useQuery({
    queryKey: ['embedding-models', selectedEmbeddingPlatform],
    queryFn: () => getEmbeddingModels(selectedEmbeddingPlatform),
    enabled: !!selectedEmbeddingPlatform,
  });

const llmPlatformOptions = toOptions(llmPlatformsData);
const embeddingPlatformOptions = toOptions(embeddingPlatformsData);
const llmModelOptions = toOptions(llmModelsData);
const embeddingModelOptions = toOptions(embeddingModelsData);

  const [apiKeyReplaceMode, setApiKeyReplaceMode] = React.useState(isEditing);
  const [secretKeyReplaceMode, setSecretKeyReplaceMode] = React.useState(isEditing);
  const [accessKeyReplaceMode, setAccessKeyReplaceMode] = React.useState(isEditing);
  const [embeddingApiKeyReplaceMode, setEmbeddingApiKeyReplaceMode] = React.useState(isEditing);
  // Embedding platform specific replace modes
  const [embeddingSecretKeyReplaceMode, setEmbeddingSecretKeyReplaceMode] = React.useState(isEditing);
  const [embeddingAccessKeyReplaceMode, setEmbeddingAccessKeyReplaceMode] = React.useState(isEditing);
  const [embeddingAzureApiKeyReplaceMode, setEmbeddingAzureApiKeyReplaceMode] = React.useState(isEditing);

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
    // Reset embedding platform specific fields
    setValue('embeddingAccessKey', '');
    setValue('embeddingSecretKey', '');
    setValue('embeddingDeploymentName', '');
    setValue('embeddingTargetUri', '');
    setValue('embeddingAzureApiKey', '');

    // Reset replace mode states when platform changes
    setEmbeddingApiKeyReplaceMode(false);
    setEmbeddingSecretKeyReplaceMode(false);
    setEmbeddingAccessKeyReplaceMode(false);
    setEmbeddingAzureApiKeyReplaceMode(false);
  };
  // Model options based on selected platform
  const getLLMModelOptions = () => {
    return llmModelOptions;
  };

  const getEmbeddingModelOptions = () => {
    return embeddingModelOptions;
  };

  const deploymentEnvironments = [
    { label: t('llmConnectionForm.environments.testing'), value: 'testing' },
    { label: t('llmConnectionForm.environments.production'), value: 'production' },
  ];

  const renderPlatformSpecificFields = () => {
    switch (selectedLLMPlatform) {
      case 'aws':
        return (
          <>
            <div className="form-row">
              <p className='form-label'>{t('llmConnectionForm.aws.accessKey.label')}</p>
              <p className='form-description'>{t('llmConnectionForm.aws.accessKey.description')}</p>
              <Controller
                name="accessKey"
                control={control}
                rules={{ 
                  required: t('llmConnectionForm.validationMessages.accessKeyRequiredAws'),
                  pattern: {
                    value: /^\S+$/,
                    message: t('llmConnectionForm.validationMessages.invalidAccessKey')
                  }
                }}
                render={({ field }) => (
                  <FormInput
                    label=""
                    type={isEditing ? 'text' : 'password'}
                    placeholder={t('llmConnectionForm.aws.accessKey.placeholder')}
                    error={errors.accessKey?.message}
                    readOnly={accessKeyReplaceMode}
                    showEndButton={accessKeyReplaceMode}
                    onEndButtonClick={() => {
                      setAccessKeyReplaceMode(false);
                      setValue('accessKey', '');
                    }}
                    endButtonText={t('global.change')}
                    {...field}
                  />
                )}
              />
            </div>
            <div className="form-row">
              <p className='form-label'>{t('llmConnectionForm.aws.secretKey.label')}</p>
              <p className='form-description'>{t('llmConnectionForm.aws.secretKey.description')}</p>
              <Controller
                name="secretKey"
                control={control}
                rules={{ 
                  required: t('llmConnectionForm.validationMessages.secretKeyRequiredAws'),
                  pattern: {
                    value: /^\S+$/,
                    message: t('llmConnectionForm.validationMessages.invalidSecretKey')
                  }
                }}
                render={({ field }) => (
                  <FormInput
                    label=""
                    type={isEditing ? 'text' : 'password'}
                    placeholder={t('llmConnectionForm.aws.secretKey.placeholder')}
                    error={errors.secretKey?.message}
                    readOnly={secretKeyReplaceMode}
                    showEndButton={secretKeyReplaceMode}
                    onEndButtonClick={() => {
                      setSecretKeyReplaceMode(false);
                      setValue('secretKey', '');
                    }}
                    endButtonText={t('global.change')}
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
              <p className='form-label'>{t('llmConnectionForm.azure.deploymentName.label')}</p>
              <p className='form-description'>{t('llmConnectionForm.azure.deploymentName.description')}</p>
              <Controller
                name="deploymentName"
                control={control}
                rules={{ required: t('llmConnectionForm.validationMessages.deploymentNameRequiredAzure') }}
                render={({ field }) => (
                  <FormInput
                    label=""
                    placeholder={t('llmConnectionForm.azure.deploymentName.placeholder')}
                    error={errors.deploymentName?.message}
                    {...field}
                  />
                )}
              />
            </div>
            <div className="form-row">
              <p className='form-label'>{t('llmConnectionForm.azure.targetUri.label')}</p>
              <p className='form-description'>{t('llmConnectionForm.azure.targetUri.description')}</p>
              <Controller
                name="targetUri"
                control={control}
                rules={{
                  required: t('llmConnectionForm.validationMessages.endpointRequiredAzure'),
                  pattern: {
                    value: /^https?:\/\/.+/,
                    message: t('llmConnectionForm.validationMessages.invalidUrl')
                  }
                }}
                render={({ field }) => (
                  <FormInput
                    label=""
                    placeholder={t('llmConnectionForm.azure.targetUri.placeholder')}
                    error={errors.targetUri?.message}
                    {...field}
                  />
                )}
              />
            </div>
            <div className="form-row">
              <p className='form-label'>{t('llmConnectionForm.azure.apiKey.label')}</p>
              <p className='form-description'>{t('llmConnectionForm.azure.apiKey.description')}</p>

              <Controller
                name="apiKey"
                control={control}
                rules={{ 
                  required: t('llmConnectionForm.validationMessages.apiKeyRequiredAzure'),
                  pattern: {
                    value: /^\S+$/,
                    message: t('llmConnectionForm.validationMessages.invalidApiKey')
                  }
                }}
                render={({ field }) => (
                  <FormInput
                    label=""
                    type={isEditing ? 'text' : 'password'}
                    placeholder={t('llmConnectionForm.azure.apiKey.placeholder')}
                    error={errors.apiKey?.message}
                    readOnly={apiKeyReplaceMode}
                    showEndButton={apiKeyReplaceMode}
                    onEndButtonClick={() => {
                      setApiKeyReplaceMode(false);
                      setValue('apiKey', '');
                    }}
                    endButtonText={t('global.change')}
                    {...field}
                  />
                )}
              />
            </div>
          </>
        );

      default:
        return null;
    }
  };

  const renderEmbeddingPlatformSpecificFields = () => {
    switch (selectedEmbeddingPlatform) {
      case 'aws':
        return (
          <>
            <div className="form-row">
              <p className='form-label'>{t('llmConnectionForm.aws.embeddingAccessKey.label')}</p>
              <p className='form-description'>{t('llmConnectionForm.aws.embeddingAccessKey.description')}</p>
              <Controller
                name="embeddingAccessKey"
                control={control}
                rules={{ 
                  required: t('llmConnectionForm.validationMessages.embeddingAccessKeyRequiredAws'),
                  pattern: {
                    value: /^\S+$/,
                    message: t('llmConnectionForm.validationMessages.invalidEmbeddingAccessKey')
                  }
                }}
                render={({ field }) => (
                  <FormInput
                    label=""
                    type={isEditing ? 'text' : 'password'}
                    placeholder={t('llmConnectionForm.aws.embeddingAccessKey.placeholder')}
                    error={errors.embeddingAccessKey?.message}
                    readOnly={embeddingAccessKeyReplaceMode}
                    showEndButton={embeddingAccessKeyReplaceMode}
                    onEndButtonClick={() => {
                      setEmbeddingAccessKeyReplaceMode(false);
                      setValue('embeddingAccessKey', '');
                    }}
                    endButtonText={t('global.change')}
                    {...field}
                  />
                )}
              />
            </div>
            <div className="form-row">
              <p className='form-label'>{t('llmConnectionForm.aws.embeddingSecretKey.label')}</p>
              <p className='form-description'>{t('llmConnectionForm.aws.embeddingSecretKey.description')}</p>
              <Controller
                name="embeddingSecretKey"
                control={control}
                rules={{ 
                  required: t('llmConnectionForm.validationMessages.embeddingSecretKeyRequiredAws'),
                  pattern: {
                    value: /^\S+$/,
                    message: t('llmConnectionForm.validationMessages.invalidEmbeddingSecretKey')
                  }
                }}
                render={({ field }) => (
                  <FormInput
                    label=""
                    type={isEditing ? 'text' : 'password'}
                    placeholder={t('llmConnectionForm.aws.embeddingSecretKey.placeholder')}
                    error={errors.embeddingSecretKey?.message}
                    readOnly={embeddingSecretKeyReplaceMode}
                    showEndButton={embeddingSecretKeyReplaceMode}
                    onEndButtonClick={() => {
                      setEmbeddingSecretKeyReplaceMode(false);
                      setValue('embeddingSecretKey', '');
                    }}
                    endButtonText={t('global.change')}
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
              <p className='form-label'>{t('llmConnectionForm.azure.embeddingDeploymentName.label')}</p>
              <p className='form-description'>{t('llmConnectionForm.azure.embeddingDeploymentName.description')}</p>
              <Controller
                name="embeddingDeploymentName"
                control={control}
                rules={{ required: t('llmConnectionForm.validationMessages.embeddingDeploymentNameRequiredAzure') }}
                render={({ field }) => (
                  <FormInput
                    label=""
                    placeholder={t('llmConnectionForm.azure.embeddingDeploymentName.placeholder')}
                    error={errors.embeddingDeploymentName?.message}
                    {...field}
                  />
                )}
              />
            </div>
            <div className="form-row">
              <p className='form-label'>{t('llmConnectionForm.azure.embeddingTargetUri.label')}</p>
              <p className='form-description'>{t('llmConnectionForm.azure.embeddingTargetUri.description')}</p>
              <Controller
                name="embeddingTargetUri"
                control={control}
                rules={{
                  required: t('llmConnectionForm.validationMessages.embeddingEndpointRequiredAzure'),
                  pattern: {
                    value: /^https?:\/\/.+/,
                    message: t('llmConnectionForm.validationMessages.invalidUrl')
                  }
                }}
                render={({ field }) => (
                  <FormInput
                    label=""
                    placeholder={t('llmConnectionForm.azure.targetUri.placeholder')}
                    error={errors.embeddingTargetUri?.message}
                    {...field}
                  />
                )}
              />
            </div>
            <div className="form-row">
              <p className='form-label'>{t('llmConnectionForm.azure.embeddingApiKey.label')}</p>
              <p className='form-description'>{t('llmConnectionForm.azure.embeddingApiKey.description')}</p>
              <Controller
                name="embeddingAzureApiKey"
                control={control}
                rules={{ 
                  required: t('llmConnectionForm.validationMessages.embeddingApiKeyRequiredAzure'),
                  pattern: {
                    value: /^\S+$/,
                    message: t('llmConnectionForm.validationMessages.invalidEmbeddingApiKey')
                  }
                }}
                render={({ field }) => (
                  <FormInput
                    label=""
                    type={isEditing ? 'text' : 'password'}
                    placeholder={t('llmConnectionForm.azure.embeddingApiKey.placeholder')}
                    error={errors.embeddingAzureApiKey?.message}
                    readOnly={embeddingAzureApiKeyReplaceMode}
                    showEndButton={embeddingAzureApiKeyReplaceMode}
                    onEndButtonClick={() => {
                      setEmbeddingAzureApiKeyReplaceMode(false);
                      setValue('embeddingAzureApiKey', '');
                    }}
                    endButtonText={t('global.change')}
                    {...field}
                  />
                )}
              />
            </div>
          </>
        );

      default:
        return null;
    }
  };

  const handleFormSubmit = (data: LLMConnectionFormData) => {
    const cleanedData = {
      ...data,
      monthlyBudget: data.monthlyBudget.replace(/,/g, ''),
      warnBudget: data.warnBudget.replace('%', ''),
      stopBudget: data.stopBudget.replace('%', ''),
    };
    onSubmit(cleanedData);
  };

  return (
    <div className="llm-connection-form">
      <form onSubmit={handleSubmit(handleFormSubmit)}>
        <div className="form-section">
          <h3 className="form-section-title">{t('llmConnectionForm.sections.llmConfiguration')}</h3>

          <div className="form-row">
            <p className='form-label'>{t('llmConnectionForm.fields.connectionName.label')}</p>
            <p className='form-description'>{t('llmConnectionForm.fields.connectionName.description')}</p>
            <Controller
              name="connectionName"
              control={control}
              rules={{ 
                required: t('llmConnectionForm.validationMessages.connectionNameRequired'),
                maxLength: {
                  value: 100,
                  message: t('llmConnectionForm.validationMessages.connectionNameMaxLength')
                }
              }}
              render={({ field }) => (
                <FormInput
                  label=""
                  placeholder={t('llmConnectionForm.fields.connectionName.placeholder')}
                  error={errors.connectionName?.message}
                  disabled={readOnly}
                  //maxLength={100}
                  {...field}
                />
              )}
            />
          </div>

          <div className="form-row">
            <p className='form-label'>{t('llmConnectionForm.fields.llmPlatform.label')}</p>
            <p className='form-description'>{t('llmConnectionForm.fields.llmPlatform.description')}</p>
            <Controller
              name="llmPlatform"
              control={control}
              rules={{ required: t('llmConnectionForm.validationMessages.llmPlatformRequired') }}
              render={({ field }) => (
                <FormSelect
                  label=""
                  options={llmPlatformOptions || []}
                  placeholder={
                    llmPlatformsLoading
                      ? t('llmConnectionForm.placeholders.loadingPlatforms')
                      : llmPlatformsError
                        ? t('llmConnectionForm.placeholders.errorLoadingPlatforms')
                        : t('llmConnectionForm.fields.llmPlatform.placeholder')
                  }
                  error={errors.llmPlatform?.message || (llmPlatformsError ? t('llmConnectionForm.validationMessages.failedToLoadPlatforms') : undefined)}
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
            <p className='form-label'>{t('llmConnectionForm.fields.llmModel.label')}</p>
            <p className='form-description'>{t('llmConnectionForm.fields.llmModel.description')}</p>

            <Controller
              name="llmModel"
              control={control}
              rules={{ required: t('llmConnectionForm.validationMessages.llmModelRequired') }}
              render={({ field }) => (
                <FormSelect
                  label=""
                  options={getLLMModelOptions() || []}
                  placeholder={
                    llmModelsLoading
                      ? t('llmConnectionForm.placeholders.loadingModels')
                      : llmModelsError
                        ? t('llmConnectionForm.placeholders.errorLoadingModels')
                        : !selectedLLMPlatform
                          ? t('llmConnectionForm.placeholders.selectPlatformFirst')
                          : t('llmConnectionForm.fields.llmModel.placeholder')
                  }
                  error={errors.llmModel?.message || (llmModelsError ? t('llmConnectionForm.validationMessages.failedToLoadModels') : undefined)}
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
          <h3 className="form-section-title">{t('llmConnectionForm.sections.embeddingConfiguration')}</h3>

          <div className="form-row">
            <p className='form-label'>{t('llmConnectionForm.fields.embeddingPlatform.label')}</p>
            <p className='form-description'>{t('llmConnectionForm.fields.embeddingPlatform.description')}</p>

            <Controller
              name="embeddingModelPlatform"
              control={control}
              rules={{ required: t('llmConnectionForm.validationMessages.embeddingPlatformRequired') }}
              render={({ field }) => (
                <FormSelect
                  label=""
                  options={embeddingPlatformOptions || []}
                  placeholder={
                    embeddingPlatformsLoading
                      ? t('llmConnectionForm.placeholders.loadingPlatforms')
                      : embeddingPlatformsError
                        ? t('llmConnectionForm.placeholders.errorLoadingPlatforms')
                        : t('llmConnectionForm.fields.embeddingPlatform.placeholder')
                  }
                  error={errors.embeddingModelPlatform?.message || (embeddingPlatformsError ? t('llmConnectionForm.validationMessages.failedToLoadPlatforms') : undefined)}
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
            <p className='form-label'>{t('llmConnectionForm.fields.embeddingModel.label')}</p>
            <p className='form-description'>{t('llmConnectionForm.fields.embeddingModel.description')}</p>

            <Controller
              name="embeddingModel"
              control={control}
              rules={{ required: t('llmConnectionForm.validationMessages.embeddingModelRequired') }}
              render={({ field }) => (
                <FormSelect
                  label=""
                  options={getEmbeddingModelOptions() || []}
                  placeholder={
                    embeddingModelsLoading
                      ? t('llmConnectionForm.placeholders.loadingModels')
                      : embeddingModelsError
                        ? t('llmConnectionForm.placeholders.errorLoadingModels')
                        : !selectedEmbeddingPlatform
                          ? t('llmConnectionForm.placeholders.selectPlatformFirst')
                          : t('llmConnectionForm.fields.embeddingModel.placeholder')
                  }
                  error={errors.embeddingModel?.message || (embeddingModelsError ? t('llmConnectionForm.validationMessages.failedToLoadModels') : undefined)}
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

          {/* Embedding Platform-specific fields */}
          {renderEmbeddingPlatformSpecificFields()}
        </div>

        <div className="form-section">
          <h3 className="form-section-title">{t('llmConnectionForm.sections.budgetDeployment')}</h3>

          <div className="form-row">
            <p className='form-label'>{t('llmConnectionForm.fields.monthlyBudget.label')}</p>
            <p className='form-description'>{t('llmConnectionForm.fields.monthlyBudget.description')}</p>

            <Controller
              name="monthlyBudget"
              control={control}
              rules={{
                required: t('llmConnectionForm.validationMessages.monthlyBudgetRequired'),
                pattern: {
                  value: /^[\d,]+(\.\d{1,2})?$/,
                  message: t('llmConnectionForm.validationMessages.monthlyBudgetInvalid')
                },
                validate: value => {
                  const numericValue = value.replace(/,/g, '');
                  return Number(numericValue) > 0 || t('llmConnectionForm.validationMessages.monthlyBudgetPositive');
                }
              }}
              render={({ field }) => (
                <FormInput
                  label=""
                  placeholder={t('llmConnectionForm.fields.monthlyBudget.placeholder')}
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
              name="disconnectOnBudgetExceed"
              control={control}
              render={({ field }) => (
                <FormCheckbox
                  label=""
                  name="disconnectOnBudgetExceed"
                  item={{
                    label: t('llmConnectionForm.fields.disconnectOnBudgetExceed.label'),
                    value: "true",
                    checked: field.value
                  }}
                  checked={field.value}
                  onChange={(e) => field.onChange(e.target.checked)}
                  hideLabel={true}
                />
              )}
            />
          </div>

          <div className="form-row">
            <p className='form-label'>{t('llmConnectionForm.fields.warnBudget.label')}</p>
            <p className='form-description'>{t('llmConnectionForm.fields.warnBudget.description')}</p>

            <Controller
              name="warnBudget"
              control={control}
              rules={{
                required: t('llmConnectionForm.validationMessages.warnBudgetRequired'),
                pattern: {
                  value: /^\d+$/,
                  message: t('llmConnectionForm.validationMessages.numbersOnly')
                },
                validate: (value, formValues) => {
                  const numericValue = Number(value.replace('%', ''));

                  if (numericValue < 1 || numericValue > 100) {
                    return t('llmConnectionForm.validationMessages.warnBudgetRange');
                  }
                  return true;
                }
              }}
              render={({ field }) => (
                <FormInput
                  label=""
                  placeholder={t('llmConnectionForm.fields.warnBudget.placeholder')}
                  error={errors.warnBudget?.message}
                  value={field.value ? `${field.value}%` : ''}
                  onChange={(e) => {
                    const value = e.target.value.replace(/[^\d]/g, ''); // Remove all non-numeric characters
                    field.onChange(value);
                  }}
                  name={field.name}
                  onBlur={field.onBlur}
                />
              )}
            />
          </div>

          {disconnectOnBudgetExceed && (
            <div className="form-row">
              <p className='form-label'>{t('llmConnectionForm.fields.stopBudget.label')}</p>
              <p className='form-description'>{t('llmConnectionForm.fields.stopBudget.description')}</p>

              <Controller
                name="stopBudget"
                control={control}
                rules={{
                  required: disconnectOnBudgetExceed ? t('llmConnectionForm.validationMessages.stopBudgetRequired') : false,
                  pattern: {
                    value: /^\d+$/,
                    message: t('llmConnectionForm.validationMessages.numbersOnly')
                  },
                  validate: (value, formValues) => {
                    if (!disconnectOnBudgetExceed) return true;

                    const numericValue = Number(value.replace('%', ''));
                    const warnValue = Number(formValues.warnBudget?.replace('%', '') || 0);

                    if (numericValue < 1 || numericValue > 200) {
                      return t('llmConnectionForm.validationMessages.stopBudgetRange');
                    }

                    if (warnValue > 0 && numericValue <= warnValue) {
                      return t('llmConnectionForm.validationMessages.stopBudgetGreater');
                    }

                    return true;
                  }
                }}
                render={({ field }) => (
                  <FormInput
                    label=""
                    placeholder={t('llmConnectionForm.fields.stopBudget.placeholder')}
                    error={errors.stopBudget?.message}
                    value={field.value ? `${field.value}%` : ''}
                    onChange={(e) => {
                      const value = e.target.value.replace(/[^\d]/g, ''); // Remove all non-numeric characters
                      field.onChange(value);
                    }}
                    name={field.name}
                    onBlur={field.onBlur}
                  />
                )}
              />
            </div>
          )}

          <div className="form-row">
            <Controller
              name="deploymentEnvironment"
              control={control}
              rules={{ required: t('llmConnectionForm.validationMessages.deploymentEnvironmentRequired') }}
              render={({ field }) => (
                <div className="radio-group">
                  <label className="radio-group-label">{t('llmConnectionForm.fields.deploymentEnvironment.label')}</label>
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
                {t('global.cancel')}
              </Button>
              {isEditing && (<Button
                appearance="error"
                onClick={onDelete}
                type='button'
              >
                {t('llmConnectionForm.buttons.deleteConnection')}
              </Button>)}
              <Button
                type="submit"
                disabled={!isDirty || !isValid}
                appearance="primary"
              >
                {isEditing ? (t('llmConnectionForm.buttons.updateConnection')) : (t('llmConnectionForm.buttons.createConnection'))}
              </Button>
            </div>
          </Track>
        </div>

      </form>
    </div>
  );
};

export default LLMConnectionForm;