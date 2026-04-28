---
name: storyworld-references
description: >
  Storyworld character reference handling — HuggingFace dataset
  download, character-yaml lookup, reference-image selection. Pairs
  with the generic comfyui skill for t2i/i2i/video generation.
  Triggers on: storyworld character, named character reference,
  6166r-style character codes, polyu-storyworld-characters, Athena,
  generate image of character <code>.
---

# Storyworld References Skill

Handles the storyworld-specific layer above generic ComfyUI access:
the HuggingFace `venetanji/polyu-storyworld-characters` dataset, the
per-character YAML files in this repo, the multi-image reference set
per character, and the `.txt` caption files that ride alongside each
image. Calls into the underlying
[`comfyui` skill](https://github.com/venetanji/creative-skills/tree/main/comfyui)
for the actual generation; keeps the per-character handling isolated
so the generic skill stays generic.

## Why this is split out

The generic `creative-skills/comfyui` skill knows how to talk to
ComfyUI (Flux2 / LTX-2.3, t2i / i2i / video, scripts at
`~/.openclaw/skills/comfyui/scripts/…`). It does **not** need to know
about a specific student-storyworld dataset, character codes, or the
captions-next-to-images convention. Anything storyworld-specific lives
here; anything you'd want for any ComfyUI workflow lives there.

## Dataset

All 84 character reference images are published on HuggingFace:

- **Dataset:** `venetanji/polyu-storyworld-characters`
- **Total images:** ~420 (multiple references per character)
- **Per character:** image files (`1.png`, `2.jpg`, `img3.jpeg`, …)
  and a `.txt` file alongside each image with a tag-based caption.

Character codes are the last four digits of the contributor's
student id, suffixed with a single character (e.g. `6166r`, `1822g`).
The matching YAML lives in this repo at `characters/<code>.yaml`.

## Storage paths (sandbox / host)

References are stored on disk under the storyworld skill's
references directory:

```
~/.openclaw/skills/storyworld/references/<code>/
  1.png
  1.txt
  2.png
  2.txt
  …
```

YAMLs (this repo, mirrored into the sandbox) live under:

```
~/.openclaw/skills/storyworld/characters/<code>.yaml
```

As with the comfyui skill, prefer absolute paths (`/home/sandbox/…`
or `/home/venetanji/…`) inside `exec` calls — tilde expansion is
unreliable.

## Download

The download helper lives in the sibling **creative-skills** repo at
`comfyui/scripts/download_characters.py`. (It does not yet live in
this repo's `scripts/` — only `validate_yaml_keys.py` does. Moving or
copying the downloader here is a follow-on; for now we cite it where
it actually exists.)

```bash
# All 84 characters (~420 images)
HF_TOKEN=<YOUR_HF_TOKEN> \
python3 /home/sandbox/.openclaw/skills/comfyui/scripts/download_characters.py

# A specific subset
HF_TOKEN=<YOUR_HF_TOKEN> \
python3 /home/sandbox/.openclaw/skills/comfyui/scripts/download_characters.py 6166r 1822g
```

The script writes into
`~/.openclaw/skills/storyworld/references/<code>/` so the storage
paths above are populated on first run.

## Character lookup

For any character code:

1. Read the YAML: `~/.openclaw/skills/storyworld/characters/<code>.yaml`
   — gives you `name`, `age`, `personality`, `appearance`,
   `profile_image`, `backstory`.
2. Read captions: `~/.openclaw/skills/storyworld/references/<code>/*.txt`
   — tag-based descriptions of each reference image.
3. Pick the best reference image. The YAML's `profile_image` field is
   a strong default (e.g. `5.png` for `6166r` / Athena); otherwise
   `1.png` is conventionally the primary front view.
4. Build the i2i prompt by combining the YAML description and the
   chosen reference's caption.

## Workflow: "Generate image of character `<code>`"

The full path from request to output:

1. Read YAML: `~/.openclaw/skills/storyworld/characters/<code>.yaml` →
   character description.
2. Read captions: `~/.openclaw/skills/storyworld/references/<code>/*.txt`.
3. Pick best reference image (YAML's `profile_image`, or `1.png`).
4. Upload to ComfyUI via `upload_if_local()` from the comfyui skill's
   `core.py`.
5. Build i2i prompt: combine YAML description + reference caption +
   the user's scene direction.
6. Run `flux2_single_image_edit` via the comfyui skill's
   `comfy_graph.py i2i`.
7. Download → crop if needed → deliver (Discord, etc.).

**No MCP needed.** All assets are local once the HF dataset is
downloaded.

### Concrete example — Athena (`6166r`)

```bash
# 1. Upload Athena's reference image to ComfyUI
python3 -c "
import sys; sys.path.insert(0,'/home/sandbox/.openclaw/skills/comfyui/scripts')
from core import upload_if_local
name = upload_if_local('/home/sandbox/.openclaw/skills/storyworld/references/6166r/1.png')
print(name)
"

# 2. i2i with the uploaded reference guiding generation
python3 /home/sandbox/.openclaw/skills/comfyui/scripts/comfy_graph.py i2i \
  --image /path/to/uploaded/6166r_1.png \
  --prompt "Athena walking through a moonlit forest, dramatic portrait" \
  --steps 12 --seed 42
```

The YAML for `6166r` (Athena) gives you the descriptive base
("goddess of wisdom… tall, regal, and beautiful… often depicted with
an owl and a shield…"); the `.txt` caption next to `1.png` gives you
visual tags; concatenate, then add the scene direction the user
asked for.

## Calling the comfyui skill (variants, multi-prompt, etc.)

The actual ComfyUI t2i / i2i / video workflows live in the generic
[`creative-skills/comfyui`](https://github.com/venetanji/creative-skills/tree/main/comfyui)
skill. From a storyworld perspective, the most useful entry points
are:

- `t2i` — text-to-image (no reference; for sketches / mood).
- `i2i` — single reference + prompt (the default for "image of
  `<code>`").
- `i2iN` / `i2i2` — multiple references (e.g. character + costume
  reference, or two characters in one shot).
- `multiprompt` / `i2iNmulti` — N prompts × refs in **one** comfy
  submission, for variants of the same character. Always preferred
  over a shell `for`-loop.

Example — 10 variants of the same storyworld character from one
reference, in one submission:

```bash
python3 /home/sandbox/.openclaw/skills/comfyui/scripts/comfy_graph.py multiprompt \
    --image /home/sandbox/.openclaw/skills/storyworld/references/6166r/1.png \
    --prompts "$(printf 'standing on Olympus at dawn\nin a moonlit forest\n…\nin a marble courtroom')" \
    --append ". Consistent style: cinematic, painterly. Preserve same character (Athena, 6166r)." \
    --width 896 --height 1664 \
    --prefix athena_variants \
    --output-dir /workspace/outputs/variants/
```

Refer to the comfyui SKILL for the full CLI reference, model
choices, video flows, and delivery-to-Discord conventions — those
are all generic and should not be duplicated here.

## Consumers

- **agent-pr** (in agentic-media lordships) for author-identity
  continuity — see
  `agentic-media/control-center/schemas/agent-creative.md` §11.
- Storyworld coursework agents that need to generate scenes /
  variants of student-contributed characters.

## Follow-ons

- Move (or symlink) `download_characters.py` from
  `creative-skills/comfyui/scripts/` into this repo's `scripts/` so
  the dataset, the YAMLs, and the downloader are co-located. Until
  that lands, the script lives only in creative-skills.
- Add a small `lookup.py` here that, given a character code, prints
  the chosen reference path + the assembled YAML+caption prompt
  fragment, so callers don't reimplement steps 1-3 of the workflow
  above.
