# Production Architecture (Updated 2026-11-23)

## Native ADK Model Integration
The defining change to the architecture was upgrading the foundational orchestrator loop to leverage native Google ADK abstractions:
- **`ADKModelGateway(BaseLlm)`**: Binds all legacy HTTP interactions, error boundaries, rate limit checks, and logging logic directly behind ADK's `BaseLlm` object.
- **Workflow State Engine**: Native `@node` functionality processes sequential application phases. By adopting the `BaseLlm` gateway, nodes construct and process `LlmRequest` and `LlmResponse` schemas precisely as ADK was designed to operate. 
- **Voice Intercepts**: Strictly constrained sub-200ms model-invocation boundaries on voice ensure that the 1.5s TTFA target SLA is reliably met.

See the complete diagram and latency breakdown in the initial architecture documents (`ARCHITECTURE.md`).