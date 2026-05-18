# Quick Start: Using the Semantic Parser

## Installation

No installation needed! The semantic parser is pure Python with no external dependencies.

## Basic Usage

### 1. Simple Query Analysis

```python
from semantic_parser import identify_subject_verb_object

query = "ex steals dog"
parse = identify_subject_verb_object(query)

print(f"Subject: {parse.subject}")   # "ex"
print(f"Verb: {parse.verb}")         # "steals"
print(f"Object: {parse.object}")     # "dog"
print(f"Intent: {parse.intent_category}")  # "legal_crisis"
```

### 2. Enhanced Query Understanding

```python
from semantic_parser import enhance_query_understanding

query = "where to go when landlord took my car"
understanding = enhance_query_understanding(query)

print(understanding)
# {
#   "semantic_parse": {
#     "subject": "landlord",
#     "verb": "took",
#     "object": "car",
#     "confidence": 0.95
#   },
#   "intent_category": "legal_crisis",
#   "needs_legal_resources": True,
#   "suggested_clarification": "landlord took my car legal help"
# }
```

### 3. Result Reranking

```python
from semantic_parser import rerank_results_by_semantic_relevance

query = "ex steals dog"
parse = identify_subject_verb_object(query)

results = [
    {"title": "Dog Steals Seat", "snippet": "...", "relevance_score": 1.0},
    {"title": "Ex Stole Pet Legal Help", "snippet": "...", "relevance_score": 1.0},
]

reranked = rerank_results_by_semantic_relevance(query, parse, results)
# Correct results will be ranked higher
```

### 4. Integrated with Query Preprocessing

```python
from query_understanding import preprocess_query

query = "where to go when ex steals dog"
prep = preprocess_query(query)

print(f"Intent: {prep.intent}")  # "legal_crisis"
print(f"Semantic: {prep.semantic_understanding}")
# Includes full semantic parse + suggestions
```

## API Integration

### Flask Route Example

```python
from flask import Flask, request, jsonify
from query_understanding import preprocess_query
from semantic_parser import rerank_results_by_semantic_relevance

app = Flask(__name__)

@app.route('/search')
def search():
    query = request.args.get('q', '')
    
    # Preprocess with semantic understanding
    prep = preprocess_query(query)
    
    # Get search results from your providers
    results = your_search_function(prep.normalized)
    
    # Rerank if semantic parse available
    if prep.semantic_understanding:
        parse_dict = prep.semantic_understanding['semantic_parse']
        # Convert dict to object
        parse_obj = type('Parse', (), parse_dict)()
        results = rerank_results_by_semantic_relevance(
            query, parse_obj, results
        )
    
    return jsonify({
        'query': prep.original,
        'intent': prep.intent,
        'results': results,
        'semantic': prep.semantic_understanding
    })
```

## Configuration

### Adding New Relationship Actors

Edit `semantic_parser.py`:

```python
RELATIONSHIP_ACTORS = {
    "ex", "landlord", "roommate",
    # Add your custom actors
    "business partner", "cofounder", "investor",
}
```

### Adding New Legal Verbs

```python
LEGAL_ACTION_VERBS = {
    "steal", "take", "hide",
    # Add your custom verbs
    "embezzle", "misappropriate", "convert",
}
```

### Adding New Property Nouns

```python
PROPERTY_NOUNS = {
    "dog", "car", "money",
    # Add your custom property
    "intellectual property", "trade secrets", "client list",
}
```

## Common Patterns

### Check if Legal Crisis

```python
prep = preprocess_query(query)
if prep.intent == "legal_crisis":
    # Show legal resources
    display_legal_help()
```

### Get Suggested Query

```python
understanding = enhance_query_understanding(query)
suggestion = understanding.get('suggested_clarification')
if suggestion:
    print(f"Did you mean: {suggestion}?")
```

### Check Confidence Level

```python
parse = identify_subject_verb_object(query)
if parse.confidence > 0.9:
    # High confidence - use semantic understanding
    use_semantic_results()
else:
    # Low confidence - fall back to standard search
    use_standard_search()
```

## Error Handling

The semantic parser is designed to fail gracefully:

```python
try:
    from semantic_parser import enhance_query_understanding
    SEMANTIC_AVAILABLE = True
except ImportError:
    SEMANTIC_AVAILABLE = False

if SEMANTIC_AVAILABLE:
    understanding = enhance_query_understanding(query)
else:
    # Fall back to standard processing
    understanding = None
```

## Testing

### Run Test Suite

```bash
cd C:\Users\pc\abbiey-search-engine-2
python test_semantic_parser.py
```

### Quick Test

```python
from semantic_parser import identify_subject_verb_object

test_queries = [
    "ex steals dog",
    "landlord took car",
    "roommate hid keys",
]

for query in test_queries:
    parse = identify_subject_verb_object(query)
    print(f"{query} -> {parse.subject} {parse.verb} {parse.object}")
```

## Performance Tips

1. **Cache results** for repeated queries
2. **Skip reranking** if confidence < 0.8
3. **Limit reranking** to top 50 results
4. **Use async** for large result sets

```python
# Example caching
from functools import lru_cache

@lru_cache(maxsize=1000)
def cached_parse(query: str):
    return identify_subject_verb_object(query)
```

## Debugging

### Enable verbose output

```python
parse = identify_subject_verb_object(query)
print(f"Confidence: {parse.confidence}")
print(f"Explanation: {parse.explanation}")
```

### Check word sense

```python
from semantic_parser import detect_word_sense

sense = detect_word_sense("steals", ["ex", "dog"])
print(f"Detected sense: {sense}")  # "theft"

sense2 = detect_word_sense("steals", ["dog", "couch"])
print(f"Detected sense: {sense2}")  # "casual_action"
```

## Troubleshooting

### Query not being classified as legal_crisis

Check if keywords are in dictionaries:
```python
from semantic_parser import RELATIONSHIP_ACTORS, LEGAL_ACTION_VERBS

print("ex" in RELATIONSHIP_ACTORS)  # Should be True
print("steals" in LEGAL_ACTION_VERBS)  # Should be True
```

### Results not being reranked

Ensure semantic parse has required fields:
```python
parse = identify_subject_verb_object(query)
assert parse.subject is not None
assert parse.verb is not None
assert parse.object is not None
```

### Low confidence scores

Add more specific patterns or increase weights:
```python
# In semantic_parser.py
if result.subject and result.verb and result.object:
    result.confidence = 0.95  # Increase from 0.85
```

## Next Steps

1. **Deploy to production** - Add to your Flask app
2. **Monitor metrics** - Track legal_crisis detection rate
3. **Collect feedback** - A/B test with/without semantic parsing
4. **Extend patterns** - Add domain-specific entities
5. **Add ML model** - Optional: Replace rules with trained model

## Support

For issues or questions:
1. Check `SEMANTIC_PARSER_README.md` for detailed docs
2. Review `BEFORE_AFTER_COMPARISON.md` for examples
3. Run `test_semantic_parser.py` to verify installation
4. See `example_semantic_integration.py` for full integration

## License

Same as parent project (abbiey-search-engine-2)
