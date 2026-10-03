#!/usr/bin/env python3
"""Outils de traduction EventLead, sans gettext (bibliothèque standard uniquement).

Les textes du site sont écrits en français dans le code : le français est la langue d'origine,
`locale/en` et `locale/ht` contiennent les traductions en anglais et en créole haïtien.

Commandes (à lancer depuis la racine du projet) :

  python tools/i18n.py sync       extrait les textes du code, fusionne, écrit les .po et compile les .mo
  python tools/i18n.py compile    compile seulement les .po en .mo (c'est ce que Django lit)
  python tools/i18n.py report     liste les textes sans traduction (--lang en|ht, --files f1 f2 ...)
  python tools/i18n.py msgids F   affiche en JSON les textes trouvés dans les fichiers F, à traduire
  python tools/i18n.py check      vérifie les .po (traductions vides, variables %(x)s, formes plurielles)

Un fichier JSON déposé dans locale/_work/ (forme {"texte français": {"en": "...", "ht": "..."}}, une liste
pour les formes plurielles ; clé « contexte\\x04texte » pour un texte avec contexte) est fusionné par `sync`, qui le supprime ensuite :
les corrections se font directement dans les .po. Les .mo sont versionnés : Windows n'a pas besoin de
gettext pour lancer le site.
"""
import argparse
import ast
import json
import os
import re
import struct
import sys
import tempfile
from collections import OrderedDict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOCALE = ROOT / "locale"
WORK = LOCALE / "_work"
LANGS = {"en": "n != 1", "ht": "n > 1"}
APP_DIRS = ["accounts", "ads", "core", "events", "gifts", "payments", "eventlead"]
PY_FUNCS = {"gettext", "gettext_lazy", "gettext_noop", "_", "ngettext", "ngettext_lazy", "pgettext", "pgettext_lazy", "npgettext"}
SKIP_PY_PARTS = {"migrations", "tests", "__pycache__"}
SKIP_PY_NAMES = {"seed_demo.py"}

STR = r'"((?:[^"\\]|\\.)*)"|\'((?:[^\'\\]|\\.)*)\''
TAG_RE = re.compile(r"\{%.*?%\}|\{\{.*?\}\}", re.S)
TRANS_RE = re.compile(r"\{%\s*(?:trans|translate)\s+(?:" + STR + r")(?P<rest>[^%]*?)%\}", re.S)
UNDERSCORE_RE = re.compile(r"(?<![\w.])_\(\s*(?:" + STR + r")\s*\)")
BLOCK_RE = re.compile(
    r"\{%\s*blocktrans(?:late)?(?P<args>(?:[^%]|%(?!\}))*)%\}(?P<body>.*?)\{%\s*endblocktrans(?:late)?\s*%\}", re.S
)
PLURAL_RE = re.compile(r"\{%\s*plural\s*%\}")
VAR_RE = re.compile(r"\{\{\s*(\w+)\s*\}\}")
PLACEHOLDER_RE = re.compile(r"%\((\w+)\)[sd]|%[sd]")


def unescape(s):
    return re.sub(r"\\(.)", r"\1", s)


class Entry:
    def __init__(self, msgid, plural=None, ctx=None):
        self.msgid, self.plural, self.ctx = msgid, plural, ctx
        self.refs = []
        self.msgstr = []  # une chaîne, ou une par forme plurielle
        self.fuzzy = False

    @property
    def key(self):
        return (self.ctx, self.msgid)


def trim(s):
    return re.sub(r"\s*\n\s*", " ", s.strip())


def block_msgid(body, trimmed):
    def convert(part):
        if trimmed:
            part = trim(part)
        part = part.replace("%", "%%")
        return VAR_RE.sub(lambda m: "%(" + m.group(1) + ")s", part)

    parts = PLURAL_RE.split(body)
    return convert(parts[0]), (convert(parts[1]) if len(parts) > 1 else None)


def extract_template(path, text):
    found = []

    def line(pos):
        return text.count("\n", 0, pos) + 1

    for m in TRANS_RE.finditer(text):
        msgid = unescape(m.group(1) if m.group(1) is not None else m.group(2))
        ctx = re.search(r"context\s+(?:\"([^\"]*)\"|'([^']*)')", m.group("rest"))
        found.append((msgid, None, ctx and (ctx.group(1) or ctx.group(2)), line(m.start())))
    for m in BLOCK_RE.finditer(text):
        args = m.group("args")
        singular, plural = block_msgid(m.group("body"), "trimmed" in args.split())
        ctx = re.search(r"context\s+(?:\"([^\"]*)\"|'([^']*)')", args)
        found.append((singular, plural, ctx and (ctx.group(1) or ctx.group(2)), line(m.start())))
    for tag in TAG_RE.finditer(text):
        if re.match(r"\{%\s*(trans|translate|blocktrans|blocktranslate)\b", tag.group(0)):
            continue
        for m in UNDERSCORE_RE.finditer(tag.group(0)):
            msgid = unescape(m.group(1) if m.group(1) is not None else m.group(2))
            found.append((msgid, None, None, line(tag.start())))
    return found


