# Changelog

## 0.1.0 (2026-10-09)

First release.

- **Rules:** MEP-001 element without a system, MEP-003 missing required properties,
  MEP-004 open ports, MEP-005 missing insulation, MEP-006 connection between different
  systems, MEP-007 duplicate GlobalId and MEP-008 missing or wrong storey.
- **Model:** IFC2X3, IFC4 and IFC4X3; IFC2x3 elements are recognised through their type;
  coordinates are converted to metres.
- **Configuration:** YAML validated by pydantic, with errors reported as `file:line`;
  rules without configuration are skipped and listed; optional system names read from a
  property set for exports without `IfcSystem`.
- **Reports:** console, JSON, self-contained HTML with filters, and BCF 2.1 with one topic
  per issue, a viewpoint that selects the elements and stable topic GUIDs.
- **LLM:** `mepcheck explain` adds explanations and suggested fixes through Anthropic
  (default) or OpenAI, sends only the issue context, rejects answers for unknown issue ids
  and caches responses.
- **MCP:** `mepcheck mcp` serves `load_model`, `list_rules`, `run_checks`, `get_issue`,
  `get_element`, `export_bcf` and `export_html` over stdio.
- **Samples and CI:** `scripts/get_samples.py` downloads open CC BY 4.0 models; CI runs ruff,
  the tests on Python 3.11 to 3.13 and a regression test on the sample models.
