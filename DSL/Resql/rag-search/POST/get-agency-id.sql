SELECT 
    CASE 
        WHEN COUNT(*) > 0 THEN ARRAY_AGG(agency_id ORDER BY agency_id)
        ELSE NULL
    END as agency_ids,
    COUNT(*) > 0 as has_data
FROM public.agency_sync;