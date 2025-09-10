import BackArrowButton from "assets/BackArrowButton";
import LLMConnectionForm, { LLMConnectionFormData } from "components/molecules/LLMConnectionForm";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";

const CreateLLMConnection = () => {
    const navigate = useNavigate();
      const [isLoading, setIsLoading] = useState(false);
    
      const handleSubmit = async (data: LLMConnectionFormData) => {
        setIsLoading(true);
        try {
          // Here you would typically call your API to create the LLM connection
          console.log('Creating LLM Connection:', data);
          
          // Simulate API call
          await new Promise(resolve => setTimeout(resolve, 1000));
          
          // Navigate back to connections list or show success message
          navigate('/llm-connections');
        } catch (error) {
          console.error('Error creating LLM connection:', error);
          // Handle error (show toast, etc.)
        } finally {
          setIsLoading(false);
        }
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
      />
        </div>

    )
}

export default CreateLLMConnection;