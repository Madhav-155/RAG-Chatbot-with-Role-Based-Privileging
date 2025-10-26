#!/usr/bin/env python3
"""
Comprehensive Test Suite for RAG Chatbot with RBAC
Tests different roles with SQL and RAG queries
Generates a detailed performance report
"""

import sys
import time
import requests
from requests.auth import HTTPBasicAuth
from datetime import datetime

API_URL = "http://localhost:8000"

# Test user credentials for different roles
TEST_USERS = {
    "C-Level": ("admin", "admin123"),
    "HR": ("hr", "hr123"),
    "Finance": ("finance", "finance123"),
    "Marketing": ("marketing", "marketing123"),
    "Engineering": ("engineering", "engineering123"),
    "General": ("general", "general123")
}

# Test queries organized by type and complexity
TEST_QUERIES = {
    "SQL_BASIC": [
        "Show me all employees in the Finance department",
        "How many employees are there in total?",
        "List employees with performance rating 5",
        "Give me employees in Mumbai location",
        "Show me employees from HR department"
    ],
    "SQL_ADVANCED": [
        "Give me details of employees whose performance rating is between 3 and 5",
        "Show me people who has performance rating 4 and above from finance department",
        "What is the average salary in the Data department?",
        "Find employees with rating greater than 3 in Engineering",
        "Give me top performers (rating 5) in Marketing department"
    ],
    "SQL_AGGREGATION": [
        "How many employees have performance rating above 4?",
        "Count total employees in each department",
        "What is the highest performance rating?",
        "Show me departments with most employees",
        "Count employees hired in 2023"
    ],
    "RAG_GENERAL": [
        "What is the company's mission?",
        "Tell me about employee benefits",
        "Explain the leave policy",
        "What are the company holidays?",
        "Summarize the employee handbook"
    ],
    "RAG_DOMAIN_SPECIFIC": [
        "Summarize the Q4 2024 marketing report",
        "What were the marketing highlights in Q1 2024?",
        "Tell me about the financial performance",
        "What are the engineering best practices?",
        "Explain the compliance policies"
    ],
    "RAG_COMPLEX": [
        "What is the company's marketing strategy for 2024?",
        "Summarize the quarterly financial report",
        "What are the key insights from marketing campaigns?",
        "Tell me about the company's technology stack",
        "Explain the recruitment process"
    ]
}

class TestResult:
    def __init__(self):
        self.total_tests = 0
        self.successful = 0
        self.failed = 0
        self.timeouts = 0
        self.access_denied = 0
        self.total_time = 0
        self.results = []
    
    def add_result(self, role, query, status, response_time, mode=None, error=None):
        self.total_tests += 1
        self.total_time += response_time
        
        result = {
            "role": role,
            "query": query,
            "status": status,
            "response_time": round(response_time, 2),
            "mode": mode,
            "error": error
        }
        
        if status == "SUCCESS":
            self.successful += 1
        elif status == "FAILED":
            self.failed += 1
        elif status == "TIMEOUT":
            self.timeouts += 1
        elif status == "ACCESS_DENIED":
            self.access_denied += 1
        
        self.results.append(result)
        
    def get_summary(self):
        avg_time = self.total_time / self.total_tests if self.total_tests > 0 else 0
        success_rate = (self.successful / self.total_tests * 100) if self.total_tests > 0 else 0
        
        return {
            "total_tests": self.total_tests,
            "successful": self.successful,
            "failed": self.failed,
            "timeouts": self.timeouts,
            "access_denied": self.access_denied,
            "success_rate": round(success_rate, 2),
            "average_response_time": round(avg_time, 2),
            "total_time": round(self.total_time, 2)
        }

def test_login(username, password):
    """Test login for a user"""
    try:
        response = requests.get(
            f"{API_URL}/login",
            auth=HTTPBasicAuth(username, password),
            timeout=10
        )
        return response.status_code == 200
    except Exception as e:
        print(f"   ❌ Login failed for {username}: {e}")
        return False

