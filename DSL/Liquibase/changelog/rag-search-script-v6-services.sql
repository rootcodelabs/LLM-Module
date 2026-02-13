-- changeset Erangi Ariyasena:rag-script-v6-changeset1

-- Custom types used:
CREATE TYPE ruuter_request_type AS ENUM ('GET', 'POST');
CREATE TYPE service_state AS ENUM ('active', 'inactive', 'draft');

CREATE TABLE public.services (
  -- Primary key
  id SERIAL PRIMARY KEY,
  
  -- Basic service information
  name TEXT NOT NULL,
  description TEXT NOT NULL,
  service_id TEXT NOT NULL UNIQUE, 
  
  -- Service classification
  ruuter_type ruuter_request_type DEFAULT 'GET',  -- ENUM: 'GET' or 'POST'
  current_state service_state DEFAULT 'draft',    -- ENUM: 'active', 'inactive', 'draft'
  is_common BOOLEAN NOT NULL DEFAULT FALSE,
  
  -- Intent classification data (for LLM)
  slot TEXT NOT NULL DEFAULT '',
  entities text[] NOT NULL DEFAULT '{}',
  examples text[] NOT NULL DEFAULT '{}',
  
  -- Service configuration
  structure JSON NOT NULL DEFAULT '{}',
  endpoints JSON NOT NULL DEFAULT '[]',
  
  -- Timestamps
  created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create index for unique service_id for faster lookups
CREATE UNIQUE INDEX idx_services_service_id ON public.services(service_id);

