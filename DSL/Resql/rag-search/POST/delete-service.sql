UPDATE services
SET deleted = true,
    updated_at = :updated_at::timestamp with time zone
WHERE id = :id AND deleted = false;
