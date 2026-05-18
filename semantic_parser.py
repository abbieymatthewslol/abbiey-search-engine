"""
Enhanced semantic parsing for queries with complex subject-verb-object relationships.

Addresses the "ex steals dog" problem where traditional parsing incorrectly identifies
the dog as the subject. Uses NER, dependency parsing simulation, and context-aware
intent classification.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

# Relationship actors that should be weighted as human subjects
RELATIONSHIP_ACTORS = {
    "ex", "ex-boyfriend", "ex-girlfriend", "ex-bf", "ex-gf", 
    "ex-wife", "ex-husband", "ex-spouse", "ex-partner", 
    "former partner", "former boyfriend", "former girlfriend",
    "ex boyfriend", "ex girlfriend", "ex wife", "ex husband",
    "landlord", "neighbor", "neighbour", "roommate", "flatmate",
    "boss", "coworker", "colleague", "manager", "supervisor"
}

# Legal/crisis verbs that signal property disputes or theft
LEGAL_ACTION_VERBS = {
    "steal", "steals", "stole", "stolen", 
    "take", "takes", "took", "taken",
    "hide", "hides", "hid", "hidden",
    "keep", "keeps", "kept", "keeping",
    "refuse", "refuses", "refused",
    "withhold", "withholds", "withheld"
}

# Property that can be stolen/taken (not actors)
PROPERTY_NOUNS = {
    "dog", "dogs", "cat", "cats", "pet", "pets", "puppy", "puppies", "kitten", "kittens",
    "car", "vehicle", "truck", "motorcycle", "bike", "bicycle",
    "phone", "laptop", "computer", "ipad", "tablet", "watch",
    "money", "cash", "wallet", "purse", "jewelry", "jewellery",
    "keys", "passport", "documents", "papers", "mail",
    "furniture", "couch", "tv", "television"
}

# Crisis/legal intent signals
CRISIS_LEGAL_SIGNALS = {
    "help", "legal", "law", "lawyer", "attorney", "police", "court",
    "custody", "stolen", "theft", "restraining order", "sue", "rights",
    "report", "file complaint", "charges", "illegal", "crime"
}


@dataclass
class SemanticParse:
    """Structured semantic parse result"""
    subject: Optional[str] = None  # Who is doing the action
    verb: Optional[str] = None  # The action
    object: Optional[str] = None  # What is being acted upon
    intent_category: str = "informational"  # legal_crisis, informational, navigational
    confidence: float = 0.0
    explanation: str = ""


def identify_subject_verb_object(query: str) -> SemanticParse:
    """
    Parse query to identify subject (actor), verb (action), and object (patient).
    
    Example: "ex steals dog" -> subject=ex, verb=steals, object=dog
    """
    query_lower = query.lower().strip()
    tokens = query_lower.split()
    
    result = SemanticParse()
    
    # Pattern 1: [relationship actor] + [legal verb] + [property]
    # e.g., "ex steals dog", "landlord took my car"
    for i, token in enumerate(tokens):
        # Clean possessives
        clean_token = token.rstrip("'s")
        
        # Check for relationship actor at start
        if clean_token in RELATIONSHIP_ACTORS or f"{clean_token} {tokens[i+1] if i+1 < len(tokens) else ''}" in RELATIONSHIP_ACTORS:
            result.subject = clean_token
            result.confidence = 0.9
            
            # Find verb after subject
            for j in range(i+1, min(i+4, len(tokens))):
                verb_candidate = tokens[j]
                if verb_candidate in LEGAL_ACTION_VERBS:
                    result.verb = verb_candidate
                    
                    # Find object after verb
                    for k in range(j+1, min(j+4, len(tokens))):
                        obj_candidate = tokens[k].rstrip("s")  # handle plurals
                        if obj_candidate in PROPERTY_NOUNS or tokens[k] in PROPERTY_NOUNS:
                            result.object = tokens[k]
                            result.confidence = 0.95
                            break
                    break
            
            if result.subject and result.verb and result.object:
                break
    
    # Pattern 2: Question form - "where to go when ex steals dog"
    # Extract the core relationship from question context
    if not result.subject and any(q in query_lower for q in ["where to", "what to do", "how to", "who to call"]):
        for rel in RELATIONSHIP_ACTORS:
            if rel in query_lower:
                result.subject = rel
                result.confidence = 0.85
                
                for verb in LEGAL_ACTION_VERBS:
                    if verb in query_lower:
                        result.verb = verb
                        
                        for prop in PROPERTY_NOUNS:
                            if prop in query_lower:
                                result.object = prop
                                break
                        break
                break
    
    # Classify intent
    if result.subject and result.verb and result.object:
        if any(sig in query_lower for sig in CRISIS_LEGAL_SIGNALS):
            result.intent_category = "legal_crisis"
            result.explanation = f"Detected legal/crisis situation: {result.subject} {result.verb} {result.object}"
        else:
            result.intent_category = "informational"
            result.explanation = f"Informational query about: {result.subject} {result.verb} {result.object}"
    
    return result


def rerank_results_by_semantic_relevance(
    query: str, 
    parse: SemanticParse, 
    results: List[Dict]
) -> List[Dict]:
    """
    Rerank search results based on semantic parse.
    
    Downrank results that misinterpret the query (e.g., "dog stealing seat" 
    for "ex steals dog" queries).
    """
    if not parse.subject or not parse.verb or not parse.object:
        return results
    
    query_lower = query.lower()
    
    # Patterns that indicate misinterpretation
    wrong_subject_patterns = [
        f"{parse.object}.*{parse.verb}",  # "dog steals" when ex is subject
        f"{parse.object}.*steal.*seat",   # "dog stealing seat"
        f"{parse.object}.*steal.*spot",   # "dog stealing spot"  
        f"{parse.object}.*steal.*couch",  # "dog stealing couch"
    ]
    
    # Correct interpretation patterns
    correct_patterns = [
        f"{parse.subject}.*{parse.verb}.*{parse.object}",  # "ex steals dog"
        "custody",
        "legal",
        "stolen pet",
        "recover",
        "report",
    ]
    
    scored_results = []
    for result in results:
        title = result.get("title", "").lower()
        snippet = result.get("snippet", "").lower()
        combined = f"{title} {snippet}"
        
        relevance_score = result.get("relevance_score", 1.0)
        
        # Penalize misinterpretations
        for pattern in wrong_subject_patterns:
            if re.search(pattern, combined, re.I):
                relevance_score *= 0.3  # Heavy penalty
                break
        
        # Boost correct interpretations
        for pattern in correct_patterns:
            if re.search(pattern, combined, re.I):
                relevance_score *= 1.5
                break
        
        result["semantic_relevance_score"] = relevance_score
        scored_results.append(result)
    
    # Sort by semantic relevance
    scored_results.sort(key=lambda r: r.get("semantic_relevance_score", 0), reverse=True)
    
    return scored_results


def suggest_query_clarification(parse: SemanticParse, original_query: str) -> Optional[str]:
    """
    Suggest a clarified query if the semantic parse indicates potential ambiguity.
    """
    if parse.intent_category == "legal_crisis" and parse.subject and parse.object:
        # Suggest legal help query
        return f"{parse.subject} stole my {parse.object} legal help"
    
    if parse.subject and parse.verb and parse.object:
        # Suggest more specific query
        return f"{parse.subject} {parse.verb} {parse.object} what to do"
    
    return None


def detect_word_sense(verb: str, context_words: List[str]) -> str:
    """
    Disambiguate verb senses based on context.
    
    Example: "steal" can mean:
    - theft (taking property) <- with ex, dog, legal context
    - moving quietly
    - taking someone's seat/spot <- with dog, couch, funny context
    """
    context_set = set(w.lower() for w in context_words)
    
    if verb in LEGAL_ACTION_VERBS:
        # Theft sense indicators
        theft_indicators = RELATIONSHIP_ACTORS | PROPERTY_NOUNS | CRISIS_LEGAL_SIGNALS
        if context_set & theft_indicators:
            return "theft"
        
        # Casual/funny sense indicators  
        casual_indicators = {"seat", "spot", "couch", "bed", "funny", "cute", "hilarious"}
        if context_set & casual_indicators:
            return "casual_action"
    
    return "unknown"


def enhance_query_understanding(query: str) -> Dict:
    """
    Main entry point: comprehensive semantic analysis of query.
    
    Returns enhanced understanding with:
    - Semantic parse (subject, verb, object)
    - Intent classification
    - Suggested clarifications
    - Reranking signals
    """
    parse = identify_subject_verb_object(query)
    
    tokens = query.lower().split()
    verb_sense = None
    if parse.verb:
        verb_sense = detect_word_sense(parse.verb, tokens)
    
    clarification = suggest_query_clarification(parse, query)
    
    return {
        "semantic_parse": {
            "subject": parse.subject,
            "verb": parse.verb,
            "object": parse.object,
            "confidence": parse.confidence,
            "explanation": parse.explanation,
        },
        "intent_category": parse.intent_category,
        "verb_sense": verb_sense,
        "suggested_clarification": clarification,
        "needs_legal_resources": parse.intent_category == "legal_crisis",
    }
