const { Client } = require("@opensearch-project/opensearch");
const { openSearchConfig } = require("./config");
const { streamAzureOpenAIResponse } = require("./azureOpenAI");
const { activeConnections } = require("./connectionManager");
const streamQueue = require("./streamQueue");

let client = buildClient();

async function searchNotification({ channelId, connectionId, sender }) {
  try {
    const response = await client
      .search({
        index: openSearchConfig.notificationIndex,
        body: {
          query: {
            bool: {
              must: { match: { channelId } },
              must_not: { match: { sentTo: connectionId } },
            },
          },
          sort: { timestamp: { order: "asc" } },
        },
      })
      .catch(handleError);

    for (const hit of response.body.hits.hits) {
      const notification = hit._source;

      await sender(notification.payload);

      await markAsSent(hit, connectionId);
    }
  } catch (e) {
    console.error("processing notification error:", e);
    await sender({ error: "Notification processing failed" });
  }
}

async function createAzureOpenAIStreamRequest({ channelId, messages, options = {} }) {
  const { stream = true } = options;

  try {
    const connections = Array.from(activeConnections.entries()).filter(
      ([_, connData]) => connData.channelId === channelId
    );

    if (connections.length === 0) {
      const requestId = streamQueue.addToQueue(channelId, { messages, options });
      console.log(`No active connections for channel ${channelId}, queued request ${requestId}`);
    }

    const responsePromises = connections.map(async ([connectionId, connData]) => {
      const { sender } = connData;

      try {
        const response = await streamAzureOpenAIResponse(messages, options);

        if (!activeConnections.has(connectionId)) {
          return;
        }

        const openAIFallback1 = "The requested information is not found in the retrieved data. Please try another query or topic.";
        const openAIFallback2 = "The requested information is not available in the retrieved data. Please try another query or topic.";
        const estonianFallback = "Mulle kättesaadavates andmetes puudub teie küsimusele vastav info. Palun täpsustage oma küsimust.";

        if (stream) {
          sender({
            type: "stream_start",
            streamId: channelId,
            channelId,
          });

          let context;
          let cumulative = "";
          let startedStreaming = false;

          for await (const part of response) {
            if (!activeConnections.has(connectionId)) break;

            const choice = part.choices?.[0];
            if (!choice) continue;

            if (!context && choice.delta?.context) context = choice.delta.context;

            const content = choice.delta?.content;
            if (!content) continue;

            cumulative += content;

            if (!startedStreaming) {
              const isPrefixOfT1 = openAIFallback1.startsWith(cumulative);
              const isPrefixOfT2 = openAIFallback2.startsWith(cumulative);

              if (isPrefixOfT1 || isPrefixOfT2) continue;
              
              startedStreaming = true;

              sender({
                type: "stream_chunk",
                channelId,
                content: cumulative,
                isComplete: false,
              });
            } else {
              sender({
                type: "stream_chunk",
                channelId,
                content,
                isComplete: false,
              });
            }
          }

          if (activeConnections.has(connectionId)) {
            if (!startedStreaming) {
              const trimmed = cumulative.trim();
              if (trimmed === openAIFallback1 || trimmed === openAIFallback2) {
                sender({
                  type: "stream_chunk",
                  channelId,
                  content: estonianFallback,
                  isComplete: false,
                });
              }
            }

            sender({
              type: "stream_complete",
              channelId,
              content: "",
              context: context || {},
              isComplete: true,
            });
          }
        } else {
          let content = response.choices[0]?.message?.content || "";
          const context = response.choices[0]?.message?.context || {};

          const trimmed = content.trim();
          const isDefaultMessage = trimmed === openAIFallback1 || trimmed === openAIFallback2;

          if (isDefaultMessage) content = estonianFallback;
          
          sender({
            type: "complete_response",
            channelId,
            content: content,
            context,
            isComplete: true,
          });
        }
      } catch (error) {
        if (activeConnections.has(connectionId)) {
          const errorMessage = `Failed to ${stream ? "stream" : "generate"} response: ${error.message}`;
          sender({
            type: stream ? "stream_error" : "response_error",
            channelId,
            content: errorMessage,
            isComplete: true,
          });
        }
        throw error;
      }
    });

    await Promise.all(responsePromises);

    return {
      success: true,
      channelId,
      connectionsCount: connections.length,
      message: `Azure OpenAI ${stream ? "streaming" : "response"} completed for all connections`,
    };
  } catch (error) {
    console.error(`Error in createAzureOpenAIStreamRequest (stream=${stream}):`, error);
    throw error;
  }
}

