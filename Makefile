.PHONY: test validate-scenarios quality-gate

test:
	PYTHONPATH=src python3 -m unittest discover -s tests -v

validate-scenarios:
	PYTHONPATH=src python3 examples/validate_scenarios.py

quality-gate:
	python3 scripts/quality_gate.py
