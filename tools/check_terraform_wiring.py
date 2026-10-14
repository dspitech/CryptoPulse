"""Verification statique du cablage Terraform, sans acces aux registres de providers.

Complete `terraform validate` (qui reste la reference, executee en CI) en detectant localement :
variables ou locals utilises mais non declares, arguments de module inconnus ou manquants,
sorties de module inexistantes, references a des ressources ou data sources non definis.

Usage : python tools/check_terraform_wiring.py [dossier_infra]
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

META_ARGS = {"source", "count", "for_each", "depends_on", "providers", "version"}
RESOURCE_PREFIXES = ("azurerm_", "random_", "tls_", "time_", "archive_", "cloudinit_", "terraform_data")


# --------------------------------------------------------------------------- analyse lexicale
def strip_comments(text: str) -> str:
    out, i, n = [], 0, len(text)
    while i < n:
        c = text[i]
        if c == '"':
            j = skip_string(text, i)
            out.append(text[i:j])
            i = j
        elif c == "#" or text.startswith("//", i):
            while i < n and text[i] != "\n":
                i += 1
        elif text.startswith("/*", i):
            i = text.find("*/", i) + 2
        else:
            out.append(c)
            i += 1
    return "".join(out)


def skip_string(text: str, i: int) -> int:
    """i pointe sur le guillemet ouvrant ; retourne l'index apres le guillemet fermant."""
    i += 1
    while i < len(text):
        c = text[i]
        if c == "\\":
            i += 2
        elif text.startswith("${", i) or text.startswith("%{", i):
            i = skip_braces(text, i + 1)
        elif c == '"':
            return i + 1
        else:
            i += 1
    raise ValueError("chaine non terminee")


def skip_braces(text: str, i: int) -> int:
    """i pointe sur '{' ; retourne l'index apres l'accolade fermante correspondante."""
    depth = 0
    while i < len(text):
        c = text[i]
        if c == '"':
            i = skip_string(text, i)
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    raise ValueError("accolade non fermee")


def expression_text(text: str) -> str:
    """Retire le texte litteral des chaines mais conserve le contenu des interpolations ${...}.
    Evite de confondre un chemin comme "docker-compose.local.yml" avec une reference local.yml."""
    out, i, n = [], 0, len(text)
    while i < n:
        if text[i] == '"':
            j = skip_string(text, i)
            literal = text[i:j]
            for m in re.finditer(r"\$\{", literal):
                end = skip_braces(literal, m.end() - 1)
                out.append(" " + literal[m.end(): end - 1] + " ")
            out.append('""')
            i = j
        else:
            out.append(text[i])
            i += 1
    return "".join(out)


BLOCK_RE = re.compile(r'^(variable|output|resource|data|module|locals)\b([^\n{]*)\{', re.MULTILINE)


def parse_blocks(text: str):
    """Retourne (type, labels, corps) pour chaque bloc de premier niveau."""
    blocks, pos = [], 0
    while True:
        m = BLOCK_RE.search(text, pos)
        if not m:
            return blocks
        end = skip_braces(text, m.end() - 1)
        labels = re.findall(r'"([^"]+)"', m.group(2))
        blocks.append((m.group(1), labels, text[m.end(): end - 1]))
        pos = end


def top_level_keys(body: str) -> set[str]:
    """Noms d'attributs situes au premier niveau d'un corps de bloc."""
    keys, depth, i = set(), 0, 0
    line_start = True
    while i < len(body):
        c = body[i]
        if c == '"':
            i = skip_string(body, i)
            line_start = False
            continue
        if c in "{[(":
            depth += 1
        elif c in "}])":
            depth -= 1
        elif c == "\n":
            line_start = True
            i += 1
            continue
        elif line_start and depth == 0:
            m = re.match(r"\s*([A-Za-z_][\w-]*)\s*=(?!=)", body[i:])
            if m:
                keys.add(m.group(1))
        if not c.isspace():
            line_start = False
        i += 1
    return keys


