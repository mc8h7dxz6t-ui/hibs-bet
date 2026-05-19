"""M5/Apple Silicon and Free API Optimizations for HibsBetting"""

import os
import platform
from typing import Dict, Optional

class M5Optimizer:
    """Optimizations for macOS Apple Silicon (M5, M4, M3, M2, M1)"""
    
    @staticmethod
    def is_apple_silicon() -> bool:
        """Check if running on Apple Silicon"""
        return platform.machine() == 'arm64'
    
    @staticmethod
    def get_optimal_settings() -> Dict[str, any]:
        """Get optimized settings for Apple Silicon"""
        if not M5Optimizer.is_apple_silicon():
            return {}
        
        return {
            # Use native arm64 numpy/pandas for better performance
            'use_native_blas': True,
            # Reduce thread count for battery efficiency
            'numpy_threads': os.cpu_count() or 4,
            'scikit_learn_threads': (os.cpu_count() or 4) - 1,
            # Memory-efficient settings
            'cache_size_mb': 256,
            'batch_size': 32,
            # Socket optimization for M-series
            'use_quic': True,
            'connection_pool_size': 10,
        }
    
    @staticmethod
    def configure_environment():
        """Configure environment for optimal M5/Apple Silicon performance"""
        if M5Optimizer.is_apple_silicon():
            # Prefer native arm64 libraries
            os.environ['OPENBLAS_NUM_THREADS'] = str((os.cpu_count() or 4) - 1)
            os.environ['MKL_NUM_THREADS'] = str((os.cpu_count() or 4) - 1)
            os.environ['VECLIB_MAXIMUM_THREADS'] = str((os.cpu_count() or 4) - 1)


class FreeAPIOptimizer:
    """Optimizations for staying within free API tier limits"""
    
    # Free tier limits per service per day
    DAILY_LIMITS = {
        'football_data_org': 100,
        'api_sports': 150,
        'sportsmonk': 150,
        'odds_api': 500,  # Note: monthly, not daily
        'stats_api': 150,
    }
    
    # Recommended cache TTLs to reduce API calls
    RECOMMENDED_CACHE_TTL_HOURS = {
        'fixtures': 12,  # Fixtures rarely change
        'team_stats': 4,  # Update every 4 hours
        'player_stats': 6,  # Update every 6 hours
        'odds': 1,  # Odds change frequently
        'predictions': 12,  # Predictions valid for ~12 hours
    }
    
    @staticmethod
    def get_daily_budget(service: str) -> Optional[int]:
        """Get daily API call budget for a service"""
        return FreeAPIOptimizer.DAILY_LIMITS.get(service)
    
    @staticmethod
    def get_recommended_cache_ttl(data_type: str) -> Optional[int]:
        """Get recommended cache TTL in hours for data type"""
        return FreeAPIOptimizer.RECOMMENDED_CACHE_TTL_HOURS.get(data_type)
    
    @staticmethod
    def get_priority_leagues() -> list:
        """Get recommended league focus to minimize API calls"""
        return [
            'SCOTLAND',  # Hibernian's primary league
            'EPL',  # High interest
            'EUROPA_LEAGUE',  # Hibernian's European competition
        ]
    
    @staticmethod
    def get_smart_prefetch_strategy() -> Dict[str, any]:
        """Get smart prefetching strategy to stay within free tier"""
        return {
            'update_frequency': 'every 4 hours',
            'focus_leagues': FreeAPIOptimizer.get_priority_leagues(),
            'prefetch_fixtures': 14,  # Days ahead to prefetch
            'cache_all_results': True,
            'batch_api_calls': True,  # Combine calls where possible
            'skip_historical': True,  # Don't fetch full historical data
        }


def setup_optimizations():
    """Setup all M5 and free API optimizations"""
    M5Optimizer.configure_environment()
    
    # Log platform info
    platform_info = {
        'system': platform.system(),
        'machine': platform.machine(),
        'is_apple_silicon': M5Optimizer.is_apple_silicon(),
        'cpu_count': os.cpu_count(),
    }
    
    return {
        'platform': platform_info,
        'm5_settings': M5Optimizer.get_optimal_settings(),
        'api_strategy': FreeAPIOptimizer.get_smart_prefetch_strategy(),
    }


if __name__ == '__main__':
    config = setup_optimizations()
    print("HibsBetting Optimization Configuration:")
    print(f"Platform: {config['platform']}")
    print(f"M5 Settings: {config['m5_settings']}")
    print(f"API Strategy: {config['api_strategy']}")
