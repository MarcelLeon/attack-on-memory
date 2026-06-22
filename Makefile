.PHONY: test validate-scenarios policy-check north-star replay-benchmark status qualify-runtime check-runtime-qualification quality-gate

PYTHON ?= python3

test:
	PYTHONPATH=src $(PYTHON) -m unittest discover -s tests -v

validate-scenarios:
	PYTHONPATH=src $(PYTHON) examples/validate_scenarios.py

policy-check:
	PYTHONPATH=src $(PYTHON) scripts/policy_check.py

north-star:
	PYTHONPATH=src $(PYTHON) scripts/north_star_report.py

replay-benchmark:
	PYTHONPATH=src $(PYTHON) scripts/run_replay_benchmark.py

status:
	PYTHONPATH=src $(PYTHON) scripts/project_status.py

qualify-runtime:
	@test -n "$(WORKDIR)" -a -n "$(OUTPUT)" -a -n "$(PROFILE)" -a -n "$(ENVIRONMENT)" || \
		(echo "Set WORKDIR, OUTPUT, PROFILE, and ENVIRONMENT"; exit 2)
	PYTHONPATH=src $(PYTHON) scripts/qualify_runtime.py \
		--workdir "$(WORKDIR)" --output "$(OUTPUT)" \
		--profile-id "$(PROFILE)" --environment "$(ENVIRONMENT)" $(QUALIFY_ARGS)

check-runtime-qualification:
	PYTHONPATH=src $(PYTHON) scripts/check_runtime_qualification.py

quality-gate:
	$(PYTHON) scripts/quality_gate.py
