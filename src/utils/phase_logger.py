"""
Phase Logger for tracking Agent execution phases
"""
import time
import logging
from enum import Enum
from typing import Optional
from contextlib import contextmanager

logger = logging.getLogger(__name__)


class Phase(str, Enum):
    USER_INPUT = "USER_INPUT"
    AGENT_START = "AGENT_START"
    RETRIEVAL = "RETRIEVAL"
    TOOL_EXECUTION = "TOOL_EXECUTION"
    LLM_CALL = "LLM_CALL"
    VISION_PROCESSING = "VISION_PROCESSING"
    CONTEXT_ENRICHMENT = "CONTEXT_ENRICHMENT"
    STREAMING = "STREAMING"
    AGENT_RESPONSE = "AGENT_RESPONSE"
    DOCUMENT_PROCESSING = "DOCUMENT_PROCESSING"


class PhaseLogger:
    def __init__(self, name: str = "PhaseLogger"):
        self.name = name
        self.logger = logging.getLogger(name)
        
        if not self.logger.handlers:
            self.logger.setLevel(logging.INFO)
            handler = logging.StreamHandler()
            handler.setLevel(logging.INFO)
            formatter = logging.Formatter("[%(asctime)s] [%(phase)s] %(message)s | Duration: %(duration)s")
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
    
    @contextmanager
    def phase(self, phase: Phase, message: str, **kwargs):
        start_time = time.time()
        self._log(phase, message, 0.0, **kwargs)
        try:
            yield
        finally:
            duration = time.time() - start_time
            self._log(phase, message, duration, **kwargs, end=True)
    
    def log_phase(self, phase: Phase, message: str, duration: Optional[float] = None, **kwargs):
        self._log(phase, message, duration, **kwargs)
    
    def _log(self, phase: Phase, message: str, duration: Optional[float], **kwargs):
        duration_str = f"{duration:.2f}s" if duration is not None else "N/A"
        
        record = self.logger.makeRecord(
            self.logger.name,
            logging.INFO,
            None,
            None,
            message,
            (),
            None
        )
        record.phase = phase.value
        record.duration = duration_str
        
        for key, value in kwargs.items():
            setattr(record, key, value)
        
        self.logger.handle(record)


phase_logger = PhaseLogger("PhaseLogger")