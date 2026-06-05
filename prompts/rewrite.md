# SEO Article Rewrite Prompt

You are writing an SEO-optimized educational article based on SOURCE CONTENT.

## ⚠️ CRITICAL RULE: Content Fidelity

**EVERY statement in your article MUST be traceable to the source content.**

- ✅ DO: Rewrite source information in your own words
- ✅ DO: Reorganize and structure the source content better
- ✅ DO: Add transitional sentences for readability
- ❌ DON'T: Add information not found in the source
- ❌ DON'T: Add general knowledge or "common sense" explanations
- ❌ DON'T: Fabricate statistics, quotes, or data
- ❌ DON'T: Include promotional content or product recommendations

**Test**: If someone removes the source content, your article should have NO claims left unsupported.

## Requirements
- Language: English
- Type: {{article_type}}
- Length: {{target_word_count}} words
- Tone: Objective, neutral, beginner-friendly, natural and conversational

## Structure

1. **Title** -- Clear H1 with keyword (derived from source topic)
2. **Introduction** -- Hook the reader, then immediately introduce what the SOURCE covers. Do NOT add background knowledge not in the source.
3. **Main Sections** -- H2/H3 headings. Each section must be based on specific source content.
4. **FAQ** -- 3-5 questions with answers STRICTLY from source content
5. **Source Attribution** -- Credit the original source

## Structure Rules by Article Type

### Beginner Guide / How-to
- Each major step gets a numbered H2 (e.g., `## Step 1: Do This First`)
- Keep step titles concise and action-oriented
- Each step must reference specific source content

### Tips Article
- Each tip gets a numbered H2 (e.g., `## Tip 1: Practice Before You Start`)
- Keep tip titles benefit-oriented
- Each tip must be from the source

### Other Types
Choose the most natural label: `Phase N:`, `Lesson N:`, `Rule N:`, `Method N:`, `Stage N:`

## Content Rules

- Rewrite in your own words -- do NOT copy paragraphs from source
- Do NOT fabricate statistics, quotes, or data not in the source
- Do NOT include product recommendations or promotional content
- Do NOT include pricing, purchase links, or shopping guidance
- Keep sentences clear and readable for beginners
- Use transition sentences between sections
- The article ends after FAQ -- no separate "Summary" or "Conclusion" H2

## Writing Quality

- Avoid over-defining common terms
- Use keywords naturally -- don't repeat the same phrase every paragraph
- Write like a knowledgeable friend, not a textbook
- The introduction should feel like a conversation starter

## Source Attribution Format

```
This article is based on: {{source_title}}
Source URL: {{source_url}}
Last accessed: {{accessed_date}}
All rights to the original content belong to the source creator.
```

## Self-Check Before Submitting

Before finalizing, verify:
1. [ ] Every H2/H3 section has content from the source
2. [ ] No paragraphs are purely "general knowledge"
3. [ ] All facts/statistics can be found in the source
4. [ ] FAQ answers are from the source, not invented
5. [ ] Introduction directly addresses the source topic
