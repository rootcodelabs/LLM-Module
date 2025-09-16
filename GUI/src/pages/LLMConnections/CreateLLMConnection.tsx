import BackArrowButton from "assets/BackArrowButton";
import LLMConnectionForm, { LLMConnectionFormData } from "components/molecules/LLMConnectionForm";
import { Link, useNavigate } from "react-router-dom";
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useToast } from 'hooks/useToast';
import { createLLMConnection } from 'services/llmConnections';
import { llmConnectionsQueryKeys } from 'utils/queryKeys';
import { ToastTypes } from 'enums/commonEnums';

const CreateLLMConnection = () => {
    const navigate = useNavigate();
    const toast = useToast();
    const queryClient = useQueryClient();
    
    const createConnectionMutation = useMutation({
      mutationFn: createLLMConnection,
      onSuccess: async () => {
        // Invalidate and refetch LLM connections
        await queryClient.invalidateQueries({
          queryKey: llmConnectionsQueryKeys.all()
        });
        
        toast.open({
          type: ToastTypes.SUCCESS,
          title: 'Success',
          message: 'LLM connection created successfully!',
        });
        
        navigate('/llm-connections');
      },
      onError: (error: any) => {
        console.error('Error creating LLM connection:', error);
        toast.open({
          type: ToastTypes.ERROR,
          title: 'Error',
          message: error?.message || 'Failed to create LLM connection. Please try again.',
        });
      },
    });
    
    const handleSubmit = async (data: LLMConnectionFormData) => {
      createConnectionMutation.mutate(data);
    };
    
    const handleCancel = () => {
      navigate('/llm-connections');
    };

    return(
        <div className="container">
        <div className="title_container">
          <div className="flex-grid">
            <Link to={'/llm-connections'}>
              <BackArrowButton />
            </Link>
            <div className="title">{'Create LLM Connection'}</div>
          </div>
        </div>
        <LLMConnectionForm
        onSubmit={handleSubmit}
        onCancel={handleCancel}
        isEditing={false}
        onDelete={() => {}}
      />
        </div>

    )
}

export default CreateLLMConnection;