"""File storage and cleanup management service."""

import asyncio
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any
import tempfile
import hashlib

from ..models.config import StorageConfig
from ..models.messages import VoicemailMessage, AudioAttachment
from ..utils.logging import LoggerMixin


class FileManager(LoggerMixin):
    """Service for managing file storage and cleanup operations."""
    
    def __init__(self, config: StorageConfig):
        self.config = config
        self._ensure_directories()
    
    def _ensure_directories(self) -> None:
        """Ensure required directories exist."""
        try:
            # Create main storage directory
            self.config.path.mkdir(parents=True, exist_ok=True)
            
            # Create subdirectories
            (self.config.path / "temp").mkdir(exist_ok=True)
            (self.config.path / "processed").mkdir(exist_ok=True)
            (self.config.path / "failed").mkdir(exist_ok=True)
            
            self.log_info(
                f"Storage directories initialized",
                storage_path=str(self.config.path)
            )
            
        except Exception as e:
            self.log_error(f"Failed to create storage directories: {e}")
            raise
    
    async def store_voicemail_files(self, voicemail_msg: VoicemailMessage) -> Dict[str, Path]:
        """
        Store voicemail audio files temporarily for processing.
        
        Args:
            voicemail_msg: Voicemail message with audio attachments
            
        Returns:
            Dictionary mapping attachment filenames to stored file paths
        """
        stored_files = {}
        correlation_id = voicemail_msg.correlation_id
        
        try:
            # Create correlation-specific directory
            work_dir = self.config.path / "temp" / correlation_id
            work_dir.mkdir(parents=True, exist_ok=True)
            
            self.log_info(
                f"Created work directory for voicemail processing",
                work_dir=str(work_dir),
                audio_files_count=len(voicemail_msg.audio_attachments)
            )
            
            # Store each audio attachment
            for i, attachment in enumerate(voicemail_msg.audio_attachments):
                file_path = await self._store_audio_file(work_dir, attachment, i)
                if file_path:
                    stored_files[attachment.filename] = file_path
            
            self.log_info(
                f"Stored {len(stored_files)} audio files",
                stored_count=len(stored_files),
                total_count=len(voicemail_msg.audio_attachments)
            )
            
            return stored_files
            
        except Exception as e:
            self.log_error(
                f"Failed to store voicemail files: {e}",
                correlation_id=correlation_id
            )
            # Clean up any partially stored files
            await self._cleanup_correlation_files(correlation_id)
            return {}
    
    async def _store_audio_file(
        self, 
        work_dir: Path, 
        attachment: AudioAttachment, 
        index: int
    ) -> Optional[Path]:
        """
        Store a single audio file.
        
        Args:
            work_dir: Working directory for this correlation ID
            attachment: Audio attachment to store
            index: Index of the attachment
            
        Returns:
            Path to stored file or None if storage failed
        """
        try:
            # Generate safe filename
            safe_filename = self._generate_safe_filename(attachment.filename, index)
            file_path = work_dir / safe_filename
            
            # Write audio data to file
            with open(file_path, 'wb') as f:
                f.write(attachment.data)
            
            # Verify file was written correctly
            if file_path.stat().st_size != len(attachment.data):
                raise ValueError("File size mismatch after writing")
            
            self.log_debug(
                f"Stored audio file",
                filename=attachment.filename,
                stored_path=str(file_path),
                size_bytes=len(attachment.data)
            )
            
            return file_path
            
        except Exception as e:
            self.log_error(
                f"Failed to store audio file: {e}",
                filename=attachment.filename,
                size_bytes=len(attachment.data)
            )
            return None
    
    def _generate_safe_filename(self, original_filename: str, index: int) -> str:
        """
        Generate a safe filename for storage.
        
        Args:
            original_filename: Original attachment filename
            index: Index of the attachment
            
        Returns:
            Safe filename for filesystem storage
        """
        # Get file extension
        file_path = Path(original_filename)
        extension = file_path.suffix.lower()
        
        # Create hash of original filename for uniqueness
        filename_hash = hashlib.md5(original_filename.encode()).hexdigest()[:8]
        
        # Generate safe filename
        safe_filename = f"audio_{index:02d}_{filename_hash}{extension}"
        
        return safe_filename
    
    async def cleanup_correlation_files(self, correlation_id: str, success: bool = True) -> bool:
        """
        Clean up files for a specific correlation ID.
        
        Args:
            correlation_id: Correlation ID to clean up
            success: Whether processing was successful
            
        Returns:
            True if cleanup was successful, False otherwise
        """
        try:
            return await self._cleanup_correlation_files(correlation_id, success)
        except Exception as e:
            self.log_error(
                f"Failed to cleanup correlation files: {e}",
                correlation_id=correlation_id
            )
            return False
    
    async def _cleanup_correlation_files(self, correlation_id: str, success: bool = True) -> bool:
        """
        Internal method to clean up correlation files.
        
        Args:
            correlation_id: Correlation ID to clean up
            success: Whether processing was successful
            
        Returns:
            True if cleanup was successful, False otherwise
        """
        work_dir = self.config.path / "temp" / correlation_id
        
        if not work_dir.exists():
            self.log_debug(f"Work directory does not exist, nothing to cleanup", correlation_id=correlation_id)
            return True
        
        try:
            # Move files to appropriate directory based on success
            if success:
                target_dir = self.config.path / "processed" / correlation_id
            else:
                target_dir = self.config.path / "failed" / correlation_id
            
            # Move the entire work directory
            if target_dir.exists():
                shutil.rmtree(target_dir)
            
            shutil.move(str(work_dir), str(target_dir))
            
            self.log_info(
                f"Moved correlation files to {'processed' if success else 'failed'} directory",
                correlation_id=correlation_id,
                target_dir=str(target_dir)
            )
            
            # Schedule cleanup of old files
            asyncio.create_task(self._schedule_old_file_cleanup())
            
            return True
            
        except Exception as e:
            self.log_error(
                f"Failed to move correlation files: {e}",
                correlation_id=correlation_id
            )
            
            # Fallback: just delete the work directory
            try:
                shutil.rmtree(work_dir)
                self.log_info(f"Deleted work directory as fallback", correlation_id=correlation_id)
                return True
            except Exception as cleanup_error:
                self.log_error(
                    f"Failed to delete work directory: {cleanup_error}",
                    correlation_id=correlation_id
                )
                return False
    
    async def _schedule_old_file_cleanup(self) -> None:
        """Schedule cleanup of old processed/failed files."""
        try:
            cutoff_time = datetime.utcnow() - timedelta(hours=self.config.cleanup_after_hours)
            
            # Clean up old processed files
            await self._cleanup_old_directories(
                self.config.path / "processed",
                cutoff_time
            )
            
            # Clean up old failed files
            await self._cleanup_old_directories(
                self.config.path / "failed",
                cutoff_time
            )
            
        except Exception as e:
            self.log_error(f"Error in scheduled file cleanup: {e}")
    
    async def _cleanup_old_directories(self, base_dir: Path, cutoff_time: datetime) -> None:
        """
        Clean up old directories based on modification time.
        
        Args:
            base_dir: Base directory to clean
            cutoff_time: Delete directories older than this time
        """
        if not base_dir.exists():
            return
        
        try:
            deleted_count = 0
            
            for item in base_dir.iterdir():
                if item.is_dir():
                    # Check modification time
                    mod_time = datetime.fromtimestamp(item.stat().st_mtime)
                    
                    if mod_time < cutoff_time:
                        shutil.rmtree(item)
                        deleted_count += 1
                        
                        self.log_debug(
                            f"Deleted old directory",
                            directory=str(item),
                            mod_time=mod_time.isoformat()
                        )
            
            if deleted_count > 0:
                self.log_info(
                    f"Cleaned up old directories",
                    base_dir=str(base_dir),
                    deleted_count=deleted_count,
                    cutoff_hours=self.config.cleanup_after_hours
                )
                
        except Exception as e:
            self.log_error(
                f"Error cleaning up old directories: {e}",
                base_dir=str(base_dir)
            )
    
    async def get_storage_stats(self) -> Dict[str, Any]:
        """
        Get storage statistics.
        
        Returns:
            Dictionary with storage statistics
        """
        try:
            stats = {
                "storage_path": str(self.config.path),
                "temp_files": 0,
                "processed_files": 0,
                "failed_files": 0,
                "total_size_bytes": 0,
            }
            
            # Count files in each directory
            for subdir, key in [
                ("temp", "temp_files"),
                ("processed", "processed_files"),
                ("failed", "failed_files")
            ]:
                dir_path = self.config.path / subdir
                if dir_path.exists():
                    count = sum(1 for _ in dir_path.rglob("*") if _.is_file())
                    stats[key] = count
            
            # Calculate total size
            if self.config.path.exists():
                total_size = sum(
                    f.stat().st_size 
                    for f in self.config.path.rglob("*") 
                    if f.is_file()
                )
                stats["total_size_bytes"] = total_size
                stats["total_size_mb"] = total_size / (1024 * 1024)
            
            # Get disk space
            import shutil
            total, used, free = shutil.disk_usage(self.config.path)
            stats["disk_total_gb"] = total / (1024**3)
            stats["disk_used_gb"] = used / (1024**3)
            stats["disk_free_gb"] = free / (1024**3)
            
            return stats
            
        except Exception as e:
            self.log_error(f"Failed to get storage stats: {e}")
            return {"error": str(e)}