def test_query(username, password, role, query, timeout=150):
    """Test a single query"""
    start_time = time.time()
    
    try:
        response = requests.post(
            f"{API_URL}/chat",
            json={"question": query},
            auth=HTTPBasicAuth(username, password),
            timeout=timeout
        )
        
        response_time = time.time() - start_time
        
        if response.status_code == 200:
            data = response.json()
            mode = data.get("mode", "UNKNOWN")
            answer = data.get("answer", "")
            
            # Check for access denied
            if "access denied" in answer.lower() or "denied" in answer.lower():
                return "ACCESS_DENIED", response_time, mode, "Access denied"
            
            # Check for errors
            if "error" in answer.lower() or "failed" in answer.lower():
                return "FAILED", response_time, mode, answer[:100]
            
            return "SUCCESS", response_time, mode, None
        else:
            return "FAILED", response_time, None, f"HTTP {response.status_code}"
            
    except requests.exceptions.Timeout:
        response_time = time.time() - start_time
        return "TIMEOUT", response_time, None, "Request timeout"
    except Exception as e:
        response_time = time.time() - start_time
        return "FAILED", response_time, None, str(e)

def run_tests():
    """Run all tests"""
    print("=" * 80)
    print("🧪 COMPREHENSIVE RAG CHATBOT TEST SUITE")
    print("=" * 80)
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    overall_results = TestResult()
    role_results = {}
    category_results = {}
    
    # Test each role
    for role, (username, password) in TEST_USERS.items():
        print(f"\n{'='*80}")
        print(f"Testing Role: {role} (User: {username})")
        print(f"{'='*80}")
        
        # Test login
        print(f"   🔐 Testing login...")
        if not test_login(username, password):
            print(f"   ❌ Skipping {role} - login failed")
            continue
        print(f"   ✅ Login successful")
        
        role_results[role] = TestResult()
        
        # Test each query category
        for category, queries in TEST_QUERIES.items():
            print(f"\n   📋 Category: {category}")
            
            if category not in category_results:
                category_results[category] = TestResult()
            
            for i, query in enumerate(queries, 1):
                print(f"      Query {i}/{len(queries)}: {query[:60]}...")
                
                status, response_time, mode, error = test_query(username, password, role, query)
                
                # Record results
                overall_results.add_result(role, query, status, response_time, mode, error)
                role_results[role].add_result(role, query, status, response_time, mode, error)
                category_results[category].add_result(role, query, status, response_time, mode, error)
                
                # Print result
                status_icon = {
                    "SUCCESS": "✅",
                    "FAILED": "❌",
                    "TIMEOUT": "⏱️",
                    "ACCESS_DENIED": "🔒"
                }.get(status, "❓")
                
                print(f"         {status_icon} {status} | {response_time:.2f}s | Mode: {mode or 'N/A'}")
                if error:
                    print(f"            Error: {error[:80]}")
                
                # Small delay between queries
                time.sleep(0.5)
    
    # Generate report
    generate_report(overall_results, role_results, category_results)

