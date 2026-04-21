# graphql

Strawberry GraphQL layer over [Context-Fabric](https://context-fabric.ai/docs/core)
corpora. Hides Text-Fabric node IDs and short feature codes (`sp`, `lex`, `gn`)
behind readable field names (`partOfSpeech`, `lemma`, `gender`) so frontends can
ask for text the way users read it.

## Quick start

```python
from exegia_graphql import registry, schema

# Load one or more corpora at startup
registry.load("bhsa", "/path/to/bhsa")

# Wire into FastAPI
from strawberry.fastapi import GraphQLRouter
app.include_router(GraphQLRouter(schema), prefix="/graphql")
```

Print the SDL:

```bash
uv run exegia-graphql
```

## Example queries

```graphql
# Look up a verse by reference
{
  verse(corpus: "bhsa", reference: "Genesis 1:1") {
    reference
    text
    words {
      text
      lemma
      partOfSpeech
      gloss
    }
  }
}

# Pull a whole chapter
{
  passage(corpus: "bhsa", reference: "Genesis 1") {
    reference
    text
  }
}

# Structured word search — every option is a typed field, not a pattern string.
# This asks: "every qal-stem verb in Genesis 1". Fields are AND-combined; omit
# any you don't need.
{
  words(
    corpus: "bhsa"
    filter: {
      partOfSpeech: "verb"
      verbStem: "qal"
      book: "Genesis"
      chapter: 1
    }
    limit: 25
  ) {
    text
    lemma
    gloss
    verse { reference }
  }
}

# Escape hatch — run a raw TF/CF pattern when the structured filter isn't
# expressive enough (cross-node constraints, ordering, etc.).
# Syntax: https://context-fabric.ai/docs/concepts/text-fabric-compat
{
  search(corpus: "bhsa", pattern: "word sp=verb vs=qal", limit: 10) {
    reference
    text
  }
}
```

## Public API

- `registry` — process-wide `CorpusRegistry` for loading/resolving corpora.
- `schema` — `strawberry.Schema` ready to mount on FastAPI.
- `Query` — root type, importable for composition with other schemas.
- Types: `Corpus`, `Book`, `Chapter`, `Verse`, `Clause`, `Phrase`, `Word`,
  `SearchMatch`, `WordFilter`.
