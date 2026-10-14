#!/usr/bin/env python3
"""Fetch an arXiv paper's LaTeX source + PDF and extract equations and figures.

Usage: python3 -I fetch_arxiv.py <arxiv-id-or-url> <out-dir>

Writes into <out-dir>:
  paper.pdf, src/ (extracted source, untrusted), paper.tex (flattened main file),
  meta.json (title/authors/abstract), equations.json, figures.json, figures/*.png
The source is treated as data only: nothing from it is executed.
"""
import gzip, io, json, re, shutil, subprocess, sys, tarfile, urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

UA = {"User-Agent": "paper-video-skill/1.0 (personal use)"}
MATH_ENVS = r"equation|align|gather|multline|eqnarray|flalign|alignat|displaymath"


def arxiv_id(s):
    m = re.search(r"(\d{4}\.\d{4,5}(v\d+)?|[a-z\-]+(\.[A-Z]{2})?/\d{7}(v\d+)?)", s)
    if not m:
        sys.exit(f"Could not parse an arXiv id from {s!r}")
    return m.group(1)


def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
        return r.read()


def fetch_meta(aid):
    ns = {"a": "http://www.w3.org/2005/Atom"}
    root = ET.fromstring(get(f"https://export.arxiv.org/api/query?id_list={aid}"))
    e = root.find("a:entry", ns)
    if e is None or e.find("a:title", ns) is None:
        return {"id": aid}
    clean = lambda t: re.sub(r"\s+", " ", t or "").strip()
    return {
        "id": aid,
        "title": clean(e.findtext("a:title", "", ns)),
        "authors": [clean(a.findtext("a:name", "", ns)) for a in e.findall("a:author", ns)],
        "abstract": clean(e.findtext("a:summary", "", ns)),
        "published": e.findtext("a:published", "", ns),
    }


def extract_source(blob, src):
    src.mkdir(parents=True, exist_ok=True)
    try:
        with tarfile.open(fileobj=io.BytesIO(blob)) as tf:
            tf.extractall(src, filter="data")  # blocks path traversal / links outside
        return
    except tarfile.ReadError:
        pass
    try:
        data = gzip.decompress(blob)
    except OSError:
        data = blob
    if data[:4] == b"%PDF":
        sys.exit("arXiv has no LaTeX source for this paper (PDF-only). Fall back to the PDF.")
    (src / "main.tex").write_bytes(data)


def find_main(src):
    cands = [p for p in src.rglob("*.tex")
             if re.search(r"\\begin\{document\}", p.read_text(errors="ignore"))]
    if not cands:
        sys.exit("No .tex file with \\begin{document} found in source.")
    return max(cands, key=lambda p: p.stat().st_size)


def strip_comments(t):
    return re.sub(r"(?<!\\)%.*", "", t)


def flatten(path, root, depth=0):
    text = strip_comments(path.read_text(errors="ignore"))
    if depth > 8:
        return text

    def sub(m):
        name = m.group(2).strip()
        for cand in (path.parent / name, root / name):
            for p in (cand, cand.with_name(cand.name + ".tex")):
                if p.is_file() and root in p.resolve().parents:
                    return flatten(p, root, depth + 1)
        return m.group(0)

    return re.sub(r"\\(input|include)\{([^}]*)\}", sub, text)


def sections_index(tex):
    return [(m.start(), m.group(2)) for m in
            re.finditer(r"\\(section|subsection)\*?\{([^}]*)\}", tex)]


def section_at(idx, pos):
    cur = ""
    for p, name in idx:
        if p > pos:
            break
        cur = name
    return cur


def context_before(tex, pos, n=300):
    s = re.sub(r"\s+", " ", tex[max(0, pos - n):pos])
    return s.strip()


def extract_equations(tex):
    idx, out = sections_index(tex), []
    start = max(tex.find(r"\begin{document}"), 0)
    found = []  # (pos, env, body)
    # Display math. (?<!\\)\\\[ skips "\\[0.5em]" line breaks.
    disp = re.compile(rf"\\begin\{{({MATH_ENVS})\*?\}}(.*?)\\end\{{\1\*?\}}"
                      r"|(?<!\\)\\\[(.*?)\\\]|\$\$(.*?)\$\$", re.S)
    masked = list(tex)
    for m in disp.finditer(tex, start):
        found.append((m.start(), m.group(1) or "display", m.group(2) or m.group(3) or m.group(4) or ""))
        masked[m.start():m.end()] = " " * (m.end() - m.start())
    masked = "".join(masked)
    # Inline math: pair unescaped $ in order on the masked text; keep only real formulas.
    dollars = [m.start() for m in re.finditer(r"(?<!\\)\$", masked) if m.start() >= start]
    for a, b in zip(dollars[0::2], dollars[1::2]):
        body = masked[a + 1:b]
        if 12 <= len(body) <= 400 and "\n\n" not in body and re.search(r"=|\\in\b", body) \
                and not re.search(r"\\(begin|cite|ref|includegraphics|section)", body):
            found.append((a, "inline", body))
    for pos, env, body in sorted(found):
        label = re.search(r"\\label\{([^}]*)\}", body)
        body = re.sub(r"\\label\{[^}]*\}", "", body).strip()
        if len(body) < 3:
            continue
        out.append({
            "n": len(out) + 1, "env": env,
            "label": label.group(1) if label else None,
            "section": section_at(idx, pos),
            "latex": body, "context_before": context_before(tex, pos),
        })
    return out


