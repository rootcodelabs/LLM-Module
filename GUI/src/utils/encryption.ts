/**
 * RSA Encryption Utility for LLM Connection Secrets
 * 
 * This module provides RSA encryption functionality using the Web Crypto API
 * to encrypt sensitive LLM credentials before storing them in HashiCorp Vault.
 */

// Import the public key - will be loaded at runtime
let publicKey: CryptoKey | null = null;

/**
 * Load the RSA public key from the server
 */
async function loadPublicKey(): Promise<CryptoKey> {
  if (publicKey) {
    return publicKey;
  }

  try {
    // Fetch the public key from the public directory
    const response = await fetch('/rsa_public_key.pem');
    if (!response.ok) {
      throw new Error(`Failed to load public key: ${response.status} ${response.statusText}`);
    }
    
    const pemText = await response.text();
    
    // Convert PEM to ArrayBuffer
    const pemHeader = '-----BEGIN PUBLIC KEY-----';
    const pemFooter = '-----END PUBLIC KEY-----';
    const pemContents = pemText
      .replace(pemHeader, '')
      .replace(pemFooter, '')
      .replace(/\s/g, '');
    
    const binaryDer = atob(pemContents);
    const binaryArray = new Uint8Array(binaryDer.length);
    for (let i = 0; i < binaryDer.length; i++) {
      binaryArray[i] = binaryDer.charCodeAt(i);
    }
    
    // Import the public key
    publicKey = await window.crypto.subtle.importKey(
      'spki',
      binaryArray.buffer,
      {
        name: 'RSA-OAEP',
        hash: 'SHA-256',
      },
      true,
      ['encrypt']
    );
    
    return publicKey;
  } catch (error) {
    console.error('Error loading public key:', error);
    throw new Error('Failed to load RSA public key for encryption');
  }
}

/**
 * Encrypt a string value using RSA-OAEP
 * @param value - The plaintext value to encrypt
 * @returns Base64-encoded encrypted value
 */
export async function encryptValue(value: string): Promise<string> {
  if (!value) {
    return '';
  }

  try {
    const key = await loadPublicKey();
    
    // Convert string to ArrayBuffer
    const encoder = new TextEncoder();
    const data = encoder.encode(value);
    
    // Encrypt the data
    const encryptedData = await window.crypto.subtle.encrypt(
      {
        name: 'RSA-OAEP',
      },
      key,
      data
    );
    
    // Convert to base64 for transmission
    const base64 = btoa(String.fromCharCode(...new Uint8Array(encryptedData)));
    return base64;
  } catch (error) {
    console.error('Error encrypting value:', error);
    throw new Error('Failed to encrypt sensitive data');
  }
}

/**
 * Encrypt an object containing sensitive credentials
 * @param credentials - Object with potentially sensitive string values
 * @returns Object with encrypted values (only encrypts non-empty string values)
 */
export async function encryptCredentials<T extends Record<string, any>>(
  credentials: T
): Promise<T> {
  const encrypted: any = { ...credentials };
  
  for (const key in credentials) {
    const value = credentials[key];
    // Only encrypt non-empty string values
    if (typeof value === 'string' && value.length > 0) {
      encrypted[key] = await encryptValue(value);
    }
  }
  
  return encrypted;
}

/**
 * Encrypt LLM credentials before sending to vault
 * @param credentials - The credentials object to encrypt
 */
export async function encryptLLMCredentials(credentials: {
  apiKey?: string;
  secretKey?: string;
  accessKey?: string;
  embeddingAccessKey?: string;
  embeddingSecretKey?: string;
  embeddingAzureApiKey?: string;
}): Promise<typeof credentials> {
  const encrypted: any = { ...credentials };
  
  // Encrypt AWS credentials
  if (credentials.secretKey) {
    encrypted.secretKey = await encryptValue(credentials.secretKey);
  }
  if (credentials.accessKey) {
    encrypted.accessKey = await encryptValue(credentials.accessKey);
  }
  
  // Encrypt Azure credentials
  if (credentials.apiKey) {
    encrypted.apiKey = await encryptValue(credentials.apiKey);
  }
  
  // Encrypt embedding AWS credentials
  if (credentials.embeddingAccessKey) {
    encrypted.embeddingAccessKey = await encryptValue(credentials.embeddingAccessKey);
  }
  if (credentials.embeddingSecretKey) {
    encrypted.embeddingSecretKey = await encryptValue(credentials.embeddingSecretKey);
  }
  
  // Encrypt embedding Azure credentials
  if (credentials.embeddingAzureApiKey) {
    encrypted.embeddingAzureApiKey = await encryptValue(credentials.embeddingAzureApiKey);
  }
  
  return encrypted;
}

/**
 * Check if a value appears to be encrypted (base64 encoded)
 * This is a simple heuristic check
 */
export function isEncrypted(value: string): boolean {
  if (!value || value.length === 0) {
    return false;
  }
  
  // Check if it looks like base64
  const base64Regex = /^[A-Za-z0-9+/]+={0,2}$/;
  return base64Regex.test(value) && value.length > 100; // Encrypted values should be reasonably long
}
