"""Base plugin class - all plugins must inherit from this"""

from abc import ABC, abstractmethod
from enum import Enum


class ProcessingMode(str, Enum):
    """Processing mode for plugins"""
    SYNC = "sync"      # Synchronous processing
    ASYNC = "async"    # Asynchronous processing


class BasePlugin(ABC):
    """Base class that all plugins must inherit from"""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique plugin identifier, e.g., 'image-compress'"""
        pass

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Display name, e.g., '图片压缩'"""
        pass

    @property
    @abstractmethod
    def category(self) -> str:
        """Category: image, video, document, ai, storage"""
        pass

    @property
    def processing_mode(self) -> ProcessingMode:
        """Processing mode: defaults to synchronous"""
        return ProcessingMode.SYNC

    @property
    def enabled(self) -> bool:
        """Whether the plugin is enabled"""
        return True

    @abstractmethod
    async def process(self, input_data: dict) -> dict:
        """Processing logic (NO database writes)

        Args:
            input_data: Input data dictionary

        Returns:
            Processing result dictionary with success, data, error fields
        """
        pass

    @abstractmethod
    def validate_input(self, input_data: dict) -> tuple[bool, str | None]:
        """Input validation

        Returns:
            (is_valid, error_message)
        """
        pass

    async def health_check(self) -> bool:
        """Health check (returns True by default)"""
        return True
