# HashiCorp Vault Server Configuration
# Production-ready configuration for LLM Orchestration Service

# Storage backend - Raft for high availability
storage "raft" {
  path    = "/vault/file"
  node_id = "vault-node-1"
  
  # Retry join configuration for clustering (single node for now)
  retry_join {
    leader_api_addr = "http://vault:8200"
  }
}

# HTTP listener configuration
listener "tcp" {
  address       = "0.0.0.0:8200"
  tls_disable   = true
  
  # Enable CORS for web UI access
  cors_enabled = true
  cors_allowed_origins = [
    "http://localhost:8200",
    "http://vault:8200"
  ]
}

# Cluster listener for HA (required even for single node)
listener "tcp" {
  address       = "0.0.0.0:8201"
  cluster_addr  = "http://0.0.0.0:8201"
  tls_disable   = true
}

# API and cluster addresses
api_addr     = "http://vault:8200"
cluster_addr = "http://vault:8201"

# Security and performance settings
disable_mlock = true
disable_cache = false
ui            = true

# Default lease and maximum lease durations
default_lease_ttl = "168h"  # 7 days
max_lease_ttl     = "720h"  # 30 days

# Logging configuration
log_level = "INFO"
log_format = "json"

# Development settings (remove in production)
# Note: In production, you should not use dev mode
# and should properly initialize and unseal the vault