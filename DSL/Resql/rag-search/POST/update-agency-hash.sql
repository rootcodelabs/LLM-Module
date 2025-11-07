UPDATE public.agency_sync 
SET 
    agency_data_hash = :newAgencyDataHash,
    updated_at = NOW()
WHERE agency_id = :agencyId
RETURNING 
    agency_id,
    agency_data_hash,
    updated_at;
