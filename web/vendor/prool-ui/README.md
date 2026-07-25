# Vendored Prool UI packages

These npm release artifacts make the web application independent of the shared UI working directory.

| Package | Version | SHA-256 |
| --- | --- | --- |
| `@prool-ui/react` | 0.1.0 | `93D94BE34F140608A255DBE630AE2D3E7A662C7A351BC77812DAF184F64CAA42` |
| `@prool-ui/themes` | 0.1.0 | `8BA7FB253719BA8977DA3F950D563A69F9CCD45E9CCE114E03DFBA062FC37FE6` |
| `@prool-ui/tokens` | 0.1.0 | `AC1EC67B8AAEA741807D2C0803CEC0C9EC441BF1DC69DD1EA655F80139CFB71D` |

Source release: shared UI `0.1.0` at commit `510c06e`.

Do not edit the archives or installed package contents. To upgrade:

1. validate and pack a new shared UI release;
2. add new versioned archives without overwriting the prior release;
3. update all three dependency paths and regenerate the lockfile;
