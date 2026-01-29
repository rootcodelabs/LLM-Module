UPDATE prompt_configuration
SET prompt = :prompt
WHERE id = :id
RETURNING id, prompt
