# Settings

Owns the `app_settings` table: user-editable values stored as JSON by key.
It does not interpret them; the owning module validates before writing and
reads them back through `public.py` (`read_settings`, `write_settings`).
Current keys belong to the generation module (`prompting.*`, `policy.*`).
