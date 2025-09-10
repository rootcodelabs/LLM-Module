import React from 'react';
import { useForm, Controller } from 'react-hook-form';
import { useTranslation } from 'react-i18next';
import FormInput from 'components/FormElements/FormInput';
import FormSelect from 'components/FormElements/FormSelect';
import Button from 'components/Button';
import Track from 'components/Track';
import './LLMConnectionForm.scss';

export type LLMConnectionFormData = {
  llmPlatform: string;
  llmModel: string;
  embeddingModelPlatform: string;
  embeddingModel: string;
  llmApiKey: string;
  embeddingApiKey: string;
  monthlyBudget: string;
  deploymentEnvironment: string;
};

type LLMConnectionFormProps = {
  onSubmit: (data: LLMConnectionFormData) => void;
  onCancel: () => void;
  defaultValues?: Partial<LLMConnectionFormData>;
  isEditing?: boolean;
  readOnly?: boolean;
};

const LLMConnectionForm: React.FC<LLMConnectionFormProps> = ({
  onSubmit,
  onCancel,
  defaultValues,
  isEditing = false,
  readOnly = false,
}) => {
  const { t } = useTranslation();
  const {
    control,
    handleSubmit,
    watch,
    formState: { errors, isDirty, isValid },
  } = useForm<LLMConnectionFormData>({
    defaultValues: {
      llmPlatform: '',
      llmModel: '',
      embeddingModelPlatform: '',
      embeddingModel: '',
      llmApiKey: '',
      embeddingApiKey: '',
      monthlyBudget: '',
      deploymentEnvironment: 'development',
      ...defaultValues,
    },
    mode: 'onChange',
  });

  const selectedLLMPlatform = watch('llmPlatform');
  const selectedEmbeddingPlatform = watch('embeddingModelPlatform');

  // Platform options
  const llmPlatformOptions = [
    { label: 'OpenAI', value: 'openai' },
    { label: 'Anthropic (Claude)', value: 'anthropic' },
    { label: 'Google Cloud (PaLM)', value: 'google' },
    { label: 'Azure OpenAI', value: 'azure' },
    { label: 'AWS Bedrock', value: 'bedrock' },
    { label: 'Cohere', value: 'cohere' },
    { label: 'Hugging Face', value: 'huggingface' },
    { label: 'Local/Self-hosted', value: 'local' },
  ];

  const embeddingPlatformOptions = [
    { label: 'OpenAI', value: 'openai' },
    { label: 'Cohere', value: 'cohere' },
    { label: 'Hugging Face', value: 'huggingface' },
    { label: 'Sentence Transformers', value: 'sentence-transformers' },
    { label: 'Azure OpenAI', value: 'azure' },
    { label: 'Google Cloud', value: 'google' },
    { label: 'Local/Self-hosted', value: 'local' },
  ];

  // Model options based on selected platform
  const getLLMModelOptions = (platform: string) => {
    switch (platform) {
      case 'openai':
        return [
          { label: 'GPT-4', value: 'gpt-4' },
          { label: 'GPT-4 Turbo', value: 'gpt-4-turbo' },
          { label: 'GPT-3.5 Turbo', value: 'gpt-3.5-turbo' },
        ];
      case 'anthropic':
        return [
          { label: 'Claude 3 Opus', value: 'claude-3-opus' },
          { label: 'Claude 3 Sonnet', value: 'claude-3-sonnet' },
          { label: 'Claude 3 Haiku', value: 'claude-3-haiku' },
        ];
      case 'google':
        return [
          { label: 'PaLM 2', value: 'palm-2' },
          { label: 'Gemini Pro', value: 'gemini-pro' },
        ];
      case 'cohere':
        return [
          { label: 'Command', value: 'command' },
          { label: 'Command Light', value: 'command-light' },
        ];
      default:
        return [{ label: 'Custom Model', value: 'custom' }];
    }
  };

  const getEmbeddingModelOptions = (platform: string) => {
    switch (platform) {
      case 'openai':
        return [
          { label: 'text-embedding-ada-002', value: 'text-embedding-ada-002' },
          { label: 'text-embedding-3-small', value: 'text-embedding-3-small' },
          { label: 'text-embedding-3-large', value: 'text-embedding-3-large' },
        ];
      case 'cohere':
        return [
          { label: 'embed-english-v3.0', value: 'embed-english-v3.0' },
          { label: 'embed-multilingual-v3.0', value: 'embed-multilingual-v3.0' },
        ];
      case 'huggingface':
        return [
          { label: 'all-MiniLM-L6-v2', value: 'sentence-transformers/all-MiniLM-L6-v2' },
          { label: 'all-mpnet-base-v2', value: 'sentence-transformers/all-mpnet-base-v2' },
        ];
      default:
        return [{ label: 'Custom Model', value: 'custom' }];
    }
  };

  const deploymentEnvironments = [
    { label: 'Testing', value: 'testing' },
    { label: 'Production', value: 'production' },
  ];

  const handleFormSubmit = (data: LLMConnectionFormData) => {
    onSubmit(data);
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
                  placeholder="Select LLM Platform"
                  error={errors.llmPlatform?.message}
                  disabled={readOnly}
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
             <p className='form-label'>LLM Model</p>
            <p className='form-description'>The LLM model that you want to use</p>
            
            <Controller
              name="llmModel"
              control={control}
              rules={{ required: 'LLM Model is required' }}
              render={({ field }) => (
                <FormSelect
                  label=""
                  options={getLLMModelOptions(selectedLLMPlatform)}
                  placeholder="Select LLM Model"
                  error={errors.llmModel?.message}
                  disabled={!selectedLLMPlatform || readOnly}
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
             <p className='form-label'>LLM API Key</p>
            <p className='form-description'>The API key of the LLM model</p>
            
            <Controller
              name="llmApiKey"
              control={control}
              rules={{ required: 'LLM API Key is required' }}
              render={({ field }) => (
                <FormInput
                  label=""
                  type="password"
                  placeholder="Enter your LLM API key"
                  error={errors.llmApiKey?.message}
                  {...field}
                />
              )}
            />
          </div>
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
                  placeholder="Select Embedding Platform"
                  error={errors.embeddingModelPlatform?.message}
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
              <p className='form-label'>Embedding Model</p>
            <p className='form-description'>The embedding model that will be used for searching your knowledge base</p>
            
            <Controller
              name="embeddingModel"
              control={control}
              rules={{ required: 'Embedding Model is required' }}
              render={({ field }) => (
                <FormSelect
                  label=""
                  options={getEmbeddingModelOptions(selectedEmbeddingPlatform)}
                  placeholder="Select Embedding Model"
                  error={errors.embeddingModel?.message}
                  disabled={!selectedEmbeddingPlatform}
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
              name="embeddingApiKey"
              control={control}
              rules={{ required: 'Embedding API Key is required' }}
              render={({ field }) => (
                <FormInput
                  label=""
                  type="password"
                  placeholder="Enter your Embedding API key"
                  error={errors.embeddingApiKey?.message}
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
                  value: /^\d+(\.\d{1,2})?$/,
                  message: 'Please enter a valid budget amount'
                }
              }}
              render={({ field }) => (
                <FormInput
                  label=""
                  type="number"
                  placeholder="Enter monthly budget"
                  error={errors.monthlyBudget?.message}
                  {...field}
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
                    {deploymentEnvironments.map((env) => (
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
            <Button 
              type="submit" 
              disabled={!isDirty || !isValid}
              appearance="primary"
            >
              {isEditing ? ('Update') : ('Create')}
            </Button>
          </div>
        </Track>
        </div>
        
      </form>
    </div>
  );
};

export default LLMConnectionForm;