async function createLLMOrchestrationStreamRequest({ channelId, message, options = {} }) {
  const connections = Array.from(activeConnections.entries()).filter(
    ([_, connData]) => connData.channelId === channelId
  );

  console.log("connections:", connections);

  if (connections.length === 0) {
    const requestId = streamQueue.addToQueue(channelId, { message, options });
    
    if (streamQueue.shouldRetry({ retryCount: 0 })) {
      throw new Error("No active connections found for this channel - request queued");
    } else {
      throw new Error("No active connections found for this channel");
    }
  }

  console.log(`Streaming LLM orchestration for channel ${channelId} to ${connections.length} connections`);

  try {
    const responsePromises = connections.map(async ([connectionId, connData]) => {
      const { sender } = connData;

      try {
        // Construct OrchestrationRequest payload
        const orchestrationPayload = {
          chatId: channelId,
          message: message,
          authorId: options.authorId || `user-${channelId}`,
          conversationHistory: options.conversationHistory || [],
          url: options.url || "sse-stream-context",
          environment: "production", // Streaming only works in production
          connection_id: options.connection_id || connectionId
        };

        console.log(`Calling LLM orchestration stream for channel ${channelId}`);

        // Call the LLM orchestration streaming endpoint
        const response = await fetch(`${process.env.LLM_ORCHESTRATOR_URL || 'http://llm-orchestration-service:8100'}/orchestrate/stream`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify(orchestrationPayload),
        });

        if (!response.ok) {
          throw new Error(`LLM Orchestration API error: ${response.status} ${response.statusText}`);
        }

        if (!activeConnections.has(connectionId)) {
          return;
        }

        // Send stream start notification
        sender({
          type: "stream_start",
          streamId: channelId,
          channelId,
          isComplete:false
        });

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
          if (!activeConnections.has(connectionId)) break;

          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop() || ''; // Keep the incomplete line in buffer

          for (const line of lines) {
            if (!line.trim()) continue;
            if (!line.startsWith('data: ')) continue;

            try {
              const data = JSON.parse(line.slice(6)); // Remove 'data: ' prefix
              const content = data.payload?.content;
              
              if (!content) continue;

              if (content === "END") {
                // Stream completed
                sender({
                  type: "stream_end",
                  streamId: channelId,
                  channelId,
                  isComplete:true
                });
                break;
              }

              // Regular token - send to client
              sender({
                type: "stream_chunk",
                content: content,
                streamId: channelId,
                channelId,
                isComplete:false
              });

            } catch (parseError) {
              console.error(`Failed to parse SSE data for channel ${channelId}:`, parseError, line);
            }
          }
        }

      } catch (error) {
        console.error(`Streaming error for connection ${connectionId}:`, error);
        if (activeConnections.has(connectionId)) {
          sender({
            type: "stream_error",
            error: error.message,
            streamId: channelId,
            channelId,
            isComplete:true
          });
        }
      }
    });

    await Promise.all(responsePromises);
    return { success: true, message: "Stream completed" };

  } catch (error) {
    console.error(`Error in createLLMOrchestrationStreamRequest:`, error);
    throw error;
  }
}

async function sendBulkNotification({ operations }) {
  await client.bulk({ body: operations });
}

async function markAsSent({ _index, _id }, connectionId) {
  await client.update({
    index: _index,
    id: _id,
    retry_on_conflict: openSearchConfig.retry_on_conflict,
    body: {
      script: {
        source: `if (ctx._source.sentTo == null) {
          ctx._source.sentTo = [params.connectionId];
        } else {
          ctx._source.sentTo.add(params.connectionId);
        }`,
        lang: "painless",
        params: { connectionId },
      },
    },
  });
}

async function enqueueChatId(chatId) {
  if (await findChatId(chatId)) return;

  await client.index({
    index: openSearchConfig.chatQueueIndex,
    body: {
      chatId,
      timestamp: Date.now(),
    },
    refresh: true,
  }).catch(handleError);
}

async function dequeueChatId(chatId) {
  await client.deleteByQuery({
    index: openSearchConfig.chatQueueIndex,
    body: {
      query: {
        match: {
          chatId: {
            query: chatId,
          },
        },
      },
    },
    refresh: true,
    conflicts: "proceed",
  }).catch(handleError);
}

async function findChatId(chatId) {
  const found = await isQueueIndexExists();
  if (!found) return null;

  const response = await client.search({
    index: openSearchConfig.chatQueueIndex,
    body: {
      query: {
        match: {
          chatId: {
            query: chatId,
          },
        },
      },
    },
  }).catch(handleError);

  if (response.body.hits.hits.length == 0) return null;

  return response.body.hits.hits[0]._source;
}

async function isQueueIndexExists() {
  const res = await client.indices.exists({
    index: openSearchConfig.chatQueueIndex,
  }).catch(handleError);
  return res.body;
}

async function findChatIdOrder(chatId) {
  const found = await findChatId(chatId);
  if (!found) return 0;

  const response = await client.search({
    index: openSearchConfig.chatQueueIndex,
    body: {
      query: {
        range: {
          timestamp: {
            lt: found.timestamp,
          },
        },
      },
      size: 0,
    },
  }).catch(handleError);

  return response.body.hits.total.value + 1;
}

function buildClient() {
  return new Client({
    node: openSearchConfig.getUrl(),
    ssl: openSearchConfig.ssl,
  });
}

function handleError(e) {
  if(e.name === 'ConnectionError')
    client = buildClient();
  throw e;
}

module.exports = {
  searchNotification,
  enqueueChatId,
  dequeueChatId,
  findChatIdOrder,
  sendBulkNotification,
  createAzureOpenAIStreamRequest,
  createLLMOrchestrationStreamRequest,
};
