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
