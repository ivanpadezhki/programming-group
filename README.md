# Programming group

Site for a programming group that goes from the basics to machine learning in one academic year, with members working in Python, R or MATLAB. Members upload one notebook or script a week; the site shows each person's progress per module.

Members: see `how-to-upload.qmd` (published as "How to upload") for how to join.

## How it works

1. Uploads live in `people/<name>/`. Each file starts with a header listing the objective IDs it covers.
2. `tools/build_site.py` reads those headers and generates the progress, member and module-upload pages. Nothing is executed; files are only read.
3. `quarto render` turns everything into a static site.
4. `.github/workflows/publish.yml` does steps 2 and 3 on every push to `main` and publishes to GitHub Pages.

## Layout

| Path | Content |
| --- | --- |
| `spine/modules.csv`, `spine/objectives.csv` | The nine modules and their learning objectives |
| `spine/config.txt` | `current_module` (which module the progress grid shows) and `repo_url` |
| `modules/module-N.qmd` | One page per module: objectives, resources per language, uploads |
| `spine.qmd`, `caveats.qmd`, `how-to-upload.qmd`, `index.qmd` | Static pages |
| `people/<name>/` | Each member's `profile.txt` and uploads |
| `tools/build_site.py` | Reads uploads, writes `members/`, `_generated/` and `progress.qmd` (all git-ignored) |
| `tests/` | Header parser tests, with fixtures for three example members |

## Maintainer tasks

- **First publish:** in the repository on GitHub, open Settings → Pages and set Source to "GitHub Actions". Then run the "Publish site" workflow once from the Actions tab.
- **Each week:** change `current_module` in `spine/config.txt` to the module the group is on.
- **Objectives or resources:** edit `spine/objectives.csv` and the module pages. The module menu is in `_quarto.yml`.
- **Warnings:** uploads with no header or an unknown objective ID are listed as warnings in the Actions log. They never stop the build.
- **Access:** give write access only to group members. Notebook text is shown with raw HTML switched off and shortcodes disabled, but members can still publish anything they upload.

## Preview locally

Install [Quarto](https://quarto.org/docs/get-started/), then:

```
python tools/build_site.py
quarto preview
```

To see the pages with example members, run `python tools/build_site.py --people tests/fixtures/people` first.

## Later

An AI review of each upload is planned but not built.
