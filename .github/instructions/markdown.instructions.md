---
applyTo: "**/*.md"
---

# Markdown Instructions

## Headings

- Use headings to structure your content. Use `#` for top-level headings, `##` for subheadings, and so on. Keep headings concise and descriptive.

## Lists

- Use bullet points for unordered lists and numbers for ordered lists. 
- Indent nested lists with two spaces.
- Any list more than 3 items long should be a numbered list

## Tables

- Ensure table header dividers are written with spaces either side of the bar `|`. E.g.

```markdown
| Column 1 | Column 2 |
| --- | --- |
| Data 1 | Data 2 |
```

- Note the space before and after the `|` in the header divider line. 
- It is important that you don't write '|---|---|' without spaces, as that will appear as errors in the markdown linter. The correct format is '| --- | --- |' with spaces around the dashes (or around the bar symbols, if you want to discuss it from that perspective).

## Mermaid

- Mermaid is used to communicate models and graphs in the markdown
- Never generate ascii models, always use mermaid
- Mermaid can also display a large number of graphs if needed. We currently use it for radar graphs in some content.
- Every `mermaid` code fence must open with the standard dark-theme init directive, as the first line inside the fence, before any diagram content:

```text
%%{init: {'theme': 'base', 'themeVariables': {'background': '#1e1e1e', 'primaryColor': '#2d2d2d', 'primaryTextColor': '#e6e6e6', 'primaryBorderColor': '#6b6b6b', 'lineColor': '#e6e6e6', 'edgeLabelBackground': '#1e1e1e', 'tertiaryColor': '#2d2d2d'}}}%%
```

- This tunes the diagram for the dark editor/GitHub preview background. Renderers that need a light background (PDF exports, the website) strip this directive themselves rather than the markdown source being maintained in two variants.
- `.github/scripts/backfill-mermaid-theme.ts` inserts this directive into every `mermaid` fence in the repo that doesn't already have one. Run it after adding new diagrams in bulk, or just include the directive by hand when writing a single new diagram.

## Code Blocks

- Code blocks follow the formatting used in the other formatting instructions in the .github/instructions/ folder.
- Code blocks should always have a language specified as part of the fences

## ToC

- For longer markdown files, include a table of contents at the top using stadard syntax
- Use the standard markdown link syntax with anchors to the headings.

## Checklists

- Use checklists for task lists.
- Use `- [ ]` for unchecked items and `- [x]` for checked items. - Indent nested checklists with two spaces.

## General

- We use github markdown
- We render markdown with a dark background, but can render the files as pdf which require a white background
- So sometimes 'themes' are applied to the markdown or mermaid

