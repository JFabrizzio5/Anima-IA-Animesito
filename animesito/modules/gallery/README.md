# Gallery

Owns every file the app shows: generated outputs, uploads and imports, with the
prompt, model, seed and parameters that produced them, a WebP thumbnail and the
SHA-256 that the policy module uses as provenance (adult edits only on files
whose hash is here with `source = generated`). Files live on the `storage`
plugin's default disk under `gallery/` and `thumbs/`.

## Endpoints

| Method | Path | Description |
| --- | --- | --- |
| GET | `/gallery` | Search (`q`, `favorite`, `kind`), newest first |
| GET | `/gallery/{id}` | One item |
| PATCH | `/gallery/{id}` | Mark or unmark favorite |
| DELETE | `/gallery/{id}` | Delete the row and its files |

## Invariants

- A row never points at a file that was not written first; delete removes files, then the row.
