# Security policy and deployment boundaries

Report suspected vulnerabilities privately through GitHub private vulnerability reporting when available. Do not include credentials or real customer events in public issues.

Ledger Bridge is a reference reconciliation service. A passing test or scan does not qualify it for production use.

## Trust boundaries

Kafka producers and records are untrusted inputs. Validation, event-ID deduplication, and atomic Redis updates protect the reconciliation state within the documented retention window; they do not establish that a producer is authorized to make a business assertion. Restrict Kafka topic access and Redis access at the network and identity layers. Use TLS and least-privilege service credentials outside the local demo.

The API supports OIDC bearer verification and the console supports authorization-code sign-in with PKCE. Configure the issuer, audience, client, allowed origins, and redirect URI for your identity provider. The local demo configuration is not an authentication boundary for an Internet-facing deployment. A live identity provider has not been qualified.

Redis holds reconciliation state, including business payloads. Apply data minimization, retention policies, access controls, backup/restore verification, and encryption appropriate to the deployment. Expired deduplication/state records limit replay protection. Never place secrets in sample events, screenshots, logs, or issue reports.

## Dependency and code checks

CI runs Python and frontend tests, audits Python runtime dependencies and npm dependencies, runs CodeQL, and exercises the Docker Compose stack. Runtime Python dependencies are hash-locked in `service/requirements.lock`; the frontend uses `npm ci`. Audits detect known advisories and do not establish absence of vulnerabilities. Container images and cloud infrastructure require separate assessment.

AWS deployment, live identity-provider interoperability, production capacity, high availability, and disaster recovery remain unverified. The CI workload's observed latency and throughput are not production guarantees.
