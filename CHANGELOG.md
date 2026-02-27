# CHANGELOG


## v0.1.1 (2026-02-27)

### Bug Fixes

- Use NEO4J_DATABASE env var instead of config dict for non-default database
  ([`74e1188`](https://github.com/elvismdev/mem0-mcp-selfhosted/commit/74e1188d38154846ec8b12602fde1d757197873b))

mem0ai's graph_memory.py passes config as positional args to Neo4jGraph() where pos 3 is `token`,
  not `database`. Setting database in the config dict causes it to land in the token parameter,
  resulting in AuthenticationError. Use NEO4J_DATABASE env var which langchain_neo4j reads via
  get_from_dict_or_env().

Upstream: mem0ai #3906, #3981, #4085 (none merged)

Resolves: PAR-57


## v0.1.0 (2026-02-27)

### Bug Fixes

- **ci**: Use angular parser compatible with PSR v9.15.2
  ([`b5bc6ab`](https://github.com/elvismdev/mem0-mcp-selfhosted/commit/b5bc6ab45edff26f07fc73774c7e0c57d22cb40d))

The v9 GitHub Action does not recognize "conventional" parser name (v10+ only). Reverts to "angular"
  and changelog.changelog_file format.

### Continuous Integration

- Add python-semantic-release configuration and GitHub Actions workflow
  ([`2473ee4`](https://github.com/elvismdev/mem0-mcp-selfhosted/commit/2473ee4ec9c0db90b2bb412d3714caae7dc41498))

Automated versioning via Conventional Commits analysis, changelog generation, git tagging
  (v{version}), and GitHub Release creation on push to main.
