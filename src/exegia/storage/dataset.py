"""
Supabase Storage Service for Dataset Management

Handles dataset operations with Supabase Storage:
- List available datasets by category
- Download datasets (zip files)
- Upload datasets
- Extract and save to local filesystem
"""

import asyncio
import io
import logging
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

from supabase import Client

logger = logging.getLogger(__name__)


class DatasetStorageService:
    """
    Service for managing biblical text datasets in Supabase Storage.

    Handles operations for bibles, books, lexicons, and dictionaries stored
    as zip files in Supabase storage buckets.
    """

    # Storage bucket names by category
    BUCKETS = {
        "bibles": "bibles",
        "books": "books",
        "lexicons": "lexicons",
        "dictionaries": "dictionaries",
    }

    def __init__(self, supabase_client: Client, local_base_path: Optional[Path] = None):
        """
        Initialize the dataset storage service.

        Args:
            supabase_client: Initialized Supabase client
            local_base_path: Base directory for local dataset storage
        """
        self.supabase = supabase_client
        self.local_base_path = local_base_path or Path.home() / ".exegia" / "datasets"

        # Ensure local base path exists
        self.local_base_path.mkdir(parents=True, exist_ok=True)

        logger.info(f"Dataset storage service initialized with local path: {self.local_base_path}")

    async def list_datasets(
        self, category: Optional[str] = None, search: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        List available datasets from Supabase Storage.

        Args:
            category: Filter by category (bibles, books, lexicons, dictionaries)
            search: Optional search term to filter dataset names

        Returns:
            List of dataset metadata dictionaries
        """
        datasets = []

        # Determine which buckets to query
        if category:
            if category not in self.BUCKETS:
                raise ValueError(
                    f"Invalid category: {category}. Must be one of {list(self.BUCKETS.keys())}"
                )
            buckets_to_query = {category: self.BUCKETS[category]}
        else:
            buckets_to_query = self.BUCKETS

        # Query each bucket
        for category_name, bucket_name in buckets_to_query.items():
            try:
                # List files in bucket
                files = self.supabase.storage.from_(bucket_name).list()

                for file_info in files:
                    file_name = file_info.get("name", "")

                    # Skip if not a zip file
                    if not file_name.endswith(".zip"):
                        continue

                    # Apply search filter if provided
                    if search and search.lower() not in file_name.lower():
                        continue

                    # Extract dataset ID (filename without .zip)
                    dataset_id = file_name.replace(".zip", "")

                    datasets.append(
                        {
                            "id": dataset_id,
                            "name": file_name,
                            "category": category_name,
                            "bucket": bucket_name,
                            "size": file_info.get("metadata", {}).get("size", 0),
                            "created_at": file_info.get("created_at"),
                            "updated_at": file_info.get("updated_at"),
                            "metadata": file_info.get("metadata", {}),
                        }
                    )

            except Exception as e:
                logger.error(f"Error listing datasets from bucket '{bucket_name}': {e}")
                continue

        return datasets

    async def download_dataset(
        self,
        dataset_id: str,
        category: str,
        extract_to: Optional[Path] = None,
        extract: bool = True,
    ) -> Path:
        """
        Download a dataset from Supabase Storage.

        Args:
            dataset_id: Dataset identifier (e.g., "KJV", "ESV")
            category: Dataset category (bibles, books, lexicons, dictionaries)
            extract_to: Custom extraction path (defaults to local_base_path/dataset_id)
            extract: Whether to extract the zip file after download

        Returns:
            Path to the downloaded/extracted dataset

        Raises:
            ValueError: If category is invalid
            FileNotFoundError: If dataset doesn't exist
            IOError: If download or extraction fails
        """
        if category not in self.BUCKETS:
            raise ValueError(f"Invalid category: {category}")

        bucket_name = self.BUCKETS[category]
        file_name = f"{dataset_id}.zip"

        # Determine extraction path
        if extract_to:
            target_path = extract_to
        else:
            target_path = self.local_base_path / category / dataset_id

        target_path.mkdir(parents=True, exist_ok=True)

        try:
            logger.info(f"Downloading dataset '{dataset_id}' from bucket '{bucket_name}'")

            # Download file from Supabase Storage
            file_data = self.supabase.storage.from_(bucket_name).download(file_name)

            if not file_data:
                raise FileNotFoundError(
                    f"Dataset '{dataset_id}' not found in bucket '{bucket_name}'"
                )

            if extract:
                # Extract zip file to target path
                logger.info(f"Extracting dataset to {target_path}")

                with zipfile.ZipFile(io.BytesIO(file_data), "r") as zip_ref:
                    zip_ref.extractall(target_path)

                logger.info(f"Successfully extracted dataset '{dataset_id}' to {target_path}")
                return target_path
            else:
                # Save zip file without extracting
                zip_path = target_path / file_name
                zip_path.write_bytes(file_data)

                logger.info(f"Downloaded dataset '{dataset_id}' to {zip_path}")
                return zip_path

        except Exception as e:
            logger.error(f"Failed to download dataset '{dataset_id}': {e}")
            raise IOError(f"Download failed: {e}")

    async def upload_dataset(
        self, local_path: Path, dataset_id: str, category: str, compress: bool = True
    ) -> Dict[str, Any]:
        """
        Upload a dataset to Supabase Storage.

        Args:
            local_path: Path to local dataset (directory or zip file)
            dataset_id: Dataset identifier
            category: Dataset category
            compress: Whether to compress directory to zip before upload

        Returns:
            Upload result metadata

        Raises:
            ValueError: If category is invalid
            FileNotFoundError: If local path doesn't exist
            IOError: If upload fails
        """
        if category not in self.BUCKETS:
            raise ValueError(f"Invalid category: {category}")

        if not local_path.exists():
            raise FileNotFoundError(f"Local path does not exist: {local_path}")

        bucket_name = self.BUCKETS[category]
        file_name = f"{dataset_id}.zip"

        try:
            # If it's a directory, compress it first
            if local_path.is_dir() and compress:
                logger.info(f"Compressing dataset '{dataset_id}' from {local_path}")

                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
                    for file_path in local_path.rglob("*"):
                        if file_path.is_file():
                            arcname = file_path.relative_to(local_path)
                            zip_file.write(file_path, arcname)

                file_data = zip_buffer.getvalue()
            elif local_path.is_file() and local_path.suffix == ".zip":
                # Already a zip file
                file_data = local_path.read_bytes()
            else:
                raise ValueError(f"Invalid local path: must be directory or .zip file")

            logger.info(f"Uploading dataset '{dataset_id}' to bucket '{bucket_name}'")

            # Upload to Supabase Storage
            result = self.supabase.storage.from_(bucket_name).upload(
                path=file_name,
                file=file_data,
                file_options={"content-type": "application/zip"},
            )

            logger.info(f"Successfully uploaded dataset '{dataset_id}'")

            return {
                "dataset_id": dataset_id,
                "category": category,
                "file_name": file_name,
                "size": len(file_data),
                "uploaded": True,
            }

        except Exception as e:
            logger.error(f"Failed to upload dataset '{dataset_id}': {e}")
            raise IOError(f"Upload failed: {e}")

    async def delete_dataset(self, dataset_id: str, category: str) -> bool:
        """
        Delete a dataset from Supabase Storage.

        Args:
            dataset_id: Dataset identifier
            category: Dataset category

        Returns:
            True if deleted successfully

        Raises:
            ValueError: If category is invalid
        """
        if category not in self.BUCKETS:
            raise ValueError(f"Invalid category: {category}")

        bucket_name = self.BUCKETS[category]
        file_name = f"{dataset_id}.zip"

        try:
            logger.info(f"Deleting dataset '{dataset_id}' from bucket '{bucket_name}'")

            self.supabase.storage.from_(bucket_name).remove([file_name])

            logger.info(f"Successfully deleted dataset '{dataset_id}'")
            return True

        except Exception as e:
            logger.error(f"Failed to delete dataset '{dataset_id}': {e}")
            return False

    async def get_dataset_info(self, dataset_id: str, category: str) -> Optional[Dict[str, Any]]:
        """
        Get metadata for a specific dataset.

        Args:
            dataset_id: Dataset identifier
            category: Dataset category

        Returns:
            Dataset metadata or None if not found
        """
        if category not in self.BUCKETS:
            raise ValueError(f"Invalid category: {category}")

        bucket_name = self.BUCKETS[category]
        file_name = f"{dataset_id}.zip"

        try:
            # List files and find the specific one
            files = self.supabase.storage.from_(bucket_name).list()

            for file_info in files:
                if file_info.get("name") == file_name:
                    return {
                        "id": dataset_id,
                        "name": file_name,
                        "category": category,
                        "bucket": bucket_name,
                        "size": file_info.get("metadata", {}).get("size", 0),
                        "created_at": file_info.get("created_at"),
                        "updated_at": file_info.get("updated_at"),
                        "metadata": file_info.get("metadata", {}),
                    }

            return None

        except Exception as e:
            logger.error(f"Error getting dataset info for '{dataset_id}': {e}")
            return None

    async def get_public_url(self, dataset_id: str, category: str) -> Optional[str]:
        """
        Get public download URL for a dataset.

        Args:
            dataset_id: Dataset identifier
            category: Dataset category

        Returns:
            Public URL or None if not available
        """
        if category not in self.BUCKETS:
            raise ValueError(f"Invalid category: {category}")

        bucket_name = self.BUCKETS[category]
        file_name = f"{dataset_id}.zip"

        try:
            # Get public URL from Supabase Storage
            result = self.supabase.storage.from_(bucket_name).get_public_url(file_name)
            return result

        except Exception as e:
            logger.error(f"Error getting public URL for '{dataset_id}': {e}")
            return None

    def list_local_datasets(self) -> List[Dict[str, Any]]:
        """
        List datasets stored locally.

        Returns:
            List of local dataset information
        """
        local_datasets = []

        if not self.local_base_path.exists():
            return local_datasets

        for category_dir in self.local_base_path.iterdir():
            if category_dir.is_dir() and category_dir.name in self.BUCKETS:
                for dataset_dir in category_dir.iterdir():
                    if dataset_dir.is_dir():
                        # Check for .tf files to confirm it's a valid dataset
                        tf_files = list(dataset_dir.glob("**/*.tf"))

                        if tf_files:
                            local_datasets.append(
                                {
                                    "id": dataset_dir.name,
                                    "category": category_dir.name,
                                    "path": str(dataset_dir),
                                    "file_count": len(tf_files),
                                    "size": sum(
                                        f.stat().st_size
                                        for f in dataset_dir.rglob("*")
                                        if f.is_file()
                                    ),
                                }
                            )

        return local_datasets

    async def sync_dataset(
        self, dataset_id: str, category: str, direction: str = "download"
    ) -> bool:
        """
        Sync a dataset between local storage and Supabase.

        Args:
            dataset_id: Dataset identifier
            category: Dataset category
            direction: "download" or "upload"

        Returns:
            True if sync was successful
        """
        try:
            if direction == "download":
                await self.download_dataset(dataset_id, category)
                return True
            elif direction == "upload":
                local_path = self.local_base_path / category / dataset_id
                await self.upload_dataset(local_path, dataset_id, category)
                return True
            else:
                raise ValueError(f"Invalid sync direction: {direction}")

        except Exception as e:
            logger.error(f"Failed to sync dataset '{dataset_id}': {e}")
            return False
