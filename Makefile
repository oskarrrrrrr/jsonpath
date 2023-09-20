.PHONY: lint
lint:
	black jsonpath
	ruff --fix jsonpath
	pyright jsonpath

.PHONY: lint-test
lint-test:
	black --check jsonpath
	ruff jsonpath
	pyright jsonpath

.PHONY: test
test:
	pytest jsonpath
