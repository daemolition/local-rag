# Local Document RAG - A privacy-focused, local RAG system
# Copyright (C) 2026 Christopher Abanilla
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.

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