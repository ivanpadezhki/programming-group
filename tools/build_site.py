#!/usr/bin/env python3
"""Generate the pages that depend on people's uploads.

Reads:   spine/*.csv, spine/config.txt, people/<name>/...
Writes:  _generated/   progress.json and one uploads list per module
         members/      an index, one page per person and one page per upload
         progress.qmd  the comparison page

Nothing here runs anyone's code. Uploads are only read as text.

Usage:  python tools/build_site.py [--people DIR]
"""
import argparse
import csv
import html
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

LANG_BY_EXT = {'.ipynb': 'Python', '.py': 'Python', '.r': 'R', '.m': 'MATLAB'}
FENCE_LANG = {'Python': 'python', 'R': 'r', 'MATLAB': 'matlab'}
STATUS_DONE, STATUS_TRIED, STATUS_NONE = 'Done', 'Attempted', 'Not started'


# ---------------------------------------------------------------- parsing

def parse_kv(lines):
    """Read 'key: value' lines into a dict. Values keep their text."""
    out = {}
    for ln in lines:
        m = re.match(r'^\s*([A-Za-z_][\w-]*)\s*:\s*(.*?)\s*$', ln)
        if m:
            out[m.group(1).lower()] = m.group(2)
    return out


def parse_ids(value):
    """'[2.1, 2.2]' or '2.1, 2.2' -> ['2.1', '2.2']."""
    value = value.strip().strip('[]')
    return [p.strip().strip('\'"') for p in re.split(r'[,\s]+', value) if p.strip().strip('\'"')]


def parse_header(lines):
    """Find the first '---' block in the first lines and read it.

    Comment markers (#, %) at the start of a line are ignored, so the same
    block works at the top of a notebook cell, an R script or a MATLAB script.
    Returns a dict (possibly empty) or None when there is no block.
    """
    cleaned = [re.sub(r'^\s*[#%]+ ?', '', ln.rstrip('\n')).strip() for ln in lines[:60]]
    start = next((i for i, ln in enumerate(cleaned) if ln == '---'), None)
    if start is None:
        return None
    block = []
    for ln in cleaned[start + 1:]:
        if ln == '---':
            break
        block.append(ln)
    else:
        return None
    return parse_kv(block)


def cell_source(cell):
    src = cell.get('source', '')
    return ''.join(src) if isinstance(src, list) else src


def read_notebook(path):
    nb = json.loads(path.read_text(encoding='utf-8'))
    cells = nb.get('cells', [])
    first = next((c for c in cells if cell_source(c).strip()), None)
    header = parse_header(cell_source(first).split('\n')) if first else None
    return nb, header


# ---------------------------------------------------------------- rendering

ZWSP = '\u200b'


def safe(text):
    """Stop Quarto shortcodes in uploaded text from running."""
    return text.replace('{{<', '{{' + ZWSP + '<').replace('{{%', '{{' + ZWSP + '%')


def fence(code, lang=''):
    code = safe(code).rstrip('\n')
    longest = max([len(m) for m in re.findall(r'`+', code)] + [2])
    ticks = '`' * (longest + 1)
    return f'{ticks}{lang}\n{code}\n{ticks}\n'


def notebook_body(nb, lang):
    out = []
    for cell in nb.get('cells', []):
        src = cell_source(cell)
        kind = cell.get('cell_type')
        if kind == 'markdown':
            out.append(safe(src).strip() + '\n')
        elif kind == 'code':
            out.append(fence(src, FENCE_LANG[lang]))
            for o in cell.get('outputs', []):
                data = o.get('data', {})
                if 'image/png' in data:
                    png = data['image/png']
                    png = ''.join(png) if isinstance(png, list) else png
                    out.append(f'![](data:image/png;base64,{png.strip()})\n')
                elif 'text/plain' in data:
                    txt = data['text/plain']
                    out.append(fence(''.join(txt) if isinstance(txt, list) else txt))
                elif o.get('output_type') == 'stream':
                    txt = o.get('text', '')
                    out.append(fence(''.join(txt) if isinstance(txt, list) else txt))
    return '\n'.join(out)


def git_date(path):
    try:
        res = subprocess.run(['git', 'log', '-1', '--format=%cs', '--', str(path)],
                             cwd=ROOT, capture_output=True, text=True, timeout=30)
        return res.stdout.strip()
    except Exception:
        return ''


# ---------------------------------------------------------------- loading

