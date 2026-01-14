# BYK-RAG (Retrieval-Augmented Generation Module)

The **BYK-RAG Module** is part of the Burokratt ecosystem, designed to provide **retrieval-augmented generation (RAG)** capabilities for Estonian government digital services. It ensures reliable, multilingual, and compliant AI-powered responses by integrating with multiple LLM providers syncing with knowledge bases, and exposing flexible configuration and monitoring features for administrators.

---

## Features

- **Configurable LLM Providers**  
  - Support for AWS Bedrock, Azure AI, Google Cloud, OpenAI, Anthropic, and self-hosted open-source LLMs.  
  - Admins can create "connections" and switch providers/models without downtime.  
  - Models searchable via dropdown with cache-enabled indicators.

- **Enhanced Security with RSA Encryption**  
  - LLM credentials encrypted with RSA-2048 asymmetric encryption before storage.
  - GUI encrypts using public key; CronManager decrypts with private key.  
  - Additional security layer beyond HashiCorp Vault's encryption.  

- **Knowledge Base Integration**  
  - Continuous sync with central knowledge base (CKB).  
  - Last sync timestamp displayed in UI.  
  - LLMs restricted to answering only from CKB content.  
  - "I don't know" payload returned when confidence is low.  

- **Citations & Transparency**  
  - All responses are accompanied with **clear citations**.  

- **Analytics & Monitoring**  
  - External **Langfuse dashboard** for API usage, inference trends, cost analysis, and performance logs.  
  - Agencies can configure cost alerts and view alerts via LLM Alerts UI.  
  - Logs integrated with **Grafana Loki**.

### Storing Langfuse Secrets

1. **Generate API keys from Langfuse UI** (Settings → Project → API Keys)

2. **Copy the script to vault container:**
```bash
docker cp store-langfuse-secrets.sh vault:/tmp/store-langfuse-secrets.sh
```

3. **Execute the script with your API keys:**
```bash
docker exec -e LANGFUSE_INIT_PROJECT_PUBLIC_KEY=<your public key> \
            -e LANGFUSE_INIT_PROJECT_SECRET_KEY=<your secret key> \
            vault sh -c "chmod +x /tmp/store-langfuse-secrets.sh && /tmp/store-langfuse-secrets.sh"
```
