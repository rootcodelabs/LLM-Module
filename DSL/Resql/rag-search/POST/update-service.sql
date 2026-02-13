UPDATE services 
SET 
    name = :name,
    description = :description,
    service_id = :service_id,
    ruuter_type = :ruuter_type::ruuter_request_type,
    current_state = :current_state::service_state,
    is_common = :is_common,
    slot = :slot,
    entities = ARRAY[:entities]::text[],
    examples = ARRAY[:examples]::text[],
    structure = :structure::json,
    endpoints = :endpoints::json,
    updated_at = :updated_at::timestamp with time zone
WHERE id = :id
RETURNING
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
    updated_at;
