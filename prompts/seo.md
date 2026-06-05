# SEO Metadata Prompt

Generate SEO metadata for the given content. Return ONLY valid JSON.

## Output Format

```json
{
  "title_tag": "SEO title (max 60 chars, include keyword)",
  "meta_description": "Meta description (140-160 chars, compelling)",
  "url_slug": "/category/keyword-slug",
  "h1": "Main heading with keyword"
}
```

## Rules
- title_tag: include focus keyword naturally, under 60 chars
- meta_description: entice clicks, 140-160 chars
- url_slug: lowercase, hyphens, no special chars
- h1: clear, includes keyword, not identical to title_tag
