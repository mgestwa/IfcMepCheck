# ifc-mep-checker

[![CI](https://github.com/mgestwa/IfcMepCheck/actions/workflows/ci.yml/badge.svg)](https://github.com/mgestwa/IfcMepCheck/actions/workflows/ci.yml)

`mepcheck` checks HVAC/MEP IFC models against a set of handover rules and reports the issues it finds.

> Status: work in progress. The full README (quickstart, rule table, architecture, design decisions) comes with `v0.1.0`.

## Development

```bash
conda create -n mepcheck -c conda-forge python=3.11 pip
conda activate mepcheck
pip install -e ".[dev,llm,mcp]"
ruff check . && ruff format --check .
pytest --cov=mepcheck
```

## LLM explanations

The rules decide what is an issue; the LLM only explains it. `mepcheck explain` adds an
`explanation` and a `suggested_fix` to each issue of a JSON report. Only the context of each
issue is sent (rule description, evidence, system, storey and, with `--ifc`, trimmed property
sets), never the model. Answers are validated against the issue ids, cached in
`.mepcheck_cache/`, and an LLM failure leaves the report without explanations.

```bash
pip install -e ".[llm]"
cp .env.example .env          # MEPCHECK_LLM_PROVIDER, MEPCHECK_LLM_MODEL, API key
mepcheck check model.ifc --json out/report.json
mepcheck explain out/report.json --lang en --ifc model.ifc --html out/report.html --bcf out/report.bcf
```

`MEPCHECK_LLM_PROVIDER` is `anthropic` (default model `claude-opus-5-5`) or `openai`
(set `MEPCHECK_LLM_MODEL`). `--max-issues` (default 50) caps how many issues are sent.

## MCP server

`mepcheck mcp` runs an MCP server over stdio with the tools `load_model`, `list_rules`,
`run_checks`, `get_issue`, `get_element`, `export_bcf` and `export_html`.

Claude Code:

```bash
claude mcp add mepcheck -- mepcheck mcp
```

Claude Desktop (`claude_desktop_config.json`; use the full path to `mepcheck` if it is not on `PATH`):

```json
{
  "mcpServers": {
    "mepcheck": { "command": "mepcheck", "args": ["mcp"] }
  }
}
```

Example conversation:

> **You:** Load samples/Clinic_HVAC.ifc with examples/clinic.yaml. Which air terminals in
> "Mechanical Supply Air 1" have no airflow?
>
> **Agent:** calls `load_model`, then `run_checks(rule_ids=["MEP-003"], system="Supply Air 1")`,
> and lists the terminals with their GlobalIds and storeys; `get_element` shows the property
> sets of a terminal, and `export_bcf` writes the topics for the viewer.

## Sample models

Models are never committed. `scripts/get_samples.py` downloads open sample models into
`samples/` and verifies their SHA-256:

```bash
python scripts/get_samples.py --list        # samples, sizes and attribution
python scripts/get_samples.py               # Building-Hvac (IFC2x3, IFC4, IFC4X3) and Duplex MEP
python scripts/get_samples.py clinic-hvac   # larger HVAC model (27 MB)
mepcheck check samples/Clinic_HVAC.ifc --config examples/clinic.yaml --html out/clinic.html
pytest -m sample                            # smoke tests on the downloaded models
```

All sample models are published under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/):

- Building-Hvac: (C) buildingSMART International Ltd., [buildingSMART/Sample-Test-Files](https://github.com/buildingSMART/Sample-Test-Files)
- Duplex Apartment and Medical-Dental Clinic: BSI (2020) "Duplex Apartment Test Files" and "Medical-Dental Test Files", buildingSMART International, [buildingsmart-community/Community-Sample-Test-Files](https://github.com/buildingsmart-community/Community-Sample-Test-Files)

## License

MIT
