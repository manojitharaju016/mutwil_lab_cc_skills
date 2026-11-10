# CSV Schema Quick Reference

This file documents the bundled CSV exporter, not a research extraction protocol.
The bundled prompt is a short generic template. Keep project-specific extraction
rules, category lists, and worked examples in a private prompt outside this repository.

## 26 CSV Columns (in this order)

The merged CSV must have these columns in this exact order:

```
custom_id, journal, year, month, title, section, filename,
source, source_identifier, source_type, source_category,
source_extracted_definition, source_generated_definition,
relationship, relationship_category,
target, target_identifier, target_type, target_category,
target_extracted_definition, target_generated_definition,
species, basis,
extracted_associated_process_or_pathway, generated_associated_process_or_pathway,
relevant_citations
```

## Citation Flattening (for CSV)

The `relevant_citations` column joins all citation objects from a single triple with `; ` between entries, and `|` between text and key inside each entry:

```
text1 | key1; text2 | key2; text3 | key3
```

Empty list → empty string.
