import { FC, useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Button, FormTextarea } from 'components';
import { ButtonAppearanceTypes, ToastTypes } from 'enums/commonEnums';
import CircularSpinner from 'components/molecules/CircularSpinner/CircularSpinner';
import { getPromptConfiguration, savePromptConfiguration } from 'services/promptConfiguration';
import { promptConfigurationQueryKeys } from 'utils/queryKeys';
import { useToast } from 'hooks/useToast';
import './PromptConfigurations.scss';

const PromptConfigurations: FC = () => {
    const { t } = useTranslation();
    const toast = useToast();
    const queryClient = useQueryClient();
    const [promptText, setPromptText] = useState('');
    const [isUpdating, setIsUpdating] = useState(false);

    // Fetch prompt configuration
    const { data: promptConfig, isLoading } = useQuery({
        queryKey: promptConfigurationQueryKeys.current(),
        queryFn: getPromptConfiguration,
    });
    

    // Update promptText when data is loaded
    useEffect(() => {
        if (promptConfig && promptConfig.length > 0) {
            setPromptText(promptConfig[0].prompt || '');
            setIsUpdating(true);
        }
    }, [promptConfig]);

    // Save prompt mutation
    const saveMutation = useMutation({
        mutationFn: savePromptConfiguration,
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: promptConfigurationQueryKeys.current() });
            toast.open({
                type: ToastTypes.SUCCESS,
                title: t('toast.success.title'),
                message: t('promptConfigurations.submitSuccess'),
            });
        },
        onError: (error: any) => {
            console.error('Error saving prompt:', error);
            toast.open({
                type: ToastTypes.ERROR,
                title: t('toast.error.title'),
                message: t('promptConfigurations.submitError'),
            });
        },
    });

    const handleSubmit = () => {
        if (!promptText.trim()) {
            return;
        }
        saveMutation.mutate(promptText);
    };

    if (isLoading) {
        return <CircularSpinner />;
    }

    return (
        <div className="prompt-configurations">
            <div className="container">
                <div className="title_container">
                    <div className="title">{t('promptConfigurations.title')}</div>
                </div>

                <div className="prompt-form">
                    <FormTextarea
                        label={t('promptConfigurations.promptLabel')}
                        name="promptText"
                        value={promptText}
                        onChange={(e) => setPromptText(e.target.value)}
                        minRows={10}
                    />

                    <div className="form-actions">
                        <Button
                            appearance={ButtonAppearanceTypes.PRIMARY}
                            onClick={handleSubmit}
                            disabled={saveMutation.isPending || !promptText.trim()}
                        >
                            {saveMutation.isPending 
                                ? (isUpdating ? t('promptConfigurations.updating') : t('promptConfigurations.saving'))
                                : (isUpdating ? t('promptConfigurations.updateButton') : t('promptConfigurations.submitButton'))
                            }
                        </Button>
                    </div>
                </div>
            </div>
        </div>
    );
};

export default PromptConfigurations;
