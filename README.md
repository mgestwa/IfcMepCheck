# ifc-mep-checker

[![CI](https://github.com/mgestwa/IfcMepCheck/actions/workflows/ci.yml/badge.svg)](https://github.com/mgestwa/IfcMepCheck/actions/workflows/ci.yml)

`mepcheck` checks HVAC/MEP IFC models against a set of handover rules and reports the issues it finds.

> Status: work in progress. The full README (quickstart, rule table, architecture, design decisions) comes with `v0.1.0`.

## Development

```bash
conda create -n mepcheck -c conda-forge python=3.11 pip
conda activate mepcheck
pip install -e ".[dev]"
ruff check . && ruff format --check .
pytest --cov=mepcheck
```

## License

MIT