# --------------------------------------------------------------------------- modeles
class Dir:
    def __init__(self, path: Path):
        self.path = path
        raw = "\n".join(strip_comments(f.read_text(encoding="utf-8")) for f in sorted(path.glob("*.tf")))
        self.text = raw
        self.expr = expression_text(raw)
        self.vars: dict[str, bool] = {}  # nom -> a une valeur par defaut
        self.outputs: set[str] = set()
        self.resources: set[tuple[str, str]] = set()
        self.data: set[tuple[str, str]] = set()
        self.modules: dict[str, str] = {}  # nom -> corps
        self.locals: set[str] = set()
        for kind, labels, body in parse_blocks(raw):
            if kind == "variable":
                self.vars[labels[0]] = bool(re.search(r"^\s*default\s*=", body, re.MULTILINE))
            elif kind == "output":
                self.outputs.add(labels[0])
            elif kind == "resource":
                self.resources.add((labels[0], labels[1]))
            elif kind == "data":
                self.data.add((labels[0], labels[1]))
            elif kind == "module":
                self.modules[labels[0]] = body
            elif kind == "locals":
                self.locals |= top_level_keys(body)


def check(root: Path) -> tuple[list[str], list[str]]:
    errors, warnings = [], []
    dirs = {d.parent: Dir(d.parent) for d in root.rglob("*.tf")}

    for path, d in dirs.items():
        rel = path.relative_to(root.parent) if root.parent in path.parents else path
        # sans les chaines litterales hors interpolation, les references var. restent detectables
        for name in set(re.findall(r"\bvar\.([A-Za-z_]\w*)", d.expr)):
            if name not in d.vars:
                errors.append(f"{rel}: var.{name} utilise mais non declare")
        for name in d.vars:
            if not re.search(rf"\bvar\.{name}\b", d.expr):
                warnings.append(f"{rel}: variable {name} declaree mais jamais utilisee")
        for name in set(re.findall(r"\blocal\.([A-Za-z_]\w*)", d.expr)):
            if name not in d.locals:
                errors.append(f"{rel}: local.{name} utilise mais non defini")
        for t, n in set(re.findall(r"(?<![\w.])((?:" + "|".join(RESOURCE_PREFIXES) + r")\w*)\.([A-Za-z_]\w*)", d.expr)):
            if (t, n) not in d.resources:
                errors.append(f"{rel}: ressource {t}.{n} referencee mais non definie")
        for t, n in set(re.findall(r"\bdata\.(\w+)\.(\w+)", d.expr)):
            if (t, n) not in d.data:
                errors.append(f"{rel}: data.{t}.{n} reference mais non defini")

        for mod, body in d.modules.items():
            src = re.search(r'source\s*=\s*"([^"]+)"', body)
            if not src:
                errors.append(f"{rel}: module {mod} sans source")
                continue
            target_path = (path / src.group(1)).resolve()
            target = dirs.get(target_path)
            if target is None:
                errors.append(f"{rel}: module {mod} pointe vers {src.group(1)} qui n'existe pas")
                continue
            args = top_level_keys(body) - META_ARGS
            for a in sorted(args - set(target.vars)):
                errors.append(f"{rel}: module {mod} recoit l'argument inconnu '{a}'")
            for v, has_default in target.vars.items():
                if not has_default and v not in args:
                    errors.append(f"{rel}: module {mod} n'a pas fourni la variable obligatoire '{v}'")
        for mod, out in set(re.findall(r"\bmodule\.(\w+)\.(\w+)", d.expr)):
            if mod not in d.modules:
                errors.append(f"{rel}: module.{mod} reference mais non declare")
                continue
            src = re.search(r'source\s*=\s*"([^"]+)"', d.modules[mod])
            target = dirs.get((path / src.group(1)).resolve()) if src else None
            if target is not None and out not in target.outputs:
                errors.append(f"{rel}: module.{mod}.{out} n'existe pas (sorties : {sorted(target.outputs)})")
    return errors, warnings


def main(argv: list[str]) -> int:
    root = Path(argv[1] if len(argv) > 1 else Path(__file__).resolve().parent.parent / "infra").resolve()
    errors, warnings = check(root)
    for w in warnings:
        print(f"AVERTISSEMENT {w}")
    for e in errors:
        print(f"ERREUR {e}")
    print(f"{len(errors)} erreur(s), {len(warnings)} avertissement(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
