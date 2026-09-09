from unittest.mock import AsyncMock

import pytest
from pipecat.frames.frames import MetricsFrame
from pipecat.metrics.metrics import STTUsage, STTUsageMetricsData
from pipecat.processors.frame_processor import FrameDirection

from api.services.pipecat.pipeline_metrics_aggregator import PipelineMetricsAggregator


@pytest.mark.asyncio
async def test_aggregates_stt_audio_seconds():
    aggregator = PipelineMetricsAggregator()
    aggregator.push_frame = AsyncMock()
    frame = MetricsFrame(
        data=[
            STTUsageMetricsData(
                processor="GoogleSTT",
                model="latest_short",
                value=STTUsage(audio_seconds=2.5),
            )
        ]
    )
    await aggregator.process_frame(frame, FrameDirection.DOWNSTREAM)
    await aggregator.process_frame(frame, FrameDirection.DOWNSTREAM)
    assert aggregator.get_stt_usage_metrics()["GoogleSTT|||latest_short"] == 5.0
