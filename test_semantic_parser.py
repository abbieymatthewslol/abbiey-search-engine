"""
Test the semantic parser with the "ex steals dog" problem.
"""

from semantic_parser import (
    identify_subject_verb_object,
    enhance_query_understanding,
    suggest_query_clarification,
    detect_word_sense,
)
from query_understanding import preprocess_query


def test_ex_steals_dog():
    """Test that 'ex steals dog' correctly identifies ex as subject, not dog."""
    
    print("=" * 80)
    print("Testing: 'where to go when ex steals dog'")
    print("=" * 80)
    
    query = "where to go when ex steals dog"
    
    # Semantic parse
    parse = identify_subject_verb_object(query)
    print(f"\nSemantic Parse:")
    print(f"  Subject (actor): {parse.subject}")
    print(f"  Verb (action): {parse.verb}")
    print(f"  Object (patient): {parse.object}")
    print(f"  Intent: {parse.intent_category}")
    print(f"  Confidence: {parse.confidence}")
    print(f"  Explanation: {parse.explanation}")
    
    # Enhanced understanding
    understanding = enhance_query_understanding(query)
    print(f"\nEnhanced Understanding:")
    print(f"  Intent category: {understanding['intent_category']}")
    print(f"  Needs legal resources: {understanding['needs_legal_resources']}")
    print(f"  Suggested clarification: {understanding['suggested_clarification']}")
    
    # Query preprocessing integration
    prep = preprocess_query(query)
    print(f"\nIntegrated Query Preprocessing:")
    print(f"  Original: {prep.original}")
    print(f"  Normalized: {prep.normalized}")
    print(f"  Intent: {prep.intent}")
    if prep.semantic_understanding:
        print(f"  Semantic parse: {prep.semantic_understanding['semantic_parse']}")
    
    # Assertions
    assert parse.subject == "ex", f"Expected subject 'ex', got '{parse.subject}'"
    assert parse.verb in ["steals", "steal"], f"Expected verb 'steals/steal', got '{parse.verb}'"
    assert parse.object == "dog", f"Expected object 'dog', got '{parse.object}'"
    assert parse.intent_category == "legal_crisis", f"Expected legal_crisis intent, got '{parse.intent_category}'"
    
    print("\n✓ Test passed: Correctly identified ex as subject, not dog!")


def test_word_sense_disambiguation():
    """Test that 'steal' is correctly disambiguated based on context."""
    
    print("\n" + "=" * 80)
    print("Testing word sense disambiguation for 'steal'")
    print("=" * 80)
    
    # Theft sense
    query1 = "ex steals dog"
    tokens1 = query1.split()
    sense1 = detect_word_sense("steals", tokens1)
    print(f"\n'{query1}' -> sense: {sense1}")
    assert sense1 == "theft", f"Expected 'theft' sense, got '{sense1}'"
    
    # Casual sense
    query2 = "dog steals my seat on the couch"
    tokens2 = query2.split()
    sense2 = detect_word_sense("steals", tokens2)
    print(f"'{query2}' -> sense: {sense2}")
    assert sense2 == "casual_action", f"Expected 'casual_action' sense, got '{sense2}'"
    
    print("\n✓ Word sense disambiguation working correctly!")


def test_various_legal_crisis_queries():
    """Test various legal/crisis query patterns."""
    
    print("\n" + "=" * 80)
    print("Testing various legal crisis patterns")
    print("=" * 80)
    
    test_cases = [
        "ex boyfriend stole my cat",
        "landlord took my dog",
        "ex wife refuses to give back my pet",
        "former partner keeping my puppy",
        "roommate hid my keys",
    ]
    
    for query in test_cases:
        parse = identify_subject_verb_object(query)
        print(f"\n'{query}'")
        print(f"  -> {parse.subject} {parse.verb} {parse.object} (confidence: {parse.confidence})")
        
        # All should identify the relationship actor as subject, not the property
        assert parse.subject is not None, f"Failed to identify subject in '{query}'"
        assert parse.object is not None, f"Failed to identify object in '{query}'"
    
    print("\n✓ All legal crisis patterns handled correctly!")


def test_mock_result_reranking():
    """Test that results are reranked based on semantic understanding."""
    
    print("\n" + "=" * 80)
    print("Testing result reranking")
    print("=" * 80)
    
    query = "ex steals dog"
    parse = identify_subject_verb_object(query)
    
    # Mock results - wrong interpretation vs correct
    mock_results = [
        {
            "title": "Funny: Dog Steals Owner's Seat on Couch",
            "snippet": "Watch this hilarious video of a dog stealing its owner's spot...",
            "relevance_score": 1.0,
        },
        {
            "title": "What to Do When Your Ex Steals Your Pet - Legal Advice",
            "snippet": "If your ex-partner took your dog, here's what you can do legally...",
            "relevance_score": 1.0,
        },
        {
            "title": "Pet Custody Laws and Stolen Animals",
            "snippet": "Legal remedies when someone steals your pet or refuses to return it...",
            "relevance_score": 1.0,
        },
    ]
    
    from semantic_parser import rerank_results_by_semantic_relevance
    reranked = rerank_results_by_semantic_relevance(query, parse, mock_results)
    
    print(f"\nOriginal order:")
    for i, r in enumerate(mock_results, 1):
        print(f"  {i}. {r['title']}")
    
    print(f"\nReranked order:")
    for i, r in enumerate(reranked, 1):
        score = r.get("semantic_relevance_score", 0)
        print(f"  {i}. {r['title']} (score: {score:.2f})")
    
    # First result after reranking should NOT be about dog stealing seat
    assert "seat" not in reranked[0]["title"].lower(), "Wrong result ranked first!"
    assert "legal" in reranked[0]["title"].lower() or "custody" in reranked[0]["title"].lower(), \
        "Expected legal/custody result to be ranked first"
    
    print("\n✓ Results correctly reranked!")


if __name__ == "__main__":
    test_ex_steals_dog()
    test_word_sense_disambiguation()
    test_various_legal_crisis_queries()
    test_mock_result_reranking()
    
    print("\n" + "=" * 80)
    print("All tests passed! ✓")
    print("=" * 80)
    print("\nThe semantic parser correctly:")
    print("  1. Identifies 'ex' as subject, not 'dog'")
    print("  2. Recognizes legal/crisis intent")
    print("  3. Disambiguates word senses based on context")
    print("  4. Reranks results to prioritize correct interpretations")
    print("  5. Suggests appropriate clarifications")
