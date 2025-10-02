SELECT 
    id,
    platform_key as value,
    platform_name as label
FROM llm_platforms 
ORDER BY platform_name;