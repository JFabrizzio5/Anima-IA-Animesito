# Prompts

Owns the vocabulary side of prompting: the modular builder's zones and presets
(`builder.toml`, ported from v1), Danbooru tag autocomplete (the tags SDXL anime
models were trained on), character search that merges Danbooru character tags
with AniList (picture, series, canonical age), and a character's appearance
tags from Danbooru's related-tag statistics. Lookups are cached in Redis.

AniList ages feed a Redis set of canonically under-18 characters
(`animesito:minor_characters`); the generation policy refuses them in adult
mode on top of the static list in `modules/policy`.

## Endpoints

| Method | Path | Description |
| --- | --- | --- |
| GET | `/prompts/builder` | Zones and preset options |
| GET | `/prompts/tags?q=&category=` | Danbooru tag autocomplete |
| GET | `/prompts/characters?q=` | Characters (Danbooru + AniList), with `minor` flag |
| GET | `/prompts/characters/{tag}/traits` | Appearance tags and series for a character tag |
