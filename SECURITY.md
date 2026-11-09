# Security policy

## Supported use

Enlaces+ only processes a single video URL that the service can access publicly. It does not accept cookies or user credentials and does not bypass logins, private-video restrictions, CAPTCHAs, DRM, paywalls, or other access controls.

## Service protection

- Keep `ENLACES_API_TOKEN` secret. Rotate it immediately if it is disclosed.
- All MCP HTTP requests to `/mcp` require a Bearer token.
- `/health` is intentionally public and returns no sensitive configuration.
- Configure the correct public hostname using `RENDER_EXTERNAL_HOSTNAME` or `MCP_ALLOWED_HOSTS`.
- Do not expose debug logs or environment variables.

## URL safety

The server accepts HTTPS only, rejects embedded credentials and non-standard ports, and rejects hostnames resolving to non-public IP addresses. Because yt-dlp follows provider redirects and resolves hosts independently, application-level DNS validation is not a complete SSRF boundary. A production operator should enforce outbound network restrictions at the hosting/network layer.

## Reporting

Do not publish secrets, access tokens, or private video URLs in issue reports. Use GitHub's private vulnerability reporting if it is enabled for this repository.
