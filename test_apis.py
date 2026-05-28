#!/usr/bin/env python3
"""
Comprehensive API validation test for abbieysearch.com
Tests all major endpoints for correctness, proper responses, and no AI slop.
"""

import json
import requests
import sys

BASE_URL = "http://127.0.0.1:8000"

def test_endpoint(name, method, path, params=None, json_data=None, expected_status=200, check_content=True):
    """Test an endpoint and report results."""
    url = f"{BASE_URL}{path}"
    try:
        if method == "GET":
            resp = requests.get(url, params=params, timeout=10)
        elif method == "POST":
            resp = requests.post(url, json=json_data, timeout=10)
        else:
            return False, f"Unknown method {method}"
        
        status_ok = resp.status_code == expected_status
        content_ok = True
        content_info = ""
        
        if check_content and status_ok:
            try:
                data = resp.json()
                content_info = f" | {len(json.dumps(data))} chars"
                if isinstance(data, dict) and "error" in data:
                    content_ok = False
                    content_info += " | ERROR in response"
            except:
                content_info = f" | {len(resp.text)} chars (non-JSON)"
        
        status = "✓" if (status_ok and content_ok) else "✗"
        print(f"{status} {name}: {resp.status_code}{content_info}")
        return status_ok and content_ok, resp.json() if resp.text else None
    except Exception as e:
        print(f"✗ {name}: {str(e)}")
        return False, None

def main():
    print("\n" + "="*70)
    print("ABBIEYSEARCH API VALIDATION TEST")
    print("="*70 + "\n")
    
    passed = 0
    failed = 0
    
    # ---- PUBLIC ENDPOINTS (NO AUTH) ----
    print("[PUBLIC ENDPOINTS - No Authentication Required]\n")
    
    ok, _ = test_endpoint("1. GET /api/suggestions", "GET", "/api/suggestions", params={"q": "python"})
    passed += ok; failed += not ok
    
    ok, _ = test_endpoint("2. GET /api/trends", "GET", "/api/trends")
    passed += ok; failed += not ok
    
    ok, _ = test_endpoint("3. GET /api/privacy-stats", "GET", "/api/privacy-stats")
    passed += ok; failed += not ok
    
    ok, _ = test_endpoint("4. GET /api/knowledge-graph", "GET", "/api/knowledge-graph", params={"q": "python"})
    passed += ok; failed += not ok
    
    ok, _ = test_endpoint("5. GET /api/open-catalog", "GET", "/api/open-catalog", params={"q": "machine learning"})
    passed += ok; failed += not ok
    
    ok, _ = test_endpoint("6. GET /search (HTML page)", "GET", "/search", params={"q": "what is machine learning"}, 
                         expected_status=200, check_content=False)
    passed += ok; failed += not ok
    
    # ---- PROTECTED ENDPOINTS (NEED AUTH OR CONTEXT) ----
    print("\n[PROTECTED/CONTEXTUAL ENDPOINTS]\n")
    
    ok, _ = test_endpoint("7. POST /api/chat (no prior search)", "POST", "/api/chat", 
                         json_data={"q": "what is python?"}, expected_status=400)
    passed += ok; failed += not ok
    
    ok, _ = test_endpoint("8. GET /api/research-chats", "GET", "/api/research-chats", expected_status=200)
    passed += ok; failed += not ok
    
    # ---- REVERSE IMAGE ENDPOINT ----
    print("\n[REVERSE IMAGE ENDPOINT]\n")
    
    ok, _ = test_endpoint("9. POST /api/reverse-image (no image)", "POST", "/api/reverse-image", 
                         expected_status=400)
    passed += ok; failed += not ok
    
    # ---- API V1 ENDPOINT (requires auth) ----
    print("\n[/api/v1 ENDPOINTS (Requires Bearer Token)]\n")
    
    try:
        resp = requests.get(f"{BASE_URL}/api/v1/search", params={"query": "python"}, timeout=10)
        if resp.status_code == 401:
            print("✓ 10. GET /api/v1/search: Returns 401 (auth required) - CORRECT BEHAVIOR")
            passed += 1
        else:
            print(f"✗ 10. GET /api/v1/search: Unexpected status {resp.status_code} (expected 401)")
            failed += 1
    except Exception as e:
        print(f"✗ 10. GET /api/v1/search: {str(e)}")
        failed += 1
    
    # ---- SUMMARY ----
    print("\n" + "="*70)
    print(f"RESULTS: {passed} passed, {failed} failed")
    if failed == 0:
        print("✓ All API endpoints responding correctly!")
    else:
        print(f"✗ {failed} endpoint(s) failed validation")
    print("="*70 + "\n")
    
    return 0 if failed == 0 else 1

if __name__ == "__main__":
    sys.exit(main())
