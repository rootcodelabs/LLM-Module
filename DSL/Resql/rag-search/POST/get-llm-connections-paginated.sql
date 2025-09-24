SELECT 
    id,
    llm_platform,
    llm_model,
    embedding_platform,
    embedding_model,
    monthly_budget,
    environment,
    connection_status,
    created_at,
    CEIL(COUNT(*) OVER() / :page_size::DECIMAL) AS totalPages
FROM llm_connections
WHERE connection_status <> 'deleted'
ORDER BY
    CASE WHEN :sorting = 'llm_platform asc' THEN llm_platform END ASC,
    CASE WHEN :sorting = 'llm_platform desc' THEN llm_platform END DESC,
    CASE WHEN :sorting = 'llm_model asc' THEN llm_model END ASC,
    CASE WHEN :sorting = 'llm_model desc' THEN llm_model END DESC,
    CASE WHEN :sorting = 'embedding_platform asc' THEN embedding_platform END ASC,
    CASE WHEN :sorting = 'embedding_platform desc' THEN embedding_platform END DESC,
    CASE WHEN :sorting = 'embedding_model asc' THEN embedding_model END ASC,
    CASE WHEN :sorting = 'embedding_model desc' THEN embedding_model END DESC,
    CASE WHEN :sorting = 'monthly_budget asc' THEN monthly_budget END ASC,
    CASE WHEN :sorting = 'monthly_budget desc' THEN monthly_budget END DESC,
    CASE WHEN :sorting = 'environment asc' THEN environment END ASC,
    CASE WHEN :sorting = 'environment desc' THEN environment END DESC,
    CASE WHEN :sorting = 'status asc' THEN connection_status END ASC,
    CASE WHEN :sorting = 'status desc' THEN connection_status END DESC,
    CASE WHEN :sorting = 'created_at asc' THEN created_at END ASC,
    CASE WHEN :sorting = 'created_at desc' THEN created_at END DESC,
    created_at DESC  -- Default fallback sorting
OFFSET ((GREATEST(:page, 1) - 1) * :page_size) LIMIT :page_size;