def load_spine():
    with open(ROOT / 'spine' / 'modules.csv', newline='', encoding='utf-8') as f:
        modules = list(csv.DictReader(f))
    with open(ROOT / 'spine' / 'objectives.csv', newline='', encoding='utf-8') as f:
        objectives = list(csv.DictReader(f))
    cfg_path = ROOT / 'spine' / 'config.txt'
    config = parse_kv(cfg_path.read_text(encoding='utf-8').split('\n')) if cfg_path.exists() else {}
    return modules, objectives, config


def slugify(name):
    return re.sub(r'[^A-Za-z0-9_-]+', '-', name).strip('-').lower() or 'member'


def load_people(people_dir, objective_ids, warnings):
    people = []
    if not people_dir.is_dir():
        return people
    for pdir in sorted(p for p in people_dir.iterdir() if p.is_dir() and not p.name.startswith(('_', '.'))):
        prof_path = pdir / 'profile.txt'
        prof = parse_kv(prof_path.read_text(encoding='utf-8').split('\n')) if prof_path.exists() else {}
        person = {
            'folder': pdir.name,
            'slug': slugify(pdir.name),
            'name': prof.get('name') or pdir.name,
            'language': prof.get('language', ''),
            'uploads': [],
        }
        used_stems = set()
        for f in sorted(pdir.rglob('*')):
            if not f.is_file() or f.suffix.lower() not in LANG_BY_EXT:
                continue
            rel = f.relative_to(ROOT) if ROOT in f.parents else f
            lang = LANG_BY_EXT[f.suffix.lower()]
            nb = None
            try:
                if f.suffix.lower() == '.ipynb':
                    nb, header = read_notebook(f)
                else:
                    header = parse_header(f.read_text(encoding='utf-8', errors='replace').split('\n'))
            except Exception as exc:
                warnings.append((str(rel), f'could not read file: {exc}'))
                continue
            if header is None:
                warnings.append((str(rel), 'no header block, so it counts for nothing yet (see How to upload)'))
                header = {}
            done = parse_ids(header.get('objectives', ''))
            tried = parse_ids(header.get('attempted', ''))
            for i in done + tried:
                if i not in objective_ids:
                    warnings.append((str(rel), f'unknown objective ID {i}'))
            done = [i for i in done if i in objective_ids]
            tried = [i for i in tried if i in objective_ids and i not in done]
            stem = slugify(f.stem)
            base = stem
            n = 2
            while stem in used_stems:
                stem = f'{base}-{n}'
                n += 1
            used_stems.add(stem)
            person['uploads'].append({
                'file': f,
                'rel': str(rel).replace('\\', '/'),
                'stem': stem,
                'lang': lang,
                'nb': nb,
                'done': done,
                'attempted': tried,
                'week': header.get('week', ''),
                'title': header.get('title', '') or f.name,
                'date': git_date(f) if ROOT in f.parents else '',
            })
        people.append(person)
    return people


# ---------------------------------------------------------------- progress

def compute(people, modules, objectives, config):
    by_module = {}
    for o in objectives:
        by_module.setdefault(int(o['module']), []).append(o['id'])
    for p in people:
        done, tried, evidence = set(), set(), {}
        for u in p['uploads']:
            for i in u['done']:
                done.add(i)
                evidence.setdefault(i, u)
            tried.update(u['attempted'])
        tried -= done
        p['done'], p['tried'], p['evidence'] = done, tried, evidence
        p['modules'] = {}
        for m in modules:
            ids = by_module[int(m['id'])]
            n = sum(1 for i in ids if i in done)
            p['modules'][int(m['id'])] = {'done': n, 'total': len(ids), 'pct': round(100 * n / len(ids))}
        started = [m for m, v in p['modules'].items() if v['done'] or any(i in tried for i in by_module[m])]
        p['current'] = max(started) if started else 0
        p['languages'] = sorted({u['lang'] for u in p['uploads']})
    return by_module


def status(p, i):
    if i in p['done']:
        return STATUS_DONE
    if i in p['tried']:
        return STATUS_TRIED
    return STATUS_NONE


# ---------------------------------------------------------------- output

def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


def lang_tag(p):
    langs = p['languages'] or ([p['language']] if p['language'] else [])
    return ', '.join(langs) if langs else 'no uploads yet'


def md_cell(text):
    return str(text).replace('|', '\\|').replace('\n', ' ')


def upload_path(p, u):
    return f'/members/{p["slug"]}--{u["stem"]}.qmd'


