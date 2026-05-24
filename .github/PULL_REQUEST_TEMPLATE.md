## Summary

- 

## Type of change

- [ ] Bug fix
- [ ] Documentation
- [ ] Test coverage
- [ ] Docker/Compose
- [ ] OpenWebUI integration
- [ ] Other

## Validation

- [ ] `python -m py_compile src/codex_openai_bridge.py scripts/configure_openwebui_provider.py`
- [ ] `python -m unittest discover -s tests`
- [ ] `bash -n install.sh`
- [ ] `CODEX_BRIDGE_SECRET_FILE=/dev/null docker compose config`
- [ ] `docker build -t codex-openai-bridge:dev .`
- [ ] Not run; reason:

## Safety checklist

- [ ] No secrets, tokens, prompts, private paths, or personal data were added.
- [ ] Public endpoints, env vars, CLI flags, and defaults are unchanged unless explained above.
- [ ] README or docs were updated if behavior changed.
- [ ] Tests were added or updated for behavior changes.

## Notes for reviewers

- 