def extract_python(path, text):
    found = []
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:  # pragma: no cover
        print(f"Erreur de syntaxe dans {path}: {exc}", file=sys.stderr)
        return found
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        name = fn.id if isinstance(fn, ast.Name) else fn.attr if isinstance(fn, ast.Attribute) else None
        if name not in PY_FUNCS:
            continue
        strs = [a.value for a in node.args if isinstance(a, ast.Constant) and isinstance(a.value, str)]
        if name in ("ngettext", "ngettext_lazy"):
            if len(strs) >= 2:
                found.append((strs[0], strs[1], None, node.lineno))
        elif name in ("pgettext", "pgettext_lazy"):
            if len(strs) >= 2:
                found.append((strs[1], None, strs[0], node.lineno))
        elif name == "npgettext":
            if len(strs) >= 3:
                found.append((strs[1], strs[2], strs[0], node.lineno))
        elif strs:
            found.append((strs[0], None, None, node.lineno))
    return found


def source_files():
    files = sorted((ROOT / "templates").rglob("*.html"))
    for app in APP_DIRS:
        for p in sorted((ROOT / app).rglob("*.py")):
            rel = set(p.relative_to(ROOT).parts)
            if rel & SKIP_PY_PARTS or p.name in SKIP_PY_NAMES or p.name.startswith("test_"):
                continue
            files.append(p)
    return files


def extract(files=None):
    entries = OrderedDict()
    for path in files or source_files():
        path = Path(path)
        rel = str(path.resolve().relative_to(ROOT)).replace(os.sep, "/")
        text = path.read_text(encoding="utf-8")
        items = extract_template(rel, text) if path.suffix == ".html" else extract_python(rel, text)
        for msgid, plural, ctx, lineno in items:
            e = entries.setdefault((ctx, msgid), Entry(msgid, plural, ctx))
            if plural and not e.plural:
                e.plural = plural
            e.refs.append(f"{rel}:{lineno}")
    return entries


# ----------------------------------------------------------------------------- .po


def po_quote(s):
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\t", "\\t") + '"'


def po_field(name, value):
    lines = value.split("\n")
    if len(lines) == 1:
        return f"{name} {po_quote(value)}\n"
    out = f'{name} ""\n'
    for i, part in enumerate(lines):
        out += po_quote(part + ("\n" if i < len(lines) - 1 else "")).replace("\\n\"", "\\n\"") + "\n"
    return out


def po_unquote(s):
    s = s.strip()[1:-1]
    return re.sub(r"\\(.)", lambda m: {"n": "\n", "t": "\t", '"': '"', "\\": "\\"}.get(m.group(1), m.group(1)), s)


def header(lang):
    return (
        "Project-Id-Version: EventLead\n"
        f"Language: {lang}\n"
        "MIME-Version: 1.0\n"
        "Content-Type: text/plain; charset=UTF-8\n"
        "Content-Transfer-Encoding: 8bit\n"
        f"Plural-Forms: nplurals=2; plural=({LANGS[lang]});\n"
    )


def write_po(path, lang, entries):
    out = [po_field("msgid", ""), po_field("msgstr", header(lang)), "\n"]
    for e in entries:
        if e.refs:
            out.append("#: " + " ".join(e.refs[:6]) + "\n")
        if e.fuzzy:
            out.append("#, fuzzy\n")
        if e.ctx is not None:
            out.append(po_field("msgctxt", e.ctx))
        out.append(po_field("msgid", e.msgid))
        if e.plural is not None:
            out.append(po_field("msgid_plural", e.plural))
            forms = (e.msgstr + ["", ""])[:2]
            for i, f in enumerate(forms):
                out.append(po_field(f"msgstr[{i}]", f))
        else:
            out.append(po_field("msgstr", e.msgstr[0] if e.msgstr else ""))
        out.append("\n")
    atomic_write(path, "".join(out).encode("utf-8"))


