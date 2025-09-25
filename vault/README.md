# HashiCorp Vault Setup for LLM Orchestration Service

This document explains how to set up and configure HashiCorp Vault for the LLM Orchestration Service, including Vault Agent for automatic token management.

## 🏗️ Architecture Overview

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────────┐
│   Vault Server  │    │   Vault Agent    │    │  LLM Orchestration  │
│                 │    │                  │    │      Service        │
│  - Storage      │◄───┤  - AppRole Auth  │◄───┤                     │
│  - Auth Methods │    │  - Token Sink    │    │  - Reads from       │
│  - KV v2 Engine │    │  - Auto Renewal  │    │    /run/vault/token │
│  - Policies     │    │                  │    │                     │
└─────────────────┘    └──────────────────┘    └─────────────────────┘
```

## 📋 Prerequisites

1. **Docker and Docker Compose** installed
2. **PowerShell** (Windows) or **Bash** (Linux/Mac)
3. **Network connectivity** between containers

## 🚀 Quick Start

### Step 1: Start Vault Server

```bash
# Start only the Vault server first
docker-compose up -d vault
```

### Step 2: Initialize and Configure Vault

**For Windows (PowerShell):**
```powershell
.\setup-vault.ps1
```

**For Linux/Mac (Bash):**
```bash
chmod +x setup-vault.sh
./setup-vault.sh
```

### Step 3: Start Vault Agent and LLM Service

```bash
# Start Vault Agent
docker-compose up -d vault-agent-llm

# Start LLM Orchestration Service
docker-compose up -d llm-orchestration-service
```

## 📁 Directory Structure

After setup, your vault directory will look like this:

```
vault/
├── config/
│   └── vault.hcl              # Vault server configuration
├── agents/
│   └── llm/
│       ├── agent.hcl          # Vault Agent configuration
│       ├── role_id            # AppRole role ID (auto-generated)
│       └── secret_id          # AppRole secret ID (auto-generated)
├── logs/                      # Vault server logs
└── .vault-token              # Root token (keep secure!)
```

## 🔐 Secret Schema

Secrets are stored in Vault using this path structure:

```
secret/llm-config/{provider}/{environment}/{model}
```

### Azure OpenAI Secret Example

**Path:** `secret/llm-config/azure-openai/production/gpt-4`

```json
{
  "connection_id": "azure-prod-gpt4",
  "model": "gpt-4", 
  "environment": "production",
  "endpoint": "https://your-azure-openai.openai.azure.com/",
  "api_key": "your-azure-api-key",
  "deployment_name": "gpt-4",
  "api_version": "2024-05-01-preview",
  "tags": ["production", "gpt-4"]
}
```

### AWS Bedrock Secret Example

**Path:** `secret/llm-config/aws-bedrock/production/claude-3`

```json
{
  "connection_id": "aws-prod-claude3",
  "model": "anthropic.claude-3-sonnet-20240229-v1:0",
  "environment": "production", 
  "region": "us-east-1",
  "access_key_id": "your-aws-access-key",
  "secret_access_key": "your-aws-secret-key",
  "tags": ["production", "claude-3"]
}
```

## 🔧 Manual Configuration

If you prefer to configure Vault manually, follow these steps:

### 1. Initialize Vault

```bash
# Initialize Vault (only needed once)
docker exec vault vault operator init -key-shares=1 -key-threshold=1

# Unseal Vault with the unseal key
docker exec vault vault operator unseal <UNSEAL_KEY>

# Login with root token
docker exec -e VAULT_TOKEN=<ROOT_TOKEN> vault vault auth
```

### 2. Enable Auth Methods and Secrets Engine

```bash
# Set root token
export VAULT_TOKEN=<ROOT_TOKEN>

# Enable AppRole authentication
docker exec -e VAULT_TOKEN=$VAULT_TOKEN vault vault auth enable approle

# Enable KV v2 secrets engine
docker exec -e VAULT_TOKEN=$VAULT_TOKEN vault vault secrets enable -version=2 -path=secret kv
```

### 3. Create Policy and AppRole

```bash
# Create policy for LLM service
docker exec -e VAULT_TOKEN=$VAULT_TOKEN vault vault policy write llm-policy - << 'EOF'
path "secret/data/llm-config/*" {
  capabilities = ["read"]
}
path "secret/metadata/llm-config/*" {
  capabilities = ["list", "read"]
}
EOF

# Create AppRole
docker exec -e VAULT_TOKEN=$VAULT_TOKEN vault vault write auth/approle/role/llm-service \
  token_policies="llm-policy" \
  token_ttl=1h \
  token_max_ttl=4h
```

### 4. Get AppRole Credentials

```bash
# Get role ID
docker exec -e VAULT_TOKEN=$VAULT_TOKEN vault vault read -field=role_id auth/approle/role/llm-service/role-id > ./vault/agents/llm/role_id

# Generate secret ID
docker exec -e VAULT_TOKEN=$VAULT_TOKEN vault vault write -field=secret_id auth/approle/role/llm-service/secret-id > ./vault/agents/llm/secret_id
```

## 🔍 Troubleshooting

### Common Issues

1. **"Vault Agent token file not found"**
   - Ensure Vault Agent is running: `docker-compose logs vault-agent-llm`
   - Check if token is being written: `docker exec vault-agent-llm ls -la /agent/out/`

2. **"Connection refused to vault:8200"**
   - Verify Vault server is running: `docker-compose ps vault`
   - Check Vault server logs: `docker-compose logs vault`

3. **"Permission denied" errors**
   - Verify AppRole credentials are correct
   - Check policy permissions in Vault UI

### Verification Commands

```bash
# Check Vault server status
docker exec vault vault status

# Check if secrets exist
docker exec -e VAULT_TOKEN=<ROOT_TOKEN> vault vault kv list secret/llm-config/

# Test AppRole authentication
docker exec vault vault write auth/approle/login \
  role_id=@/agent/in/role_id \
  secret_id=@/agent/in/secret_id
```

### Logs

```bash
# Vault server logs
docker-compose logs vault

# Vault Agent logs  
docker-compose logs vault-agent-llm

# LLM service logs
docker-compose logs llm-orchestration-service
```

## 🔒 Security Considerations

1. **Root Token**: Store securely and rotate regularly
2. **AppRole Credentials**: Auto-generated and rotated by Vault Agent
3. **Network**: Vault is only accessible within Docker network (no external ports)
4. **TLS**: In production, enable TLS for all Vault communications
5. **Policies**: Follow principle of least privilege

## 🎯 Production Deployment

For production environments:

1. **Enable TLS** in vault.hcl and agent.hcl
2. **Use external storage** (Consul, database) instead of Raft for HA
3. **Configure proper** backup and disaster recovery
4. **Set up monitoring** and alerting
5. **Implement proper** secret rotation policies
6. **Use Vault namespaces** for multi-tenancy

## 📚 Additional Resources

- [HashiCorp Vault Documentation](https://www.vaultproject.io/docs)
- [Vault Agent Documentation](https://www.vaultproject.io/docs/agent)
- [AppRole Auth Method](https://www.vaultproject.io/docs/auth/approle)
- [KV v2 Secrets Engine](https://www.vaultproject.io/docs/secrets/kv/kv-v2)