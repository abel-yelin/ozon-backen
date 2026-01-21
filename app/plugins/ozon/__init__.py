"""Ozon download plugin for batch image downloading from Ozon marketplace"""

from .download import OzonDownloadPlugin
from .image_push import OzonImagePushPlugin

__all__ = ["OzonDownloadPlugin", "OzonImagePushPlugin"]
