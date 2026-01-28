# ai_analyzer.py - AI-based productivity insights
import pandas as pd
import numpy as np
from datetime import datetime
import json
from typing import Dict, List
import os

class ProductivityAnalyzer:
    def __init__(self):
        self.patterns = {
            'high_productivity': {
                'keyboard_wpm': 30,
                'mouse_events_per_min': 50,
                'app_productivity': 80,
                'screenshot_variation': 0.3
            },
            'low_productivity': {
                'keyboard_wpm': 10,
                'mouse_events_per_min': 20,
                'app_productivity': 50,
                'screenshot_variation': 0.1
            }
        }
        
    def analyze_session(self, report_path: str) -> Dict:
        """Analyze a session report with AI insights"""
        with open(report_path, 'r') as f:
            report = json.load(f)
            
        insights = {
            'session_id': report['session_info']['session_id'],
            'analysis_date': datetime.now().isoformat(),
            'overall_assessment': '',
            'strengths': [],
            'weaknesses': [],
            'patterns_found': [],
            'recommendations': [],
            'productivity_trend': '',
            'predicted_score_next_session': 0
        }
        
        # Extract metrics
        keyboard_wpm = report['keyboard_tracking'].get('words_per_minute', 0)
        mouse_events = report['mouse_tracking'].get('total_events', 0)
        app_productivity = report['application_tracking'].get('productivity_score', 0)
        duration = report['session_info'].get('duration_minutes', 1)
        
        # Calculate per-minute metrics
        mouse_per_min = mouse_events / duration if duration > 0 else 0
        
        # Analyze patterns
        if keyboard_wpm >= 30 and app_productivity >= 80:
            insights['overall_assessment'] = "High Productivity Session"
            insights['strengths'].append("Excellent keyboard activity")
            insights['strengths'].append("Focused application usage")
            insights['patterns_found'].append("Deep work pattern detected")
            
        elif keyboard_wpm < 10 and app_productivity < 60:
            insights['overall_assessment'] = "Low Productivity Session"
            insights['weaknesses'].append("Low keyboard engagement")
            insights['weaknesses'].append("Distracting applications used")
            insights['patterns_found'].append("Distraction pattern detected")
            
        else:
            insights['overall_assessment'] = "Mixed Productivity Session"
            
        # Generate AI recommendations
        if keyboard_wpm < 20:
            insights['recommendations'].append(
                "Try using typing practice tools to increase your WPM from {:.1f} to 30+".format(keyboard_wpm)
            )
            
        if mouse_per_min < 30:
            insights['recommendations'].append(
                "Consider learning keyboard shortcuts to reduce mouse dependency"
            )
            
        if app_productivity < 70:
            distracting_time = report['application_tracking'].get('distracting_seconds', 0)
            if distracting_time > 300:  # 5 minutes
                insights['recommendations'].append(
                    "You spent {:.1f} minutes on distracting apps. Consider using focus apps.".format(distracting_time/60)
                )
        
        # Predict next session score
        current_score = report['overall_productivity'].get('score', 0)
        if insights['recommendations']:
            # If there are improvements to make, predict 10% improvement
            insights['predicted_score_next_session'] = min(current_score * 1.1, 100)
        else:
            insights['predicted_score_next_session'] = current_score
            
        # Determine trend
        if current_score >= 70:
            insights['productivity_trend'] = "Upward"
        elif current_score >= 50:
            insights['productivity_trend'] = "Stable"
        else:
            insights['productivity_trend'] = "Needs Improvement"
            
        return insights
    
    def analyze_multiple_sessions(self, history_csv: str) -> Dict:
        """Analyze historical data for trends"""
        if not os.path.exists(history_csv):
            return {"error": "History file not found"}
            
        df = pd.read_csv(history_csv)
        
        if df.empty:
            return {"error": "No historical data"}
            
        analysis = {
            'total_sessions': len(df),
            'date_range': {
                'start': df['date'].min(),
                'end': df['date'].max()
            },
            'average_score': df['overall_score'].mean(),
            'best_score': df['overall_score'].max(),
            'worst_score': df['overall_score'].min(),
            'trend_analysis': '',
            'daily_patterns': [],
            'weekly_insights': []
        }
        
        # Calculate trends
        if len(df) >= 2:
            scores = df['overall_score'].values
            trend = np.polyfit(range(len(scores)), scores, 1)[0]
            
            if trend > 1:
                analysis['trend_analysis'] = "Positive trend - Improving!"
            elif trend < -1:
                analysis['trend_analysis'] = "Negative trend - Needs attention"
            else:
                analysis['trend_analysis'] = "Stable performance"
                
        # Find best time of day
        df['hour'] = pd.to_datetime(df['start_time']).dt.hour
        best_hour = df.groupby('hour')['overall_score'].mean().idxmax()
        analysis['daily_patterns'].append(
            f"Most productive hour: {best_hour}:00 ({df.groupby('hour')['overall_score'].mean().max():.1f} avg score)"
        )
        
        # Day of week analysis
        df['day_of_week'] = pd.to_datetime(df['date']).dt.day_name()
        best_day = df.groupby('day_of_week')['overall_score'].mean().idxmax()
        analysis['weekly_insights'].append(
            f"Most productive day: {best_day}"
        )
        
        return analysis

# Test function
def test_ai_analyzer():
    print("🧠 Testing AI Productivity Analyzer")
    print("="*50)
    
    analyzer = ProductivityAnalyzer()
    
    # Find latest report
    import glob
    reports = glob.glob("enhanced_demo/*.json")
    
    if reports:
        latest_report = max(reports, key=os.path.getctime)
        print(f"Analyzing: {os.path.basename(latest_report)}")
        
        insights = analyzer.analyze_session(latest_report)
        
        print(f"\n📊 AI ANALYSIS RESULTS:")
        print(f"Session: {insights['session_id']}")
        print(f"Assessment: {insights['overall_assessment']}")
        
        if insights['strengths']:
            print("\n✅ STRENGTHS:")
            for strength in insights['strengths']:
                print(f"  • {strength}")
                
        if insights['weaknesses']:
            print("\n❌ WEAKNESSES:")
            for weakness in insights['weaknesses']:
                print(f"  • {weakness}")
                
        if insights['recommendations']:
            print("\n💡 AI RECOMMENDATIONS:")
            for rec in insights['recommendations']:
                print(f"  • {rec}")
                
        print(f"\n📈 Predicted next session score: {insights['predicted_score_next_session']:.1f}/100")
        
    else:
        print("No reports found for analysis")
        
    # Analyze history if available
    history_file = "enhanced_demo/enhanced_history.csv"
    if os.path.exists(history_file):
        print("\n" + "="*50)
        print("📅 HISTORICAL ANALYSIS")
        
        historical_insights = analyzer.analyze_multiple_sessions(history_file)
        
        if 'error' not in historical_insights:
            print(f"Total Sessions: {historical_insights['total_sessions']}")
            print(f"Date Range: {historical_insights['date_range']['start']} to {historical_insights['date_range']['end']}")
            print(f"Average Score: {historical_insights['average_score']:.1f}")
            print(f"Best Score: {historical_insights['best_score']:.1f}")
            print(f"Trend: {historical_insights['trend_analysis']}")
            
            for pattern in historical_insights['daily_patterns']:
                print(f"Pattern: {pattern}")
                
    return analyzer

if __name__ == "__main__":
    test_ai_analyzer()