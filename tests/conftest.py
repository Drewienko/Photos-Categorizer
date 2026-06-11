import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--vision",
        action="store_true",
        default=False,
        help="Run Google Vision API tests (uses API quota)",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if config.getoption("--vision"):
        return
    skip = pytest.mark.skip(reason="Vision API tests skipped by default — use --vision to run")
    for item in items:
        if "vision" in item.keywords:
            item.add_marker(skip)
