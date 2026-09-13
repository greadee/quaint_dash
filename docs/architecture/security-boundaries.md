# Security And Privacy Boundaries

## Trust Boundaries

| Boundary | Trusted Side | Less Trusted Side | Rules |
| --- | --- | --- | --- |
| Browser to API | API/server | Browser | Browser receives only authorized data and no provider keys. |
| Desktop to API/local service | Server/local trusted process | Desktop UI shell | Desktop may cache local data only with explicit config. |
| Mobile to API | API/server | Mobile app | Mobile payloads are minimal and never contain backend secrets. |
| API to Database | Server | Database file/process | Repository layer owns query shape and write permissions. |
| Workers to Providers | Server workers | External providers | Provider keys stay server-side; raw payloads are internal. |
| AI provider boundary | Server/desktop AI orchestrator | External AI provider | No sensitive portfolio/account data without explicit future consent. |
| Logs/reports | Server/local tooling | Developers/operators | Redact tokens, provider keys, account ids, and raw prompts. |

## Sensitive Data By Module

| Module | May Handle | Logging Rule |
| --- | --- | --- |
| Portfolio/Holdings | portfolio ids, holdings, valuations | Log ids/counts only unless debug fixture. |
| Transactions/Brokers | account details, transactions, broker profile keys | Redact account identifiers and tokens. |
| Provider Adapters | provider API keys, raw provider payloads | Never log secrets; sample payloads only in fixtures. |
| Operations | job ids, provider failures, readiness gaps | Safe operational counts; redact secrets. |
| AI Insights | prompts, evidence refs, generated text | Store prompt/template version and evidence ids, not raw sensitive prompts by default. |
| Web/Mobile/Desktop UI | authorized display data, local preferences | No provider keys or backend secrets. |

## AI Safety Rule

AI output is commentary. It must include evidence references and freshness, and
it must not overwrite deterministic metrics, readiness states, or provider data.

