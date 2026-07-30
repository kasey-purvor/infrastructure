# MCP Server Architecture: Key Discoveries (January 2026)

## Critical Architectural Insight: Transport Determines Deployment Model

### The Fundamental Split: stdio vs HTTP

**Local stdio servers (Claude Desktop, Claude Code CLI):**
- MUST be long-running processes
- Spawned as child processes when client launches
- Persistent bidirectional JSON-RPC over stdin/stdout pipes
- Session state maintained in memory
- Configuration: `command` + `args` in JSON config
- Common deployment: Docker containers, local executables
- **Cannot be accessed remotely**

**Remote HTTP servers (Mobile, Web, Cloud):**
- Can be stateless serverless functions (Lambda, Cloudflare Workers, Cloud Run)
- Each request is independent (like REST APIs)
- Introduced with "Streamable HTTP" transport (March 2025)
- Replaces older HTTP+SSE which required persistent connections
- Perfect for API wrapper pattern
- **Only way to support mobile apps**

## The Serverless Revolution (March 2025)

### Streamable HTTP Changes Everything

Prior to March 2025, remote MCP used HTTP+SSE transport:
- Required two separate endpoints (/sse and /messages)
- Long-lived connections necessary
- Stateful, difficult to scale
- Not compatible with serverless environments

**New Streamable HTTP transport:**
- Single endpoint for all communication
- **Stateless mode supported**: `stateless: true`
- Optional session management via `Mcp-Session-Id` header
- Optional SSE for streaming (but not required)
- Perfect for serverless deployments

### Stateless MCP Server Pattern

```typescript
const transport = new StreamableHTTPServerTransport("/mcp", {
  stateless: true  // No session persistence required
});
```

**Key characteristics:**
- Request arrives → Function wakes up → Processes → Returns → Dies
- Identical to REST API pattern
- State stored externally (DynamoDB, Redis) if needed
- No persistent connections required for basic tool calling

## MCP Server as API Wrapper

### The Universal Pattern

For services with existing APIs (Google Docs, Todoist, Notion):

```
User → Claude (client) 
  → MCP Server (translation layer)
    → Third-party API (Google Docs, etc.)
      → Response back through chain
```

**MCP server responsibilities:**
1. Receive MCP protocol requests
2. Translate to target API calls
3. Handle authentication (OAuth, API keys)
4. Translate responses back to MCP format
5. Return via HTTP

**No persistent state needed** - each call is independent.

## Mobile App Limitations

**Critical constraint:** Claude mobile apps cannot run local MCP servers.

**Why:**
- Platform sandboxing prevents filesystem access
- Cannot execute scripts or spawn processes
- No stdio transport support
- Must use cloud-hosted HTTP servers

**Workflow:**
1. Configure servers at claude.ai (desktop browser)
2. Settings sync automatically to mobile
3. All servers must be remote HTTP endpoints

## Deployment Options Comparison

### Serverless (Stateless HTTP)

**AWS Lambda:**
- Cold starts: ~100-500ms (with Firecracker microVMs)
- Pricing: Pay per request
- Best for: Infrequent use, API wrappers
- Session state: Store in DynamoDB

**Cloudflare Workers:**
- Cold starts: ~0ms (V8 isolates)
- Pricing: 100k requests/day free
- Best for: Global edge deployment, low latency
- Session state: Workers KV, Durable Objects

**Google Cloud Run:**
- Cold starts: ~200-800ms
- Pricing: Pay per request, 2M requests/month free
- Best for: Containerized apps, Google Cloud ecosystem
- Session state: Firestore, Cloud Storage

### Long-Running Servers (Stateful HTTP)

**Amazon ECS/Fargate:**
- Persistent containers
- Session state in memory
- SSE streaming support
- Requires sticky sessions for load balancing

**Google Cloud Run (always-on):**
- Min instances: 1+
- No cold starts
- More expensive but predictable latency

**Self-hosted (VPS/Home Server):**
- Full control
- Requires reverse proxy/tunnel for remote access
- Good for development/testing

## When to Use Each Pattern

### Use Serverless (Stateless) When:
- Wrapping external APIs (Google Docs, Todoist, etc.)
- Simple request/response tools
- Mobile access required
- Cost optimization important
- Unpredictable traffic patterns
- Global deployment needed

### Use Long-Running When:
- Expensive initialization (ML models)
- Heavy caching requirements
- True streaming responses needed (SSE)
- WebSocket-like bidirectional communication
- Local-only development/tools

## Cloud Hosting Options

