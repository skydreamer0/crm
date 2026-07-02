import importlib
import sys
from pathlib import Path


def test_visit_list_parser_uses_pyinstaller_config_dir(monkeypatch, tmp_path):
    bundle_dir = tmp_path / "_internal"
    config_dir = bundle_dir / "config"
    config_dir.mkdir(parents=True)
    (config_dir / "department_mapping.yaml").write_text(
        """
departments:
  URO:
    name_zh: Urology
    aliases:
      - URO
    products:
      - uri
""".strip(),
        encoding="utf-8",
    )
    (config_dir / "product_catalog.yaml").write_text(
        """
products:
  uri:
    brand_name: URI
""".strip(),
        encoding="utf-8",
    )

    monkeypatch.setattr(sys, "_MEIPASS", str(bundle_dir), raising=False)
    sys.modules.pop("visit_list_parser", None)

    module = importlib.import_module("visit_list_parser")

    assert module._CONFIG_DIR == config_dir
    assert module.DEPARTMENT_MAP["URO"]["products"] == ["uri"]
    assert module.PRODUCT_CATALOG["uri"]["brand_name"] == "URI"
