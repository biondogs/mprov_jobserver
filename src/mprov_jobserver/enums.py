from enum import IntEnum


class JobStatus(IntEnum):
    """Job status codes for mProv job server.

    These status codes are used to track the lifecycle of jobs
    in the mProv Control Center (mPCC).
    """

    PENDING = 1
    """Job is queued and waiting to be picked up by a job server."""

    RUNNING = 2
    """Job is currently being processed by a job server."""

    FAILED = 3
    """Job failed to complete successfully."""

    SUCCESS = 4
    """Job completed successfully."""