def read_po(path):
    entries = OrderedDict()
    if not Path(path).exists():
        return entries
    cur, field, fuzzy = None, None, False
    raw = Path(path).read_text(encoding="utf-8")
    blocks = re.split(r"\n\s*\n", raw)
    for block in blocks:
        ctx = msgid = plural = None
        strs = {}
        fuzzy = False
        field = None
        for line in block.split("\n"):
            if line.startswith("#,") and "fuzzy" in line:
                fuzzy = True
            if line.startswith("#"):
                continue
            m = re.match(r"(msgctxt|msgid_plural|msgid|msgstr(?:\[\d\])?)\s+(\".*\")\s*$", line)
            if m:
                field = m.group(1)
                val = po_unquote(m.group(2))
            elif line.startswith('"') and field:
                val = po_unquote(line)
            else:
                continue
            if m:
                if field == "msgctxt":
                    ctx = val
                elif field == "msgid":
                    msgid = val
                elif field == "msgid_plural":
                    plural = val
                else:
                    strs[field] = val
            else:
                if field == "msgctxt":
                    ctx += val
                elif field == "msgid":
                    msgid += val
                elif field == "msgid_plural":
                    plural += val
                else:
                    strs[field] += val
        if msgid is None or (msgid == "" and ctx is None):
            continue
        e = Entry(msgid, plural, ctx)
        e.fuzzy = fuzzy
        if plural is not None:
            e.msgstr = [strs.get("msgstr[0]", ""), strs.get("msgstr[1]", "")]
        else:
            e.msgstr = [strs.get("msgstr", "")]
        entries[e.key] = e
    return entries


def atomic_write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".")
    with os.fdopen(fd, "wb") as fh:
        fh.write(data)
    os.replace(tmp, path)


# ----------------------------------------------------------------------------- .mo


def write_mo(path, lang, entries):
    messages = {"": header(lang).encode("utf-8")}
    for e in entries:
        if e.fuzzy or not any(e.msgstr):
            continue
        if e.plural is not None:
            if not all(e.msgstr):
                continue
            key = e.msgid + "\0" + e.plural
            val = "\0".join(e.msgstr)
        else:
            key, val = e.msgid, e.msgstr[0]
        if e.ctx is not None:
            key = e.ctx + "\x04" + key
        messages[key] = val.encode("utf-8") if isinstance(val, str) else val
    keys = sorted(messages, key=lambda k: k.encode("utf-8") if isinstance(k, str) else k)
    ids = b""
    strs = b""
    offsets = []
    for k in keys:
        kb = k.encode("utf-8")
        vb = messages[k]
        offsets.append((len(ids), len(kb), len(strs), len(vb)))
        ids += kb + b"\0"
        strs += vb + b"\0"
    n = len(keys)
    keystart = 7 * 4 + 16 * n
    valuestart = keystart + len(ids)
    koffsets, voffsets = [], []
    for o1, l1, o2, l2 in offsets:
        koffsets += [l1, o1 + keystart]
        voffsets += [l2, o2 + valuestart]
    data = struct.pack("Iiiiiii", 0x950412DE, 0, n, 7 * 4, 7 * 4 + n * 8, 0, 0)
    data += struct.pack(f"{len(koffsets + voffsets)}i", *(koffsets + voffsets))
    data += ids + strs
    atomic_write(path, data)


# ----------------------------------------------------------------------------- travail


def load_work():
    """Traductions déposées dans locale/_work/*.json : {msgid: {"en": ..., "ht": ...}}."""
    merged = {}
    for p in sorted(WORK.glob("*.json")) if WORK.exists() else []:
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            sys.exit(f"{p}: JSON invalide ({exc})")
        for msgid, tr in data.items():
            for lang, val in tr.items():
                if val:
                    merged.setdefault(msgid, {})[lang] = val
    return merged


def work_for(work, entry):
    """Traductions déposées pour un texte ; pour un texte avec contexte, la clé est « contexte\\x04texte »."""
    if entry.ctx:
        return work.get(f"{entry.ctx}\x04{entry.msgid}") or work.get(entry.msgid, {})
    return work.get(entry.msgid, {})


