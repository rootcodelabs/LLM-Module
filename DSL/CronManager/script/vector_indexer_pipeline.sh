#!/bin/bash

# Check if environment variable is set
if [ -z "$signedUrls" ] || [ -z "$datasetId" ] || [ -z "$majorVersion" ] || [ -z "$minorVersion" ]; then
  echo "Please set the signedUrls, datasetId, majorVersion, minorVersion environment variables."
  exit 1
fi

# Logging function
log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}