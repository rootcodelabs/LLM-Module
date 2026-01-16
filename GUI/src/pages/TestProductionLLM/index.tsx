import { FC, useState, useRef, useEffect, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { Button, FormTextarea } from 'components';
import { useToast } from 'hooks/useToast';
import { useStreamingResponse } from 'hooks/useStreamingResponse';
import './TestProductionLLM.scss';
import MessageContent from 'components/MessageContent';
interface Message {
  id: string;
  content: string;
  isUser: boolean;
  timestamp: string;
}

const TestProductionLLM: FC = () => {
  const { t } = useTranslation();
  const toast = useToast();
  const [inputMessage, setInputMessage] = useState<string>('');
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Generate a unique channel ID for this session
  const channelId = useMemo(() => `channel-${Math.random().toString(36).substring(2, 15)}`, []);
  const { startStreaming, stopStreaming, isStreaming } = useStreamingResponse(channelId);

  // Auto-scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSendMessage = async () => {
    if (!inputMessage.trim()) {
      toast.open({
        type: 'warning',
        title: 'Warning',
        message: 'Please enter a message',
      });
      return;
    }

    const userMessageText = inputMessage.trim();
    
    // Add user message
    const userMessage: Message = {
      id: `user-${Date.now()}`,
      content: userMessageText,
      isUser: true,
      timestamp: new Date().toISOString(),
    };

    setMessages(prev => [...prev, userMessage]);
    setInputMessage('');
    setIsLoading(true);

    // Create bot message ID
    const botMessageId = `bot-${Date.now()}`;

    // Prepare conversation history (exclude the current user message)
    const conversationHistory = messages.map(msg => ({
      authorRole: msg.isUser ? 'user' : 'bot',
      message: msg.content,
      timestamp: msg.timestamp,
    }));

    const streamingOptions = {
      authorId: 'test-user-456',
      conversationHistory,
      url: 'opensearch-dashboard-test',
    };

    // Callbacks for streaming
    const onToken = (token: string) => {
      console.log('[Component] Received token:', token);
      
      setMessages(prev => {
        // Find the bot message
        const botMsgIndex = prev.findIndex(msg => msg.id === botMessageId);
        
        if (botMsgIndex === -1) {
          // First token - add the bot message
          console.log('[Component] Adding bot message with first token');
          setIsLoading(false);
          return [
            ...prev,
            {
              id: botMessageId,
              content: token,
              isUser: false,
              timestamp: new Date().toISOString(),
            }
          ];
        } else {
          // Append token to existing message
          console.log('[Component] Appending token to existing message');
          const updated = [...prev];
          updated[botMsgIndex] = {
            ...updated[botMsgIndex],
            content: updated[botMsgIndex].content + token,
          };
          return updated;
        }
      });
    };

    const onComplete = () => {
      console.log('[Component] Stream completed');
      setIsLoading(false);
    };

    const onError = (error: string) => {
      console.error('[Component] Stream error:', error);
      setIsLoading(false);
      
      toast.open({
        type: 'error',
        title: 'Streaming Error',
        message: error,
      });
    };

    // Start streaming
    try {
      await startStreaming(userMessageText, streamingOptions, onToken, onComplete, onError);
    } catch (error) {
      console.error('[Component] Failed to start streaming:', error);
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
    stopStreaming();
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
                  <MessageContent content={msg.content} />
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
              value={inputMessage}
              onChange={(e) => setInputMessage(e.target.value)}
              onKeyDown={handleKeyPress}
              placeholder="Type your message here... (Press Enter to send, Shift+Enter for new line)"
              hideLabel
              maxRows={4}
              disabled={isLoading || isStreaming}
            />
            <Button
              onClick={handleSendMessage}
              disabled={isLoading || isStreaming || !inputMessage.trim()}
              className="test-production-llm__send-button"
            >
              {isLoading || isStreaming ? 'Sending...' : 'Send'}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default TestProductionLLM;