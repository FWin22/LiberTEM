import os

import numpy as np
import pytest

from libertem.executor.dask import (
    CommonDaskMixin, DaskJobExecutor
)
from libertem.common import Shape, Slice
from libertem.executor.base import AsyncAdapter
from libertem.job.sum import SumFramesJob
from libertem.job.raw import PickFrameJob
from utils import MemoryDataSet, _mk_random


@pytest.fixture
async def aexecutor():
    sync_executor = DaskJobExecutor.make_local()
    executor = AsyncAdapter(wrapped=sync_executor)
    yield executor
    await executor.close()


def test_task_affinity_1():
    cdm = CommonDaskMixin()
    workers = [
        {'host': '127.0.0.1', 'name': 'w1'},
        {'host': '127.0.0.1', 'name': 'w2'},
        {'host': '127.0.0.1', 'name': 'w3'},
        {'host': '127.0.0.1', 'name': 'w4'},

        {'host': '127.0.0.2', 'name': 'w5'},
        {'host': '127.0.0.2', 'name': 'w6'},
        {'host': '127.0.0.2', 'name': 'w7'},
        {'host': '127.0.0.2', 'name': 'w8'},
    ]

    assert cdm._task_idx_to_workers(workers, 0) == ['w1', 'w2', 'w3', 'w4']
    assert cdm._task_idx_to_workers(workers, 1) == ['w5', 'w6', 'w7', 'w8']
    assert cdm._task_idx_to_workers(workers, 2) == ['w1', 'w2', 'w3', 'w4']
    assert cdm._task_idx_to_workers(workers, 3) == ['w5', 'w6', 'w7', 'w8']


@pytest.mark.asyncio
async def test_run_job(aexecutor):
    data = _mk_random(size=(16, 16, 16, 16), dtype='<u2')
    dataset = MemoryDataSet(data=data, tileshape=(1, 1, 16, 16), partition_shape=(1, 8, 16, 16))
    expected = data.sum(axis=(0, 1))

    job = SumFramesJob(dataset=dataset)
    out = job.get_result_buffer()

    async for tiles in aexecutor.run_job(job):
        for tile in tiles:
            tile.reduce_into_result(out)

    assert out.shape == (16, 16)
    assert np.allclose(out, expected)


@pytest.mark.skipif(os.name == 'nt',
                    reason="doesnt run on windows")
@pytest.mark.asyncio
async def test_fd_limit(aexecutor):
    import resource
    # set soft limit, throws errors but allows to raise it
    # again afterwards:
    oldlimit = resource.getrlimit(resource.RLIMIT_NOFILE)
    resource.setrlimit(resource.RLIMIT_NOFILE, (100, oldlimit[1]))

    try:
        data = _mk_random(size=(1, 1, 16, 16), dtype='<u2')
        dataset = MemoryDataSet(data=data, tileshape=(1, 1, 16, 16), partition_shape=(1, 1, 16, 16))

        slice_ = Slice(origin=(0, 0, 0, 0), shape=Shape((1, 1, 16, 16), sig_dims=2))
        job = PickFrameJob(dataset=dataset, slice_=slice_)

        for i in range(32):
            print(i)
            async for tiles in aexecutor.run_job(job):
                pass
    finally:
        resource.setrlimit(resource.RLIMIT_NOFILE, oldlimit)
