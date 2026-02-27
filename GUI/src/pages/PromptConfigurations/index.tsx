import { FC, useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Button, FormTextarea, Switch } from 'components';
import { ButtonAppearanceTypes, ToastTypes } from 'enums/commonEnums';
import CircularSpinner from 'components/molecules/CircularSpinner/CircularSpinner';
import { getPromptConfiguration, savePromptConfiguration, deletePromptConfiguration } from 'services/promptConfiguration';
import { promptConfigurationQueryKeys } from 'utils/queryKeys';
import { useToast } from 'hooks/useToast';
import './PromptConfigurations.scss';

const PromptConfigurations: FC = () => {
    const { t } = useTranslation();
    const toast = useToast();
    const queryClient = useQueryClient();
    const [promptText, setPromptText] = useState('');
    const [isUpdating, setIsUpdating] = useState(false);
    const [isEnabled, setIsEnabled] = useState(false);

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
            setIsEnabled(true);
        } else {
            setPromptText('');
            setIsUpdating(false);
            setIsEnabled(false);
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

    // Delete prompt mutation
    const deleteMutation = useMutation({
        mutationFn: deletePromptConfiguration,
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: promptConfigurationQueryKeys.current() });
            setPromptText('');
            setIsUpdating(false);
            setIsEnabled(false);
            toast.open({
                type: ToastTypes.SUCCESS,
                title: t('toast.success.title'),
                message: t('promptConfigurations.deleteSuccess'),
            });
        },
        onError: (error: any) => {
            console.error('Error deleting prompt:', error);
            toast.open({
                type: ToastTypes.ERROR,
                title: t('toast.error.title'),
                message: t('promptConfigurations.deleteError'),
            });
        },
    });

    const handleSubmit = () => {
        if (!promptText.trim()) {
            return;
        }
        saveMutation.mutate(promptText);
    };

    const handleToggleChange = (checked: boolean) => {
        if (!checked) {
            // Disable: delete the prompt if it exists, and clear textarea
            setPromptText('');
            if (isUpdating) {
                deleteMutation.mutate();
            }
        }
        setIsEnabled(checked);
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
                    <div className="toggle-header">
                        <span>{t('promptConfigurations.enableToggleLabel')}</span>
                        <Switch
                            label=""
                            hideLabel={true}
                            checked={isEnabled}
                            onCheckedChange={handleToggleChange}
                            name="enableCustomPrompt"
                            onLabel=""
                            offLabel=""
                        />
                    </div>
                    <div className="separator"></div>

                    <FormTextarea
                        label={t('promptConfigurations.promptLabel')}
                        name="promptText"
                        value={promptText}
                        onChange={(e) => setPromptText(e.target.value)}
                        minRows={10}
                        disabled={!isEnabled}
                    />

                    <div className="form-actions">
                        <Button
                            appearance={ButtonAppearanceTypes.PRIMARY}
                            onClick={handleSubmit}
                            disabled={!isEnabled || saveMutation.isLoading || !promptText.trim()}
                        >
                            {saveMutation.isLoading 
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