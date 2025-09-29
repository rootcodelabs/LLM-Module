SELECT 
    id,
    platform_key as value,
    platform_name as label
FROM embedding_platforms 
ORDER BY platform_name;