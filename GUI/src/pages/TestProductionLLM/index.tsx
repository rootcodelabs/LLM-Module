import { FC, useState, useRef, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { Button, FormTextarea, Section } from 'components';
import { productionInference, ProductionInferenceRequest } from 'services/inference';
import { useToast } from 'hooks/useToast';
import './TestProductionLLM.scss';

interface Message {
  id: string;
  content: string;
  isUser: boolean;
  timestamp: string;
}

const TestProductionLLM: FC = () => {
  const { t } = useTranslation();
  const toast = useToast();
  const [message, setMessage] = useState<string>('');
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleSendMessage = async () => {
    if (!message.trim()) {
      toast.open({
        type: 'warning',
        title: t('warningTitle'),
        message: t('emptyMessageWarning'),
      });
      return;
    }

    const userMessage: Message = {
      id: `user-${Date.now()}`,
      content: message.trim(),
      isUser: true,
      timestamp: new Date().toISOString(),
    };

    // Add user message to chat
    setMessages(prev => [...prev, userMessage]);
    setMessage('');
    setIsLoading(true);

    try {
      // Hardcoded values as requested
      const request: ProductionInferenceRequest = {
        chatId: 'test-chat-001',
        message: userMessage.content,
        authorId: 'test-author-001', 
        conversationHistory: messages.map(msg => ({
          authorRole: msg.isUser ? 'user' : 'bot',
          message: msg.content,
          timestamp: msg.timestamp,
        })),
        url: 'https://test-url.example.com',
      };

      const response = await productionInference(request);

      // Create bot response message
      let botContent = '';
      let botMessageType: 'success' | 'error' = 'success';

      if (response.status && response.status >= 400) {
        // Error response
        botContent = response.content || 'An error occurred while processing your request.';
        botMessageType = 'error';
      } else {
        // Success response
        botContent = response.content || 'Response received successfully.';
        
        if (response.questionOutOfLlmScope) {
          botContent += ' (Note: This question appears to be outside the LLM scope)';
        }
      }

      const botMessage: Message = {
        id: `bot-${Date.now()}`,
        content: botContent,
        isUser: false,
        timestamp: new Date().toISOString(),
      };

      setMessages(prev => [...prev, botMessage]);

      // Show toast notification
      toast.open({
        type: botMessageType,
        title: botMessageType === 'success' ? t('responseReceived') : t('errorOccurred'),
        message: botMessageType === 'success' 
          ? t('successMessage') 
          : t('errorMessage'),
      });

    } catch (error) {
      console.error('Error sending message:', error);
      
      const errorMessage: Message = {
        id: `error-${Date.now()}`,
        content: 'Failed to send message. Please check your connection and try again.',
        isUser: false,
        timestamp: new Date().toISOString(),
      };

      setMessages(prev => [...prev, errorMessage]);

      toast.open({
        type: 'error',
        title: 'Connection Error',
        message: 'Unable to connect to the production LLM service.',
      });
    } finally {
      setIsLoading(false);
    }
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  const clearChat = () => {
    setMessages([]);
    toast.open({
      type: 'info',
      title: 'Chat Cleared',
      message: 'All messages have been cleared.',
    });
  };

  return (
    <div>
      <div className="test-production-llm">
        <div className="test-production-llm__header">
          <h1>{t('Test Production LLM')}</h1>
          <Button onClick={clearChat} appearance="secondary">
            {t('Clear Chat')}
          </Button>
        </div>

        <div className="test-production-llm__chat-container">
          <div className="test-production-llm__messages">
            {messages.length === 0 && (
              <div className="test-production-llm__welcome">
                <p>Welcome to Production LLM Testing</p>
                <p>Start a conversation by typing a message below.</p>
              </div>
            )}
            
            {messages.map((msg) => (
              <div
                key={msg.id}
                className={`test-production-llm__message ${
                  msg.isUser ? 'test-production-llm__message--user' : 'test-production-llm__message--bot'
                }`}
              >
                <div className="test-production-llm__message-content">
                  {msg.content}
                </div>
                <div className="test-production-llm__message-timestamp">
                  {new Date(msg.timestamp).toLocaleTimeString()}
                </div>
              </div>
            ))}
            
            {isLoading && (
              <div className="test-production-llm__message test-production-llm__message--bot">
                <div className="test-production-llm__message-content">
                  <div className="test-production-llm__typing">
                    <span></span>
                    <span></span>
                    <span></span>
                  </div>
                </div>
              </div>
            )}
            
            <div ref={messagesEndRef} />
          </div>

          <div className="test-production-llm__input-area">
            <FormTextarea
              label="Message"
              name="message"
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              onKeyDown={handleKeyPress}
              placeholder="Type your message here... (Press Enter to send, Shift+Enter for new line)"
              hideLabel
              maxRows={4}
              disabled={isLoading}
            />
            <Button
              onClick={handleSendMessage}
              disabled={isLoading || !message.trim()}
              className="test-production-llm__send-button"
            >
              {isLoading ? 'Sending...' : 'Send'}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default TestProductionLLM;
