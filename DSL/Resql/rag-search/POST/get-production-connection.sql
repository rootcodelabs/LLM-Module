SELECT 
    id,
    connection_name,
    used_budget,
    monthly_budget,
    warn_budget_threshold,
    stop_budget_threshold,
    environment,
    connection_status,
    created_at,
    llm_platform,
    llm_model,
    embedding_platform,
    embedding_model
FROM llm_connections
WHERE environment = 'production'
  AND connection_status <> 'deleted'
ORDER BY created_at DESC
LIMIT 1;