def write_upload_pages(people, repo_url):
    for p in people:
        for u in p['uploads']:
            raw = f'{repo_url}/blob/main/{u["rel"]}' if repo_url else ''
            ids = ', '.join(u['done']) or 'none'
            body = notebook_body(u['nb'], u['lang']) if u['nb'] is not None else fence(
                u['file'].read_text(encoding='utf-8', errors='replace'), FENCE_LANG[u['lang']])
            meta = [f'**Person:** [{md_cell(p["name"])}](/members/{p["slug"]}.qmd)',
                    f'**Language:** {u["lang"]}',
                    f'**Objectives marked Done:** {ids}']
            if u['attempted']:
                meta.append(f'**Attempted:** {", ".join(u["attempted"])}')
            if u['week']:
                meta.append(f'**Week:** {u["week"]}')
            if u['date']:
                meta.append(f'**Uploaded:** {u["date"]}')
            if raw:
                meta.append(f'[Download the original file]({raw})')
            title = u['title'].replace('"', "'")
            page = (f'---\ntitle: "{title}"\nfrom: markdown-raw_html\n---\n\n'
                    + '  \n'.join(meta) + '\n\n' + body)
            write(ROOT / 'members' / f'{p["slug"]}--{u["stem"]}.qmd', page)


def write_person_pages(people, modules, objectives, config, by_module):
    obj_text = {o['id']: o['objective'] for o in objectives}
    for p in people:
        cur = p['current']
        lines = [f'---\ntitle: "{p["name"]}"\nsubtitle: "Languages: {lang_tag(p)}"\n---\n']
        lines.append(f'Current module: **{cur}, {modules[cur]["title"]}**.\n')
        lines.append('## Modules\n')
        lines.append('| Module | Done | Share |\n| --- | --- | --- |')
        for m in modules:
            v = p['modules'][int(m['id'])]
            lines.append(f'| [{m["id"]}: {md_cell(m["title"])}](/modules/module-{m["id"]}.qmd) | {v["done"]} of {v["total"]} | {v["pct"]}% |')
        lines.append(f'\n## Module {cur} checklist\n')
        lines.append('| ID | Objective | Status | Upload |\n| --- | --- | --- | --- |')
        for i in by_module[cur]:
            s = status(p, i)
            ev = p['evidence'].get(i)
            link = f'[{md_cell(ev["title"])}]({upload_path(p, ev)})' if ev else ''
            lines.append(f'| {i} | {md_cell(obj_text[i])} | {s} | {link} |')
        lines.append('\n## Uploads\n')
        if p['uploads']:
            lines.append('| Date | Upload | Language | Objectives Done |\n| --- | --- | --- | --- |')
            for u in sorted(p['uploads'], key=lambda x: (x['date'], x['rel']), reverse=True):
                lines.append(f'| {u["date"]} | [{md_cell(u["title"])}]({upload_path(p, u)}) | {u["lang"]} | {", ".join(u["done"])} |')
        else:
            lines.append('No uploads yet.')
        write(ROOT / 'members' / f'{p["slug"]}.qmd', '\n'.join(lines) + '\n')


def write_members_index(people):
    out = ['---', 'title: "Members"', '---', '']
    if people:
        out += ['| Person | Languages | Current module | Uploads |', '| --- | --- | --- | --- |']
        for p in people:
            out.append(f'| [{md_cell(p["name"])}](/members/{p["slug"]}.qmd) | {lang_tag(p)} | {p["current"]} | {len(p["uploads"])} |')
    else:
        out.append('No members yet. See [How to upload](/how-to-upload.qmd) to join.')
    write(ROOT / 'members' / 'index.qmd', '\n'.join(out) + '\n')


def write_module_upload_lists(people, modules, objectives):
    for m in modules:
        n = int(m['id'])
        ids = {o['id'] for o in objectives if int(o['module']) == n}
        rows = []
        for p in people:
            for u in p['uploads']:
                here = [i for i in u['done'] if i in ids]
                if here:
                    rows.append((p, u, here))
        if rows:
            out = ['| Person | Upload | Language | Objectives in this module |', '| --- | --- | --- | --- |']
            for p, u, here in rows:
                out.append(f'| [{md_cell(p["name"])}](/members/{p["slug"]}.qmd) | [{md_cell(u["title"])}]({upload_path(p, u)}) | {u["lang"]} | {", ".join(here)} |')
        else:
            out = ['No uploads for this module yet.']
        write(ROOT / '_generated' / f'uploads-module-{n}.md', '\n'.join(out) + '\n')


