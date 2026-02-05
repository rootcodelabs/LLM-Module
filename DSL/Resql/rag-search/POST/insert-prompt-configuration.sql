INSERT INTO prompt_configuration (prompt)
VALUES (:prompt)
RETURNING id, prompt