def extract_macros(tex):
    """Collect \\newcommand / \\def / \\DeclareMathOperator so equations can render in Manim."""
    pat = re.compile(r"\\(newcommand|renewcommand|providecommand|DeclareMathOperator)\*?\s*"
                     r"(\{?\\[A-Za-z]+\}?)(\[\d\])?\s*(\{(?:[^{}]|\{(?:[^{}]|\{[^{}]*\})*\})*\})")
    lines = [m.group(0) for m in pat.finditer(tex)]
    lines += re.findall(r"\\def\\[A-Za-z]+\s*\{(?:[^{}]|\{[^{}]*\})*\}", tex)
    return "\n".join(dict.fromkeys(lines))


def rasterize(src_file, dst_png):
    ext = src_file.suffix.lower()
    if ext in (".png", ".jpg", ".jpeg"):
        shutil.copy(src_file, dst_png.with_suffix(ext))
        return dst_png.with_suffix(ext)
    if ext in (".pdf", ".eps") and shutil.which("pdftoppm"):
        pdf = src_file
        if ext == ".eps":
            if not shutil.which("epstopdf"):
                return None
            pdf = dst_png.with_suffix(".pdf")
            subprocess.run(["epstopdf", str(src_file), f"--outfile={pdf}"],
                           capture_output=True, check=False)
        subprocess.run(["pdftoppm", "-png", "-r", "200", "-singlefile", str(pdf),
                        str(dst_png.with_suffix(""))], capture_output=True, check=False)
        return dst_png if dst_png.exists() else None
    return None


def extract_figures(tex, root, figdir):
    figdir.mkdir(exist_ok=True)
    idx, out = sections_index(tex), []
    gp = re.search(r"\\graphicspath\{\{([^}]*)\}", tex)
    gpaths = [root, root / gp.group(1)] if gp else [root]
    for m in re.finditer(r"\\begin\{(figure\*?|wrapfigure)\}(.*?)\\end\{\1\}", tex, re.S):
        body = m.group(2)
        cap = re.search(r"\\caption(\[[^\]]*\])?\{((?:[^{}]|\{(?:[^{}]|\{[^{}]*\})*\})*)\}", body)
        label = re.search(r"\\label\{([^}]*)\}", body)
        files = []
        for arg in re.findall(r"\\includegraphics(?:\[[^\]]*\])?\{((?:[^{}]|\{(?:[^{}]|\{[^{}]*\})*\})*)\}", body):
            # The argument may wrap paths in macros like \iftoggle{..}{a.pdf}{b.jpg}: try every path-like token.
            names = re.findall(r"[\w./\-]+", re.sub(r"\\[A-Za-z]+", " ", arg))
            found = None
            for g in names:
                for base in gpaths:
                    for ext in ("", ".pdf", ".png", ".jpg", ".jpeg", ".eps"):
                        p = base / (g + ext)
                        if p.is_file():
                            found = p
                            break
                    if found:
                        break
                if found:
                    break
            if found:
                n = len(out) + 1
                png = rasterize(found, figdir / f"fig{n:02d}_{len(files) + 1}.png")
                files.append(str(png.relative_to(figdir.parent)) if png else f"UNCONVERTED:{found}")
        out.append({
            "n": len(out) + 1, "label": label.group(1) if label else None,
            "section": section_at(idx, m.start()),
            "caption": re.sub(r"\s+", " ", cap.group(2)).strip() if cap else "",
            "files": files,
        })
    return out


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    aid, out = arxiv_id(sys.argv[1]), Path(sys.argv[2]).resolve()
    out.mkdir(parents=True, exist_ok=True)
    meta = fetch_meta(aid)
    (out / "meta.json").write_text(json.dumps(meta, indent=2))
    (out / "paper.pdf").write_bytes(get(f"https://arxiv.org/pdf/{aid}"))
    src = out / "src"
    if src.exists():
        shutil.rmtree(src)
    extract_source(get(f"https://arxiv.org/e-print/{aid}"), src)
    main_tex = find_main(src)
    tex = flatten(main_tex, src.resolve())
    (out / "paper.tex").write_text(tex)
    (out / "macros.tex").write_text(extract_macros(tex))
    eqs = extract_equations(tex)
    (out / "equations.json").write_text(json.dumps(eqs, indent=2))
    figs = extract_figures(tex, main_tex.parent, out / "figures")
    (out / "figures.json").write_text(json.dumps(figs, indent=2))
    print(json.dumps({"title": meta.get("title"), "main_tex": str(main_tex.relative_to(out)),
                      "equations": len(eqs), "figures": len(figs),
                      "figure_files": sum(len(f["files"]) for f in figs)}, indent=2))


if __name__ == "__main__":
    main()
