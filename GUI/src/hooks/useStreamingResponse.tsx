import { useState, useRef, useCallback, useEffect } from 'react';
import axios from 'axios';
import { ChoiceButton } from 'services/inference';

const getNotificationNodeUrl = (): string => {
  const value = import.meta.env.REACT_APP_NOTIFICATION_NODE_URL;
  if (!value) {
    throw new Error(
      'Environment variable REACT_APP_NOTIFICATION_NODE_URL is not defined. ' +
        'Please set it to the base URL of the notification service to enable streaming responses.'
    );
  }
  return value;
};
const notificationNodeUrl = getNotificationNodeUrl();
console.log(notificationNodeUrl);

interface StreamingOptions {
  authorId: string;
  conversationHistory: Array<{ authorRole: string; message: string; timestamp: string }>;
  url: string;
}

interface UseStreamingResponseReturn {
  startStreaming: (message: string, options: StreamingOptions, onToken: (token: string) => void, onComplete: () => void, onError: (error: string) => void, onButtons?: (buttons: ChoiceButton[]) => void) => Promise<void>;
  stopStreaming: () => void;
  isStreaming: boolean;
}

export const useStreamingResponse = (channelId: string): UseStreamingResponseReturn => {
  const [isStreaming, setIsStreaming] = useState(false);
  const eventSourceRef = useRef<EventSource | null>(null);

  const stopStreaming = useCallback(() => {
    if (eventSourceRef.current) {
      console.log('[SSE] Closing connection');
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }
    setIsStreaming(false);
  }, []);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
      }
    };
  }, []);

  const startStreaming = useCallback(
    async (
      message: string,
      options: StreamingOptions,
      onToken: (token: string) => void,
      onComplete: () => void,
      onError: (error: string) => void,
      onButtons?: (buttons: ChoiceButton[]) => void
    ) => {
      console.log('[SSE] Starting streaming for channel:', channelId);
      
      // Close any existing connection
      stopStreaming();

      try {
        // Step 1: Open SSE connection FIRST
        const sseUrl = `${notificationNodeUrl}/sse/stream/${channelId}`;
        console.log('[SSE] Connecting to:', sseUrl);

        const eventSource = new EventSource(sseUrl);
        eventSourceRef.current = eventSource;

        eventSource.onopen = () => {
          console.log('[SSE] Connection opened');
        };

        eventSource.onmessage = (event) => {
          console.log('[SSE] Message received:', event.data);

          try {
            const data = JSON.parse(event.data);

            if (data.type === 'stream_start') {
              console.log('[SSE] Stream started');
              setIsStreaming(true);
            } else if (data.type === 'stream_chunk' && data.content) {
              console.log('[SSE] Token:', data.content);
              onToken(data.content);
              if (data.buttons && data.buttons.length > 0 && onButtons) {
                onButtons(data.buttons);
              }
            } else if (data.type === 'stream_end') {
              console.log('[SSE] Stream ended');
              setIsStreaming(false);
              eventSource.close();
              eventSourceRef.current = null;
              onComplete();
            } else if (data.type === 'stream_error') {
              console.error('[SSE] Stream error:', data.error);
              setIsStreaming(false);
              eventSource.close();
              eventSourceRef.current = null;
              onError(data.error || 'Stream error occurred');
            }
          } catch (e) {
            console.error('[SSE] Failed to parse message:', e);
          }
        };

        eventSource.onerror = (err) => {
          console.error('[SSE] Connection error:', err);
          setIsStreaming(false);
          eventSource.close();
          eventSourceRef.current = null;
          onError('Connection error');
        };

        // Step 2: Wait a moment for SSE connection to establish, then trigger the stream
        await new Promise(resolve => setTimeout(resolve, 500));

        // Step 3: POST to trigger streaming
        const postUrl = `${notificationNodeUrl}/channels/${channelId}/orchestrate/stream`;
        console.log('[API] Triggering stream:', postUrl);

        await axios.post(postUrl, {
          message,
          options,
        });

        console.log('[API] Stream triggered successfully');

      } catch (err) {
        console.error('[SSE] Error starting stream:', err);
        stopStreaming();
        onError(err instanceof Error ? err.message : 'Failed to start streaming');
      }
    },
    [channelId, stopStreaming]
  );

  return {
    startStreaming,
    stopStreaming,
    isStreaming,
  };
};

