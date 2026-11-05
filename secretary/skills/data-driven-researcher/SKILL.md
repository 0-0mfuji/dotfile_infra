---
name: data-driven-researcher
description: A methodology for systematic, high-density technical research and knowledge synthesis from large datasets. Use when you need to extract and categorize every single instance of a specific topic (e.g., all niche programming languages, all robotics concepts) from multi-megabyte JSON exports or text files while maintaining perfect coverage.
---

# Data-Driven Researcher

This skill defines a robust, multi-step process for performing exhaustive technical research. It overcomes context window limitations by combining programmatic extraction with tiered AI synthesis.

## Core Methodology

### Phase 1: Programmatic Metadata Harvesting
Never rely on `read_file` or manual scanning for files over 5MB. Instead, write a targeted script to extract just the relevant metadata fields.

1.  **Analyze Structure**: Read a small chunk of the file to understand its schema.
2.  **Extract**: Write a Node.js or Python script that reads the entire file(s) and outputs a unique list of potential keywords (Tags, Titles, Summaries).
3.  **Dump**: Redirect output to a local file such as `data/karakeep/analysis/metadata_dump.txt` (this data folder is excluded from Git).

### Phase 2: Multi-Layered Pattern Filtering
Use `grep` with regex to filter the harvest results across three levels:

- **Broad Filters**: Use generic domain terms (e.g., `physics|geometry|algorithm`).
- **Niche/Minor Indicators**: Look for patterns like `~lang`, `experimental`, or specific researchers' names known in the field.
- **Exhaustive Lists**: Create long regex strings based on your knowledge base to check if specific known entities (e.g., "Coalton", "Z3") appear in the harvest.

### Phase 3: AI-Augmented Synthesis
Process the filtered keyword list using the configured assistant model to add context and hierarchy.

1.  **Categorization**: Group terms into logical technical stacks (e.g., "Backend", "Optimization", "Theory").
2.  **Enrichment**: For each term, add a concise explanation of its role and significance.
3.  **Application Mapping**: Explicitly link theoretical concepts to practical engineering implementations.

### Phase 4: Tiered Markdown Generation
Generate outputs in stages to ensure both breadth and depth:

- **List Version**: A clean, categorized summary of all identified items.
- **Detailed Version**: Deep dives into specific research themes found (e.g., "Neural Geometry").
- **Application Version**: A developer-focused guide on how to implement or use these technologies.

## Design Standards

- **Absolute Coverage**: If the user asks for "all" instances, do not stop at major ones. Use scripts to find the 1% niche cases.
- **Verification**: If you find a term like "LLVM", perform a targeted `grep` on the raw source data to confirm it's actually there before including it.
- **Categorical Integrity**: Group technologies by their *actual* usage (e.g., placing `mruby/c` in both "Runtimes" and "Embedded" if appropriate).

## Example Triggers
- "Extract every single programming language mentioned in these JSON files."
- "Categorize all mathematical and algorithmic concepts from my bookmark history."
- "Map out the compiler infrastructure mentioned across this entire codebase."

## Secretary runtime

Use local exports under `/srv/secretary/karakeep-tool/data/`. Use `secretary_tools__inspect` and the corresponding `kt-*` skill for deterministic extraction. Save results locally; identify data coverage and omissions rather than claiming completeness without checking.
