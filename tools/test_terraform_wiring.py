"""Le verificateur de cablage doit accepter le depot et detecter de vraies erreurs."""
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_terraform_wiring as checker  # noqa: E402

INFRA = Path(__file__).resolve().parent.parent / "infra"


def run(root):
    return checker.check(root)


def test_repository_is_consistent():
    errors, warnings = run(INFRA)
    assert errors == [] and warnings == []


def mutate(tmp_path, relative, old, new):
    copy = tmp_path / "infra"
    shutil.copytree(INFRA, copy)
    target = copy / relative
    text = target.read_text(encoding="utf-8")
    assert old in text
    target.write_text(text.replace(old, new, 1), encoding="utf-8")
    return copy


def test_undeclared_variable_is_detected(tmp_path):
    root = mutate(tmp_path, "modules/network/main.tf", "var.enable_ssh }", "var.enable_ssh_typo }")
    assert any("var.enable_ssh_typo" in e for e in run(root)[0])


def test_unknown_module_argument_is_detected(tmp_path):
    root = mutate(tmp_path, "modules/platform/main.tf", "  enable_https             = var.enable_https\n  enable_private",
                  "  enable_https             = var.enable_https\n  bogus_argument = 1\n  enable_private")
    assert any("bogus_argument" in e for e in run(root)[0])


def test_missing_required_variable_is_detected(tmp_path):
    root = mutate(tmp_path, "modules/platform/main.tf", "  allowed_ip               = var.allowed_ip\n", "")
    assert any("allowed_ip" in e and "obligatoire" in e for e in run(root)[0])


def test_unknown_module_output_is_detected(tmp_path):
    root = mutate(tmp_path, "modules/platform/outputs.tf", "module.compute.fqdn", "module.compute.fqdn_inexistant")
    assert any("fqdn_inexistant" in e for e in run(root)[0])


def test_undefined_resource_reference_is_detected(tmp_path):
    root = mutate(tmp_path, "modules/platform/main.tf", "azurerm_resource_group.this.id", "azurerm_resource_group.fantome.id")
    assert any("azurerm_resource_group.fantome" in e for e in run(root)[0])
