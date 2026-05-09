# CLAUDE.md

Noosphere is a single-article web extraction, AI review, and SiYuan upload tool.

## Project Rules

- Read `README.md`, `SKILL.md`, and `UPDATE.md` before changing workflow behavior.
- Keep credentials, model settings, SiYuan targets, and prompt paths in local `config.json`; do not put tokens or API keys in command examples, tests, or committed files.
- Preserve the output boundary: `outputs/raw`, `outputs/reviewed`, `outputs/assets`, `outputs/manifests`, and `outputs/reviews`.
- Keep extraction single-URL first. Do not reintroduce batch behavior unless explicitly requested.
- Keep AI workflow settings under `ai`; keep provider credentials and model parameters under `ai_providers`.
- Keep long prompts in `prompts/`; keep `config.json.example` short and human-readable.
- Do not make provider-specific code paths for one vendor when the API shape is already OpenAI or Anthropic.
- Put deterministic Markdown invariants in normalization and validation code with tests. Examples: required review sections, local image paths, Markdown links instead of bare URLs, and completed review reports.
- Put platform-specific noise removal in `src/platforms/<platform>/rules.py` only when it is general across articles. Keep one-off observations in review reports or prompts until repeated.
- Upload should validate before writing to SiYuan and should preserve Markdown tables as Markdown.
- Do not edit `outputs/raw` during review. Review and AI rewrite should work on `outputs/reviewed`.
- Do not remove or rewrite user changes outside the requested scope.

## Verification

- Run focused tests for every behavior change.
- Run `pytest -q`, `python -m compileall src`, `python -m json.tool config.json.example`, and `git diff --check` before committing broad workflow changes.
- After upload workflow changes, test `python -m src.cli --help` and relevant subcommand help.

## Git

- Keep commits grouped by intent: implementation, docs, and small corrections separately.
- Never commit `config.json`, `outputs/`, API keys, SiYuan tokens, or generated caches.
