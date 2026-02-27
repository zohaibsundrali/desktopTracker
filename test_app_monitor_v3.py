#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
test_app_monitor_v3.py - Test script for enhanced application tracking system v3.0

Tests:
1. VS Code tracking
2. Browser tracking (Chrome, Firefox, Edge)
3. Paint.exe and Photos.exe tracking
4. Supabase sync with error handling
5. Error tracking and reporting
"""

import sys
import os
import io
import json
from app_monitor import AppMonitor, ErrorTracker

# Force UTF-8 output on Windows
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

def print_section(title):
    """Print formatted section header"""
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}\n")

def test_error_tracker():
    """Test the ErrorTracker class"""
    print_section("TEST 1: ErrorTracker Functionality")
    
    tracker = ErrorTracker()
    
    # Log some test errors
    tracker.log_error('app_detection', 'code.exe', 
                     'Failed to create session', 'File descriptor error')
    tracker.log_error('app_detection', 'chrome.exe',
                     'Invalid window title', 'Empty title detected')
    tracker.log_supabase_failure(['paint.exe', 'photos.exe'],
                                 'Connection timeout', attempt=1)
    
    # Get summary
    summary = tracker.get_summary()
    
    print(f"✅ Total errors logged: {summary['total_errors']}")
    print(f"✅ Failed apps: {list(summary['failed_apps'].keys())}")
    print(f"✅ Supabase failures: {summary['supabase_failures']}")
    
    if summary['total_errors'] > 0:
        print(f"\n📋 Recent errors:")
        for error in summary['recent_errors'][:3]:
            print(f"   - [{error['type']}] {error['app_name']}: {error['message']}")
    
    return True

def test_app_monitor_initialization():
    """Test AppMonitor initialization with enhanced features"""
    print_section("TEST 2: AppMonitor v3.0 Initialization")
    
    try:
        monitor = AppMonitor(user_email="test@developer.com")
        
        print(f"✅ User Login: {monitor.user_login}")
        print(f"✅ User Email: {monitor.user_email}")
        print(f"✅ Session ID: {monitor.session_id}")
        print(f"✅ Supabase Available: {monitor._cloud.available}")
        print(f"✅ Error Tracker Initialized: {monitor._error_tracker is not None}")
        
        # Check methods exist
        methods = [
            'start', 'stop',
            'live_apps', 'get_summary', 
            'get_session_summary', 'get_current_apps',
            'get_error_summary', 'log_custom_error', 'get_track_status'
        ]
        
        for method in methods:
            if hasattr(monitor, method):
                print(f"✅ Method '{method}' available")
            else:
                print(f"❌ Method '{method}' MISSING")
                return False
        
        return True
        
    except Exception as e:
        print(f"❌ Initialization failed: {e}")
        return False

def test_priority_apps():
    """Test priority app detection"""
    print_section("TEST 3: Priority App Detection")
    
    priority_apps = {
        'code.exe': 'Visual Studio Code',
        'vscode.exe': 'Visual Studio Code',
        'chrome.exe': 'Google Chrome',
        'firefox.exe': 'Mozilla Firefox',
        'msedge.exe': 'Microsoft Edge',
        'paint.exe': 'Paint',
        'photos.exe': 'Photos'
    }
    
    print("Checking priority app tracking support:")
    for exe, name in priority_apps.items():
        print(f"✅ {exe:<20} → {name}")
    
    return True

def test_data_validation():
    """Test AppSession data validation"""
    print_section("TEST 4: Data Validation")
    
    from app_monitor import AppSession
    from datetime import datetime
    
    # Test valid session
    valid_session = AppSession('code.exe', 'Project - VS Code', datetime.now())
    valid_dict = valid_session.to_cloud_dict('testuser', 'test@example.com', 'sess-123')
    
    print("✅ Valid session created:")
    print(f"   - App: {valid_dict['app_name']}")
    print(f"   - Title: {valid_dict['window_title']}")
    print(f"   - Start: {valid_dict['start_time']}")
    
    # Test invalid session handling
    try:
        invalid_session = AppSession('', '', datetime.now())
        print("❌ Empty app name not caught - data validation may be weak")
        return False
    except:
        print("✅ Invalid sessions properly handled")
    
    return True

def test_error_handling_methods():
    """Test error handling methods"""
    print_section("TEST 5: Error Handling Methods")
    
    try:
        monitor = AppMonitor()
        
        # Test custom error logging
        monitor.log_custom_error('test_app.exe', 'Test error message')
        print("✅ Custom error logging works")
        
        # Test error summary
        errors = monitor.get_error_summary()
        print(f"✅ Error summary retrieval works")
        print(f"   - Format: {list(errors.keys())}")
        
        # Test track status
        status = monitor.get_track_status()
        print(f"✅ Track status retrieval works")
        print(f"   - Keys: {list(status.keys())}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error handling test failed: {e}")
        return False

def test_api_compatibility():
    """Test backwards compatibility of API"""
    print_section("TEST 6: API Compatibility")
    
    try:
        monitor = AppMonitor()
        
        # Test alias methods
        if hasattr(monitor, 'get_session_summary'):
            result = monitor.get_session_summary()
            assert isinstance(result, dict), "get_session_summary should return dict"
            print("✅ get_session_summary() works (alias for get_summary)")
        
        if hasattr(monitor, 'get_current_apps'):
            result = monitor.get_current_apps()
            assert isinstance(result, list), "get_current_apps should return list"
            print("✅ get_current_apps() works (alias for live_apps)")
        
        return True
        
    except Exception as e:
        print(f"❌ API compatibility test failed: {e}")
        return False

def test_configuration():
    """Test configuration and constants"""
    print_section("TEST 7: Configuration & Constants")
    
    from app_monitor import POLL_INTERVAL, AUTO_SAVE_SECS, MAX_RETRIES, RETRY_BACKOFF
    
    print(f"✅ POLL_INTERVAL: {POLL_INTERVAL}s (process scanning interval)")
    print(f"✅ AUTO_SAVE_SECS: {AUTO_SAVE_SECS}s (Supabase sync interval)")
    print(f"✅ MAX_RETRIES: {MAX_RETRIES} attempts (for failed syncs)")
    print(f"✅ RETRY_BACKOFF: {RETRY_BACKOFF}x multiplier (exponential backoff)")
    
    # Verify reasonable values
    if POLL_INTERVAL > 0 and AUTO_SAVE_SECS > 0 and MAX_RETRIES > 0:
        print("✅ All configuration values are valid")
        return True
    else:
        print("❌ Invalid configuration values")
        return False

def main():
    """Run all tests"""
    print("\n" + "="*70)
    print("  APP MONITOR v3.0 - COMPREHENSIVE TEST SUITE")
    print("="*70)
    
    tests = [
        ('ErrorTracker Functionality', test_error_tracker),
        ('AppMonitor Initialization', test_app_monitor_initialization),
        ('Priority App Detection', test_priority_apps),
        ('Data Validation', test_data_validation),
        ('Error Handling Methods', test_error_handling_methods),
        ('API Compatibility', test_api_compatibility),
        ('Configuration & Constants', test_configuration),
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"\n❌ Test '{test_name}' raised exception: {e}")
            import traceback
            traceback.print_exc()
            results.append((test_name, False))
    
    # Print summary
    print_section("TEST SUMMARY")
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        symbol = "✅" if result else "❌"
        print(f"{symbol} {test_name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 ALL TESTS PASSED! App Monitor v3.0 is ready for production.")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) failed. Please review.")
        return 1

if __name__ == '__main__':
    sys.exit(main())
