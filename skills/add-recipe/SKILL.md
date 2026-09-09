---
name: add-recipe
description: Add a new recipe to the jain-taylor-family-cookbook Jekyll site — derive the slug, process images, write the _recipes entry, and open a PR.
---

# Add a Recipe to the Family Cookbook

Add a new recipe to the jain-taylor-family-cookbook Jekyll site. Repo path: `patrick-andrew-taylor/jain-taylor-family-cookbook/` within this workspace.

## Arguments

`$ARGUMENTS` — recipe title and/or details. If not provided, ask the user for the recipe name, ingredients, and instructions before proceeding.

## Steps

### 1. Navigate to the cookbook repo

All file operations should target `patrick-andrew-taylor/jain-taylor-family-cookbook/` relative to the workspace root.

### 2. Gather recipe details

If `$ARGUMENTS` doesn't include enough information, ask the user for:
- Recipe title
- Ingredients (can be a list; you'll structure them into a table)
- Instructions (numbered steps)
- Category (one of: Appetizers, Breakfast, Desserts, Drinks, Entrees, Miscellaneous, Seasonings, Soups, Side Dishes)
- Tags (one or more of: Vegetarian, Vegan, Meat)
- Author (`pat` unless specified otherwise)
- A photo, if they have one (ask them to provide the file path, e.g. via `@/path/to/image.png`)

### 3. Derive the slug

Derive a URL-friendly slug from the recipe title — lowercase, hyphen-separated, punctuation stripped. It is used for the filename, image files, branch name, and URL.

If the resulting slug would collide with an existing file in `_recipes/`, append a short disambiguator (e.g. `-v2`).

### 4. Process the image (if provided)

Images go in `assets/img/`. Use `sips` from the cookbook root to write a
full-size JPEG at `<slug>.jpg` and a 300×400 portrait thumbnail at
`<slug>-300x400.jpg`.

### 5. Create the recipe file

Create `_recipes/<slug>.md`: Jekyll frontmatter (author, title, categories,
tags, plus the image paths when there's a photo) followed by the recipe body —
ingredients as a table, instructions as a numbered list. Use `###` subsections
if the recipe has distinct components.

### 6. Commit and open a PR

Use conventional commit format:

```
feat: add <recipe title> recipe
```

Branch name: `feat/add-<slug>`

After pushing and opening the PR, monitor for the Sourcery review. When Sourcery comments, retrieve their "Prompt for AI Agents" section and address all feedback before requesting merge.
