"""
V2 Alarm Base Classes

Tum alarm tipleri icin temel siniflar ve arayuzler.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from datetime import datetime


@dataclass
class AlarmResult:
    """Alarm tespit sonucu"""
    alarm_type: str
    score: int
    is_triggered: bool
    side: str
    odds_from: float
    odds_to: float
    money_diff: float
    timestamp: datetime
    details: Dict[str, Any]
    reason: Optional[str] = None
    sharp_score: float = 0.0
    new_bet_amount: float = 0.0
    drop_pct: float = 0.0


class AlarmDetectorV2(ABC):
    """
    V2 Alarm Detector Base Class
    
    Tum alarm tipleri bu siniftan turetilir.
    """
    
    @property
    @abstractmethod
    def alarm_type(self) -> str:
        """Alarm tipi (sharp, dropping, momentum, etc.)"""
        pass
    
    @abstractmethod
    def detect(self, history: List[Dict], market: str, match_id: str) -> List[AlarmResult]:
        """
        Ana tespit fonksiyonu.
        
        Args:
            history: Mac icin odds/volume gecmisi
            market: Market tipi (moneyway_1x2, dropping_ou25, etc.)
            match_id: Mac ID
            
        Returns:
            Tespit edilen alarmlar listesi
        """
        pass
    
    @abstractmethod
    def compute_score(self, **kwargs) -> int:
        """
        Alarm skoru hesapla (0-100)
        """
        pass


class AlarmEngineV2:
    """
    V2 Alarm Engine
    
    Tum alarm detector'leri yonetir ve koordine eder.
    """
    
    def __init__(self):
        self.detectors: Dict[str, AlarmDetectorV2] = {}
    
    def register_detector(self, detector: AlarmDetectorV2):
        """Yeni detector kaydet"""
        self.detectors[detector.alarm_type] = detector
    
    def detect_all(self, history: List[Dict], market: str, match_id: str) -> List[AlarmResult]:
        """Tum kayitli detector'lerle tespit yap"""
        results = []
        for detector in self.detectors.values():
            try:
                alarms = detector.detect(history, market, match_id)
                results.extend(alarms)
            except Exception as e:
                print(f"[AlarmEngineV2] {detector.alarm_type} error: {e}")
        return results
