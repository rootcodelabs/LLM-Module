#!/usr/bin/env python3
"""
Loki Logger for Global Classifier
Sends logs directly to Loki API for centralized logging
"""

import json
import socket
import time
from datetime import datetime

import requests


class LokiLogger:
    """Simple logger that sends logs directly to Loki API"""

    def __init__(
        self, loki_url: str = "http://loki:3100", service_name: str = "default"
    ):
        """
        Initialize LokiLogger

        Args:
            loki_url: URL for Loki service (default: container URL in bykstack network)
            service_name: Name of the service for labeling logs
        """
        self.loki_url = loki_url
        self.service_name = service_name
        self.hostname = socket.gethostname()
        self.session = requests.Session()
        # Set default timeout for all requests
        self.timeout = 5

    def _send_to_loki(self, level: str, message: str):
        """Send log entry directly to Loki API"""
        try:
            # Create timestamp in nanoseconds (Loki requirement)
            timestamp_ns = str(int(time.time() * 1_000_000_000))

            # Prepare labels for Loki
            labels = {
                "service": self.service_name,
                "level": level,
                "hostname": self.hostname,
            }

            # Create log entry
            log_entry = {
                "timestamp": datetime.now().isoformat(),
                "level": level,
                "message": message,
                "hostname": self.hostname,
                "service": self.service_name,
            }

            # Prepare Loki payload
            payload = {
                "streams": [
                    {
                        "stream": labels,
                        "values": [[timestamp_ns, json.dumps(log_entry)]],
                    }
                ]
            }

            # Send to Loki (non-blocking, fire-and-forget)
            self.session.post(
                f"{self.loki_url}/loki/api/v1/push",
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=self.timeout,
            )

        except Exception:
            # Silently ignore logging errors to not affect main application
            pass

        # Also print to console for immediate feedback
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] {level: <8} | {message}")

    def info(self, message: str):
        self._send_to_loki("INFO", message)

    def error(self, message: str):
        self._send_to_loki("ERROR", message)

    def warning(self, message: str):
        self._send_to_loki("WARNING", message)

    def debug(self, message: str):
        self._send_to_loki("DEBUG", message)