def generate_report(overall, role_results, category_results):
    """Generate detailed test report"""
    print("\n" + "=" * 80)
    print("📊 TEST REPORT")
    print("=" * 80)
    
    # Overall summary
    summary = overall.get_summary()
    print("\n🎯 OVERALL PERFORMANCE:")
    print(f"   Total Tests: {summary['total_tests']}")
    print(f"   ✅ Successful: {summary['successful']}")
    print(f"   ❌ Failed: {summary['failed']}")
    print(f"   ⏱️  Timeouts: {summary['timeouts']}")
    print(f"   🔒 Access Denied: {summary['access_denied']}")
    print(f"   📈 Success Rate: {summary['success_rate']}%")
    print(f"   ⚡ Average Response Time: {summary['average_response_time']}s")
    print(f"   🕐 Total Test Time: {summary['total_time']}s")
    
    # Role-wise breakdown
    print("\n📋 PERFORMANCE BY ROLE:")
    for role, result in role_results.items():
        role_summary = result.get_summary()
        print(f"\n   {role}:")
        print(f"      Tests: {role_summary['total_tests']}")
        print(f"      Success Rate: {role_summary['success_rate']}%")
        print(f"      Avg Response Time: {role_summary['average_response_time']}s")
    
    # Category-wise breakdown
    print("\n📊 PERFORMANCE BY QUERY TYPE:")
    for category, result in category_results.items():
        cat_summary = result.get_summary()
        print(f"\n   {category}:")
        print(f"      Tests: {cat_summary['total_tests']}")
        print(f"      Success Rate: {cat_summary['success_rate']}%")
        print(f"      Avg Response Time: {cat_summary['average_response_time']}s")
    
    # Performance analysis
    print("\n🔍 PERFORMANCE ANALYSIS:")
    
    sql_categories = ["SQL_BASIC", "SQL_ADVANCED", "SQL_AGGREGATION"]
    rag_categories = ["RAG_GENERAL", "RAG_DOMAIN_SPECIFIC", "RAG_COMPLEX"]
    
    sql_times = []
    rag_times = []
    
    for result in overall.results:
        if result['mode'] == 'SQL':
            sql_times.append(result['response_time'])
        elif result['mode'] == 'RAG':
            rag_times.append(result['response_time'])
    
    if sql_times:
        avg_sql = sum(sql_times) / len(sql_times)
        print(f"   SQL Queries: {len(sql_times)} tests, Avg: {avg_sql:.2f}s")
    
    if rag_times:
        avg_rag = sum(rag_times) / len(rag_times)
        print(f"   RAG Queries: {len(rag_times)} tests, Avg: {avg_rag:.2f}s")
    
    # Slowest queries
    print("\n🐌 TOP 5 SLOWEST QUERIES:")
    sorted_results = sorted(overall.results, key=lambda x: x['response_time'], reverse=True)
    for i, result in enumerate(sorted_results[:5], 1):
        print(f"   {i}. [{result['role']}] {result['query'][:50]}...")
        print(f"      Time: {result['response_time']}s | Mode: {result['mode']} | Status: {result['status']}")
    
    # Failed queries
    failed = [r for r in overall.results if r['status'] != 'SUCCESS']
    if failed:
        print(f"\n❌ FAILED/PROBLEMATIC QUERIES ({len(failed)}):")
        for result in failed[:10]:  # Show first 10
            print(f"\n   [{result['role']}] {result['query']}")
            print(f"      Status: {result['status']} | Time: {result['response_time']}s")
            if result['error']:
                print(f"      Error: {result['error'][:100]}")
    
    # Final verdict
    print("\n" + "=" * 80)
    print("🏆 FINAL VERDICT:")
    print("=" * 80)
    
    if summary['success_rate'] >= 95:
        verdict = "EXCELLENT ⭐⭐⭐⭐⭐"
        details = "Your chatbot is performing exceptionally well!"
    elif summary['success_rate'] >= 85:
        verdict = "VERY GOOD ⭐⭐⭐⭐"
        details = "Your chatbot is working great with minor issues."
    elif summary['success_rate'] >= 70:
        verdict = "GOOD ⭐⭐⭐"
        details = "Your chatbot is working well but needs some improvements."
    elif summary['success_rate'] >= 50:
        verdict = "FAIR ⭐⭐"
        details = "Your chatbot works but has significant issues to address."
    else:
        verdict = "NEEDS IMPROVEMENT ⭐"
        details = "Your chatbot requires major improvements."
    
    print(f"\n   Overall Rating: {verdict}")
    print(f"   {details}")
    
    if summary['average_response_time'] < 10:
        print(f"\n   ✅ Response Time: EXCELLENT (avg {summary['average_response_time']}s)")
    elif summary['average_response_time'] < 30:
        print(f"\n   ✅ Response Time: GOOD (avg {summary['average_response_time']}s)")
    else:
        print(f"\n   ⚠️  Response Time: NEEDS OPTIMIZATION (avg {summary['average_response_time']}s)")
    
    # Recommendations
    print("\n💡 RECOMMENDATIONS:")
    
    if summary['timeouts'] > 0:
        print(f"   • {summary['timeouts']} queries timed out - consider optimizing LLM parameters")
    
    if summary['access_denied'] > summary['total_tests'] * 0.1:
        print(f"   • High access denied rate - verify RBAC permissions")
    
    if summary['failed'] > 0:
        print(f"   • {summary['failed']} queries failed - review error logs and fix issues")
    
    if summary['average_response_time'] > 30:
        print("   • Consider further optimization of query processing")
    
    if summary['success_rate'] == 100:
        print("   • Perfect score! Consider adding more edge cases to test suite")
    
    print("\n" + "=" * 80)
    print(f"Test completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

if __name__ == "__main__":
    print("\n⚠️  PREREQUISITES:")
    print("   1. FastAPI server running on http://localhost:8000")
    print("   2. Ollama service running")
    print("   3. All test users created in database")
    print("\nPress Enter to start testing or Ctrl+C to cancel...")
    input()
    
    run_tests()
    
    print("\n✅ Test suite completed!")
    print("📁 Results are displayed above. Review the summary and recommendations.")
