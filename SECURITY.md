# Security policy

## Reporting a vulnerability

Please report vulnerabilities privately through GitHub's private vulnerability
reporting feature. Do not open a public issue containing credentials, personal
data, or exploit details.

## Operational safety

Jarvis can simulate keyboard input, inspect local files, control applications,
access cameras and microphones, and communicate with connected hardware. Run it
only under a dedicated, least-privileged user account and connect only trusted MCP
clients.

Keep `.env`, biometric material, recordings, generated encodings, logs, and runtime
state private. Rotate any credential that is accidentally committed or logged;
removing it from the latest commit is not sufficient.
