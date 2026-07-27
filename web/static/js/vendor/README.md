# Vendored frontend dependencies

## alpine.min.js

- **Package:** [alpinejs](https://www.npmjs.com/package/alpinejs) v3.14.1 (`dist/cdn.min.js`, unmodified)
- **License:** MIT — Copyright (c) 2019-2025 Caleb Porzio and contributors
- **Source:** <https://github.com/alpinejs/alpine>

Vendored rather than loaded from a CDN so the dashboard has no external runtime
dependency: it renders on a locked-down network, survives a CDN outage, and
cannot be affected by a compromised third-party script. Flask serves it with a
one-hour cache header, so the 44KB is fetched once.

To update:

```bash
npm pack alpinejs@<version>
tar -xzf alpinejs-<version>.tgz
cp package/dist/cdn.min.js web/static/js/vendor/alpine.min.js
```
