---
name: add-recipe
description: Add a new recipe to the jain-taylor-family-cookbook Jekyll site — derive the slug, process images, write the _recipes entry, and open a PR.
---

# Add a Recipe to the Family Cookbook

Add a new recipe to the jain-taylor-family-cookbook Jekyll site. Repo path: `patrick-andrew-jain-taylor/jain-taylor-family-cookbook/` within this workspace.

## Arguments

`$ARGUMENTS` — recipe title and/or details. If not provided, ask the user for the recipe name, ingredients, and instructions before proceeding.

## Steps

### 1. Navigate to the cookbook repo

All file operations should target `patrick-andrew-jain-taylor/jain-taylor-family-cookbook/` relative to the workspace root.

### 2. Gather recipe details

If `$ARGUMENTS` doesn't include enough information, ask the user for:
- Recipe title
- Ingredients (can be a list; you'll structure them into a table)
- Instructions (numbered steps)
- Category (one of: Appetizers, Breakfast, Desserts, Drinks, Entrees, Miscellaneous, Seasonings, Soups, Side Dishes)
- Tags (one or more of: Vegetarian, Vegan, Meat)
- Author (`pjt` unless specified otherwise)
- A photo, if they have one (ask them to provide the file path, e.g. via `@/path/to/image.png`)

### 3. Derive the slug

The slug is used for the filename, image files, branch name, and URL. Derive it from the recipe title:

1. Lowercase the entire title
2. Replace spaces with hyphens
3. Remove or replace any character that is not a letter, digit, or hyphen:
   - Ampersands (`&`) → omit (e.g. "Mac & Cheese" → `mac-cheese`)
   - Apostrophes/quotes → omit (e.g. "Mom's Soup" → `moms-soup`)
   - Commas, parentheses, slashes, and other punctuation → omit
4. Collapse multiple consecutive hyphens into one
5. Strip leading and trailing hyphens

If the resulting slug would collide with an existing file in `_recipes/`, append a short disambiguator (e.g. `-v2`).

### 4. Process the image (if provided)

Images go in `assets/img/`. Run from the cookbook root:

```bash
# Full-size JPEG
sips -s format jpeg <input> --out assets/img/<slug>.jpg

# Thumbnail — portrait 300×400 (note: sips -z takes height then width)
sips -s format jpeg -z 400 300 <input> --out assets/img/<slug>-300x400.jpg
```

### 5. Create the recipe file

Create `_recipes/<slug>.md`.

**With image:**
```markdown
---
author: pjt
title: <Title>
image:
  path: /assets/img/<slug>.jpg
  thumbnail: /assets/img/<slug>-300x400.jpg
  caption: "<Short description of the image>"
categories: [<Category>]
tags: [<Tag>]
---

<One-sentence description of the recipe.>
```

**Without image** (omit the `image:` block entirely):
```markdown
---
author: pjt
title: <Title>
categories: [<Category>]
tags: [<Tag>]
---

<One-sentence description of the recipe.>
```

**Ingredients — single section** (no `###` heading needed):
```markdown
## Ingredients

| Ingredient | Quantity |
|:-:|:-:|
| <Ingredient> | <Amount> |
```

**Ingredients — multiple sections** (e.g. separate sauce and filling):
```markdown
## Ingredients

### <Section Name>

| Ingredient | Quantity |
|:-:|:-:|
| <Ingredient> | <Amount> |

### <Section Name>

| Ingredient | Quantity |
|:-:|:-:|
| <Ingredient> | <Amount> |
```

**CRITICAL — Kramdown rule:** always put a blank line between a heading (`###`, `##`, etc.) and a table. Without it, the table renders as raw pipe text in the browser.

**Instructions — single section** (no `###` heading needed):
```markdown
## Instructions

1. Step one.
2. Step two.
```

**Instructions — multiple sections:**
```markdown
## Instructions

### <Section Name>
1. Step one.
2. Step two.

### <Section Name>
1. Step one.
2. Step two.
```

### 6. Commit and open a PR

Use conventional commit format:

```
feat: add <recipe title> recipe
```

Branch name: `feat/add-<slug>`

After pushing and opening the PR, monitor for the Sourcery review. When Sourcery comments, retrieve their "Prompt for AI Agents" section and address all feedback before requesting merge.
