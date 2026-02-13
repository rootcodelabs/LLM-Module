SELECT 
    id,
    name,
    description,
    service_id,
    ruuter_type,
    current_state,
    is_common,
    slot,
    entities,
    examples,
    structure,
    endpoints,
    created_at,
    updated_at
FROM services
WHERE id = :id;