def cmd_sync(args):
    extracted = extract()
    work = load_work()
    ordered = sorted(extracted.values(), key=lambda e: (e.refs[0].split(":")[0], int(e.refs[0].split(":")[1])))
    for lang in LANGS:
        po_path = LOCALE / lang / "LC_MESSAGES" / "django.po"
        old = read_po(po_path)
        out = []
        for e in ordered:
            n = Entry(e.msgid, e.plural, e.ctx)
            n.refs = e.refs
            prev = old.get(e.key)
            if prev and not prev.fuzzy:
                n.msgstr = list(prev.msgstr)
            tr = work_for(work, e).get(lang)
            if tr:
                n.msgstr = list(tr) if isinstance(tr, list) else [tr]
            if n.plural is not None:
                n.msgstr = (n.msgstr + ["", ""])[:2] if n.msgstr else ["", ""]
            out.append(n)
        write_po(po_path, lang, out)
        if not args.no_compile:
            write_mo(po_path.with_suffix(".mo"), lang, out)
        missing = sum(1 for e in out if not all(e.msgstr))
        print(f"{lang}: {len(out)} textes, {missing} sans traduction")
    if WORK.exists() and not args.keep_work:
        # Les traductions sont désormais dans les .po : les fichiers de travail ne doivent pas écraser une correction future
        for part in WORK.glob("*.json"):
            part.unlink()
        print("locale/_work/ vidé (les traductions sont dans les .po)")


def cmd_compile(args):
    for lang in LANGS:
        po_path = LOCALE / lang / "LC_MESSAGES" / "django.po"
        write_mo(po_path.with_suffix(".mo"), lang, list(read_po(po_path).values()))
        print(f"{lang}: {po_path.with_suffix('.mo').relative_to(ROOT)}")


def cmd_msgids(args):
    entries = extract([Path(f) for f in args.files])
    work = load_work()
    out = OrderedDict()
    for e in entries.values():
        cur = {lang: work_for(work, e).get(lang, "") for lang in LANGS}
        if e.plural is not None:
            out[e.msgid] = {lang: (cur[lang] or ["", ""]) for lang in LANGS}
            out[e.msgid]["_plural_fr"] = e.plural
        else:
            out[e.msgid] = cur
    print(json.dumps(out, ensure_ascii=False, indent=1))


def cmd_report(args):
    wanted = {str(Path(f).resolve().relative_to(ROOT)).replace(os.sep, "/") for f in args.files} if args.files else None
    for lang in ([args.lang] if args.lang else LANGS):
        old = read_po(LOCALE / lang / "LC_MESSAGES" / "django.po")
        extracted = extract()
        work = load_work()
        n = 0
        for key, e in extracted.items():
            if wanted and not any(r.rsplit(":", 1)[0] in wanted for r in e.refs):
                continue
            prev = old.get(key)
            have = bool(work_for(work, e).get(lang)) or (prev is not None and all(prev.msgstr) and not prev.fuzzy)
            if not have:
                n += 1
                print(f"[{lang}] {e.refs[0]}  {e.msgid!r}")
        print(f"{lang}: {n} sans traduction")


def cmd_check(args):
    problems = 0
    for lang in LANGS:
        entries = read_po(LOCALE / lang / "LC_MESSAGES" / "django.po")
        for e in entries.values():
            forms = e.msgstr
            for i, tr in enumerate(forms):
                src = e.msgid if i == 0 or e.plural is None else e.plural
                if not tr:
                    print(f"[{lang}] vide: {e.msgid!r}")
                    problems += 1
                    continue
                a, b = sorted(PLACEHOLDER_RE.findall(src)), sorted(PLACEHOLDER_RE.findall(tr))
                if e.plural is not None and i == 0:
                    a = sorted(PLACEHOLDER_RE.findall(e.msgid)) or a
                if a != b and not (e.plural is not None and i == 0):
                    print(f"[{lang}] variables différentes: {e.msgid!r} -> {tr!r}")
                    problems += 1
    print("OK" if not problems else f"{problems} problème(s)")
    return 1 if problems else 0


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("sync")
    s.add_argument("--no-compile", action="store_true")
    s.add_argument("--keep-work", action="store_true", help="garde les fichiers de locale/_work/ après la fusion")
    s.set_defaults(fn=cmd_sync)
    sub.add_parser("compile").set_defaults(fn=cmd_compile)
    m = sub.add_parser("msgids")
    m.add_argument("files", nargs="+")
    m.set_defaults(fn=cmd_msgids)
    r = sub.add_parser("report")
    r.add_argument("--lang", choices=list(LANGS))
    r.add_argument("--files", nargs="*")
    r.set_defaults(fn=cmd_report)
    sub.add_parser("check").set_defaults(fn=cmd_check)
    args = p.parse_args()
    sys.exit(args.fn(args) or 0)


if __name__ == "__main__":
    main()
