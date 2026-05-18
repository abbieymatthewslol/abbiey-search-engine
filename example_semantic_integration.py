"""
Example integration of semantic parser into search API.

This shows how to use the enhanced query understanding to provide
better results for queries like "ex steals dog".
"""

from query_understanding import preprocess_query
from semantic_parser import rerank_results_by_semantic_relevance, SEMANTIC_PARSER_AVAILABLE


def search_with_semantic_understanding(query: str, initial_results: list) -> dict:
    """
    Enhanced search function that uses semantic understanding.
    
    Args:
        query: User's search query
        initial_results: Results from search providers
        
    Returns:
        Dict with processed query understanding and reranked results
    """
    
    # Step 1: Preprocess query (includes semantic parsing)
    prep = preprocess_query(query)
    
    # Step 2: Check if semantic understanding is available and useful
    semantic_info = prep.semantic_understanding if SEMANTIC_PARSER_AVAILABLE else None
    
    # Step 3: Rerank results if we have semantic parse
    if semantic_info and semantic_info.get("semantic_parse", {}).get("subject"):
        parse_obj = type('Parse', (), semantic_info["semantic_parse"])()
        reranked_results = rerank_results_by_semantic_relevance(
            query, 
            parse_obj, 
            initial_results
        )
    else:
        reranked_results = initial_results
    
    # Step 4: Build response
    response = {
        "query": {
            "original": prep.original,
            "normalized": prep.normalized,
            "intent": prep.intent,
        },
        "results": reranked_results,
        "understanding": {
            "intent_line": _get_intent_line(prep),
            "needs_legal_help": prep.intent == "legal_crisis",
        },
    }
    
    # Step 5: Add semantic details if available
    if semantic_info:
        response["semantic_analysis"] = {
            "subject": semantic_info["semantic_parse"].get("subject"),
            "verb": semantic_info["semantic_parse"].get("verb"),
            "object": semantic_info["semantic_parse"].get("object"),
            "confidence": semantic_info["semantic_parse"].get("confidence"),
            "suggested_query": semantic_info.get("suggested_clarification"),
        }
        
        # Add legal resources if needed
        if semantic_info.get("needs_legal_resources"):
            response["legal_resources"] = _get_legal_resources(semantic_info)
    
    return response


def _get_intent_line(prep) -> str:
    """Get user-friendly description of intent."""
    if prep.intent == "legal_crisis":
        return "Legal resources · emergency help, legal aid, and next steps"
    elif prep.intent == "local_search":
        return "Near you · local listings and map-friendly results"
    elif prep.intent == "transactional":
        return "Shopping · prices, reviews, and where to buy"
    elif prep.intent == "navigational":
        return "Official pages · sign-in, homepage, and app entry points"
    else:
        return "Information · answers and explanations"


def _get_legal_resources(semantic_info: dict) -> dict:
    """Generate legal resource suggestions based on semantic parse."""
    parse = semantic_info.get("semantic_parse", {})
    obj = parse.get("object", "property")
    
    resources = {
        "emergency_contacts": [],
        "legal_help": [],
        "next_steps": [],
    }
    
    # Pet-specific resources
    if obj in ["dog", "cat", "pet", "puppy", "kitten"]:
        resources["emergency_contacts"] = [
            {
                "name": "Pet FBI",
                "description": "Report stolen pets and search found pets database",
                "url": "https://petfbi.org/",
            },
            {
                "name": "Local Animal Control",
                "description": "Report the theft to your local animal control",
                "action": "search_local",
            },
        ]
        resources["next_steps"] = [
            "File a police report immediately",
            "Document proof of ownership (vet records, photos, microchip)",
            "Check local animal shelters and rescue groups",
            "Post on social media and lost pet websites",
            "Consider hiring a pet detective",
        ]
    
    # General property theft resources
    resources["legal_help"] = [
        {
            "name": "Legal Aid",
            "description": "Free legal assistance for qualifying individuals",
            "action": "search_legal_aid",
        },
        {
            "name": "Small Claims Court",
            "description": "Sue for return of property or compensation",
            "action": "search_small_claims",
        },
        {
            "name": "Family Law Attorney",
            "description": "Consult with a lawyer about your rights",
            "action": "search_family_lawyer",
        },
    ]
    
    return resources


# Example usage
if __name__ == "__main__":
    # Simulate the problematic query
    query = "where to go when ex steals dog"
    
    # Mock initial search results (what the old system would return)
    mock_results = [
        {
            "title": "Funny Dogs Stealing People's Seats Compilation",
            "snippet": "Watch hilarious videos of dogs stealing their owner's spots on the couch...",
            "url": "https://example.com/funny-dogs",
            "relevance_score": 1.0,
        },
        {
            "title": "Why Does My Dog Steal My Seat?",
            "snippet": "Animal behavior experts explain why dogs take your seat when you get up...",
            "url": "https://example.com/dog-behavior",
            "relevance_score": 1.0,
        },
        {
            "title": "What to Do If Your Ex Stole Your Pet - Legal Guide",
            "snippet": "If your ex-partner took your dog, here's the legal steps you can take...",
            "url": "https://example.com/pet-custody-legal",
            "relevance_score": 1.0,
        },
    ]
    
    # Process with semantic understanding
    result = search_with_semantic_understanding(query, mock_results)
    
    # Display results
    print("=" * 80)
    print(f"Query: {result['query']['original']}")
    print(f"Intent: {result['query']['intent']}")
    print(f"Understanding: {result['understanding']['intent_line']}")
    print("=" * 80)
    
    if "semantic_analysis" in result:
        print("\nSemantic Analysis:")
        sa = result['semantic_analysis']
        print(f"  Subject: {sa['subject']}")
        print(f"  Verb: {sa['verb']}")
        print(f"  Object: {sa['object']}")
        print(f"  Confidence: {sa['confidence']}")
        print(f"  Suggested query: {sa['suggested_query']}")
    
    print("\nReranked Results:")
    for i, r in enumerate(result['results'][:5], 1):
        score = r.get('semantic_relevance_score', r.get('relevance_score', 0))
        print(f"\n{i}. {r['title']}")
        print(f"   Score: {score:.2f}")
        print(f"   {r['snippet'][:80]}...")
    
    if result['understanding']['needs_legal_help'] and 'legal_resources' in result:
        print("\n" + "=" * 80)
        print("Legal Resources:")
        print("=" * 80)
        
        lr = result['legal_resources']
        
        if lr['emergency_contacts']:
            print("\n📞 Emergency Contacts:")
            for contact in lr['emergency_contacts']:
                print(f"  • {contact['name']}: {contact['description']}")
        
        if lr['next_steps']:
            print("\n✓ Next Steps:")
            for step in lr['next_steps']:
                print(f"  {step}")
        
        if lr['legal_help']:
            print("\n⚖️ Legal Help:")
            for help_item in lr['legal_help']:
                print(f"  • {help_item['name']}: {help_item['description']}")