### Cloudflare Workers
- One-click MCP templates available
- Built-in OAuth via workers-oauth-provider
- Free tier: 100k requests/day
- ~0ms cold starts globally
- Example: Atlassian MCP server runs on this

### Google Cloud Run
- Official Google MCP servers use this
- Container or source deployment
- IAM-based authentication
- 2M requests/month free

### Azure Container Apps
- Microsoft samples available
- Consumption-based pricing
- Native SSE support
- Integration with Azure services

### Higress (Alibaba)
- Open-source gateway
- MCP session persistence
- OAuth2, audit logging, rate limiting
- Good for enterprise deployments

## Tunneling for Local Servers

### For exposing local servers to mobile:

**ngrok:**
```bash
ngrok http --basic-auth 'user:pass' 8080
# Output: https://abc123.ngrok-free.app
```

**Cloudflare Tunnel:**
```bash
cloudflared tunnel create my-mcp-tunnel
cloudflared tunnel run my-mcp-tunnel
```

**stdio to HTTP bridging:**
```bash
mcp-proxy --sse-port 8080 -- python my_stdio_server.py
```

## Security Best Practices

1. **Authentication:**
   - OAuth 2.1 with PKCE for user-facing apps
   - Bearer tokens for service-to-service
   - API key authentication for simple cases

2. **Network Security:**
   - Validate Origin headers (prevent DNS rebinding)
   - Bind to localhost for local servers
   - Use HTTPS for all remote endpoints

3. **Rate Limiting:**
   - Essential for public endpoints
   - Built into most cloud platforms
   - Can use API Gateway for additional protection

4. **Token Management:**
   - Short-lived access tokens
   - Refresh token rotation
   - Store secrets in environment variables

## The MCP Registry and Discovery

**Official Registry:** registry.modelcontextprotocol.io (launched Sept 2025)

**Community Resources:**
- github.com/wong2/awesome-mcp-servers
- smithery.ai (one-click installations)
- mcpservers.org (curated listings)

## Claude Code Specifics

**How it spawns servers:**
- stdio: Child processes via `command` + `args`
- HTTP: Standard HTTP requests to remote endpoints

**Built-in capabilities:**
- WebSearch and WebFetch (server-side tools)
- Not available on Bedrock/Vertex deployments

**Configuration scopes:**
1. Local: `.mcp.json` in project root
2. User: `~/.claude.json` for personal servers
3. Project: Team-shared, version-controlled

**No cloud version** that works differently - the web version (claude.ai/code) runs in cloud sandboxes but uses same protocol.

## Current State (January 2026)

### What Works Today:

✅ Stateless HTTP MCP servers on Lambda/Workers/Cloud Run
✅ Mobile app access via remote servers configured at claude.ai
✅ Claude Code with both local stdio and remote HTTP servers
✅ Official servers: Todoist, Notion, Asana, Atlassian, Slack (announced)
✅ Pre-built connectors in Claude: Asana, Jira, Confluence, Linear, PayPal, Sentry, Zapier

### Ecosystem Maturity:

- TypeScript SDK: Full Streamable HTTP support (v1.10.0+, April 2025)
- Python SDK: Full support via FastMCP and official SDK
- Community: Rapidly growing with hundreds of servers
- Documentation: Comprehensive at modelcontextprotocol.io

### Common Pitfalls:

❌ Trying to run stdio servers remotely (impossible)
❌ Not understanding stateless vs stateful implications
❌ Assuming mobile can run local servers
❌ Using deprecated HTTP+SSE transport
❌ Not implementing proper authentication for public endpoints

## Recommended Architecture for Cross-Platform Access

**Scenario: Want MCP access on mobile, desktop, and Claude Code**

**Option 1: All Cloud (Simplest)**
- Deploy custom MCP servers to Cloudflare Workers/Lambda
- Use pre-built connectors where available
- Configure once at claude.ai
- Automatic sync across all platforms

**Option 2: Hybrid (Maximum Control)**
- Cloud-hosted servers for mobile access
- Local stdio servers for desktop-only features
- Same servers exposed via both methods where needed

**Option 3: Self-Hosted with Tunnel**
- Run servers locally with Streamable HTTP transport
- Expose via Cloudflare Tunnel
- Configure tunnel URL as custom connector
- Desktop can use either local or remote

## Key Takeaway

**MCP servers wrapping APIs should be serverless functions.** The "constantly running Docker container" pattern is only necessary for:
1. Local stdio transport (required by protocol)
2. Optional for HTTP if you need SSE streaming or heavy caching
3. Legacy HTTP+SSE transport (now deprecated)

The ecosystem has fully embraced stateless HTTP as the standard for remote servers, enabling true serverless deployments at scale.
