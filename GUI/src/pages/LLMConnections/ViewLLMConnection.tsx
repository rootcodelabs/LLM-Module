import  { useState, useEffect } from 'react';
import { useNavigate, useSearchParams, Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import BackArrowButton from 'assets/BackArrowButton';
import LLMConnectionForm, { LLMConnectionFormData } from 'components/molecules/LLMConnectionForm';
import { mockLLMConnections, getDetailedConnectionData } from 'mockData/llmConnectionData';

const ViewLLMConnection = () => {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const [searchParams] = useSearchParams();
  const [isLoading, setIsLoading] = useState(false);
  const [isEditing, setIsEditing] = useState(false);
  const [connectionData, setConnectionData] = useState<LLMConnectionFormData | null>(null);

  const connectionId = searchParams.get('id');

  useEffect(() => {
    if (connectionId) {
      const detailedData = getDetailedConnectionData(connectionId);
      if (detailedData) {
        setConnectionData(detailedData);
      }
    }
  }, [connectionId]);

  const handleSubmit = async (data: LLMConnectionFormData) => {
    setIsLoading(true);
    try {
      console.log('Updating LLM Connection:', data);
      
      // Simulate API call
      await new Promise(resolve => setTimeout(resolve, 1000));
      
      // Update connection data
      setConnectionData(data);
      setIsEditing(false);
      
      // Show success message or navigate
      console.log('Connection updated successfully');
    } catch (error) {
      console.error('Error updating LLM connection:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const handleCancel = () => {
    if (isEditing) {
      setIsEditing(false);
    } else {
      navigate('/llm-connections');
    }
  };

  const handleEdit = () => {
    setIsEditing(true);
  };

  const handleDelete = () => {
    // Implement delete functionality
    if (window.confirm('Are you sure you want to delete this LLM connection?')) {
      console.log('Delete connection:', connectionId);
      navigate('/llm-connections');
    }
  };

  if (!connectionData) {
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

  const connection = mockLLMConnections.find(
    conn => conn.llmConnectionId.toString() === connectionId
  );

  return (
    <div className="container">
      <div className="title_container">
        <div className="flex-grid">
          <Link to={'/llm-connections'}>
            <BackArrowButton />
          </Link>
          <div className="title">
            {isEditing ? 'Edit LLM Connection' : ''}
            {connection?.llmConnectionName && ` ${connection.llmConnectionName}`}
          </div>
        </div>
        
      </div>

      <LLMConnectionForm
        onSubmit={handleSubmit}
        onCancel={handleCancel}
        defaultValues={connectionData}
        isEditing={isEditing}
      />
    </div>
  );
};

export default ViewLLMConnection;