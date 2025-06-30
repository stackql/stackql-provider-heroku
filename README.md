# stackql-provider-heroku

This repository contains the tooling, code, and CI to build and test a [StackQL](https://github.com/stackql/stackql) provider for the [Heroku Platform API](https://devcenter.heroku.com/articles/platform-api-reference). It leverages the official [Heroku API JSON Schema](https://devcenter.heroku.com/articles/json-schema-for-platform-api) to generate OpenAPI-compatible service specifications with custom `x-stackQL-*` extensions.

---

## 📦 What this Repo Does

- Fetches the [Heroku Platform API schema](https://github.com/heroku/platform-api-schema)
- Converts the schema into modular OpenAPI 3.0 service specs
- Annotates each OpenAPI operation and schema with `x-stackQL-*` extensions
- Outputs a full StackQL provider manifest and service spec tree
- Includes CI tests to validate generated specs and example queries

---

## 📥 Getting the Heroku Platform API Schema

The Heroku Platform API is described using a machine-readable JSON schema hosted in GitHub.

### Step 1: Clone the Schema Repo

```bash
git clone https://github.com/heroku/platform-api-schema.git
cd platform-api-schema
````

This will provide access to the raw schema in:

```
schema-v3.json
```

### Step 2: Inspect the Schema

You can view `schema-v3.json` to see the top-level definitions. It's structured similarly to JSON Hyper-Schema with `links`, `href`, and `rel` describing endpoints and methods.

---

## 🔄 Convert Schema to StackQL-Compatible OpenAPI Specs

To convert this schema into StackQL-compatible service specs:

1. Use or build a Python/Node.js script to:

   * Parse each top-level Heroku resource (e.g., `app`, `addon`, `release`)
   * Convert each `href` and `method` into an OpenAPI `path` + `operation`
   * Extract request and response bodies into components
   * Add `x-stackQL-resource`, `x-stackQL-method`, and `x-stackQL-verb` to each operation

2. Group operations by **service** (e.g., `apps`, `addons`, `builds`) and output them to:

   ```
   provider/
   └── heroku/
       └── v0/
           └── services/
               ├── apps.yaml
               ├── addons.yaml
               └── builds.yaml
   ```

3. Generate a top-level provider manifest:

   ```yaml
   name: heroku
   version: v0
   services:
     - name: apps
       file: services/apps.yaml
     - name: addons
       file: services/addons.yaml
     # ...
   ```

---

## 🚧 Work in Progress

This repo is under active development. Planned work includes:

* JSON Schema → OpenAPI transformer
* StackQL extensions injector
* GitHub Actions CI for schema validation
* Unit tests for provider coverage
* Documentation and query examples

---

## 📚 References

* [Heroku Platform API Reference](https://devcenter.heroku.com/articles/platform-api-reference)
* [Heroku JSON Schema](https://github.com/heroku/platform-api-schema)
* [StackQL Provider Spec Guide](https://stackql.io/docs/provider_spec)
* [StackQL GitHub Repo](https://github.com/stackql/stackql)

---

## 👷‍♂️ Contributing

Contributions are welcome! Feel free to open issues, PRs, or feature suggestions.