def shade(pct):
    return f'background: rgba(46, 125, 50, {0.08 + 0.5 * pct / 100:.2f});'


def write_progress_page(people, modules, objectives, config, by_module):
    cur_mod = int(config.get('current_module', '0'))
    cur_mod = cur_mod if 0 <= cur_mod < len(modules) else 0
    parts = ['---\ntitle: "Progress"\n---\n']
    if not people:
        parts.append('No members yet. See [How to upload](how-to-upload.qmd) to join.\n')
    else:
        parts.append('Share of each module\'s objectives marked Done in an upload. Language is shown as a tag and never changes the counts.\n')
        parts.append('## Modules by person\n')
        head = ''.join(f'<th title="{html.escape(m["title"])}">M{m["id"]}</th>' for m in modules)
        rows = []
        for p in people:
            cells = ''.join(
                f'<td class="num" style="{shade(p["modules"][int(m["id"])]["pct"])}" '
                f'title="{p["modules"][int(m["id"])]["done"]} of {p["modules"][int(m["id"])]["total"]}">'
                f'{p["modules"][int(m["id"])]["pct"]}%</td>' for m in modules)
            rows.append(f'<tr><th scope="row"><a href="members/{p["slug"]}.html">{html.escape(p["name"])}</a></th>'
                        f'<td>{html.escape(lang_tag(p))}</td><td class="num">M{p["current"]}</td>{cells}</tr>')
        parts.append('```{=html}\n<div class="grid-wrap"><table class="progress-grid">'
                     f'<thead><tr><th>Person</th><th>Language</th><th>On</th>{head}</tr></thead><tbody>'
                     + ''.join(rows) + '</tbody></table></div>\n```\n')
        parts.append(f'## Module {cur_mod} by objective: {modules[cur_mod]["title"]}\n')
        parts.append('✔ Done, ◐ Attempted, · not started. The group\'s current module is set in `spine/config.txt`.\n')
        ids = by_module[cur_mod]
        head = ''.join(f'<th title="{html.escape(next(o["objective"] for o in objectives if o["id"] == i))}">{i}</th>' for i in ids)
        rows = []
        for p in people:
            sym = {STATUS_DONE: '✔', STATUS_TRIED: '◐', STATUS_NONE: '·'}
            cells = ''.join(f'<td class="num s-{status(p, i).split()[0].lower()}" title="{status(p, i)}">{sym[status(p, i)]}</td>' for i in ids)
            rows.append(f'<tr><th scope="row">{html.escape(p["name"])}</th>{cells}</tr>')
        parts.append('```{=html}\n<div class="grid-wrap"><table class="progress-grid">'
                     f'<thead><tr><th>Person</th>{head}</tr></thead><tbody>'
                     + ''.join(rows) + '</tbody></table></div>\n```\n')
        parts.append('Objective texts are in the [module page](modules/module-%d.qmd).\n' % cur_mod)
    write(ROOT / 'progress.qmd', '\n'.join(parts))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--people', default=str(ROOT / 'people'), help='folder with one subfolder per person')
    args = ap.parse_args()

    modules, objectives, config = load_spine()
    objective_ids = {o['id'] for o in objectives}
    warnings = []
    people = load_people(Path(args.people).resolve(), objective_ids, warnings)
    by_module = compute(people, modules, objectives, config)

    # start clean so removed uploads disappear from the site
    for d in ('members', '_generated'):
        target = ROOT / d
        if target.exists():
            for f in sorted(target.rglob('*'), reverse=True):
                f.unlink() if f.is_file() else f.rmdir()

    repo_url = config.get('repo_url', '')
    write_upload_pages(people, repo_url)
    write_person_pages(people, modules, objectives, config, by_module)
    write_members_index(people)
    write_module_upload_lists(people, modules, objectives)
    write_progress_page(people, modules, objectives, config, by_module)

    summary = {p['slug']: {'name': p['name'], 'languages': p['languages'], 'current': p['current'],
                           'modules': p['modules'], 'done': sorted(p['done']), 'attempted': sorted(p['tried'])}
               for p in people}
    write(ROOT / '_generated' / 'progress.json', json.dumps(summary, indent=2))

    for path, msg in warnings:
        print(f'::warning file={path}::{msg}')
    print(f'{len(people)} people, {sum(len(p["uploads"]) for p in people)} uploads, {len(warnings)} warnings')
    return 0


if __name__ == '__main__':
    sys.exit(main())
