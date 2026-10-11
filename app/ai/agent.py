"""AI layer — Pipecat voice pipeline, all Sarvam, driven by Pipecat Flows.

Saaras STT → Sarvam LLM (node-by-node functions) → Bulbul TTS
The conversation map lives in app/ai/flow/nodes.py.
"""

from loguru import logger
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.flows import FlowManager
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.runner.types import RunnerArguments
from pipecat.runner.utils import create_transport
from pipecat.services.sarvam.llm import SarvamLLMService
from pipecat.services.sarvam.stt import SarvamSTTService
from pipecat.services.sarvam.tts import SarvamTTSService
from pipecat.services.tts_service import TextAggregationMode
from pipecat.transports.base_transport import BaseTransport, TransportParams
from pipecat.workers.runner import WorkerRunner

from app.ai.flow import nodes
from app.ai.text_normalizer import SpeechNormalizer
from app.core.settings import settings
from app.db.database import init_db


def build_services():
    if not settings.sarvam_api_key:
        raise RuntimeError("SARVAM_API_KEY is not set. Add it to your .env file.")

    stt = SarvamSTTService(
        api_key=settings.sarvam_api_key,
        settings=SarvamSTTService.Settings(model=settings.sarvam_stt_model),
    )

    # No system prompt or tools here: each Flows node supplies its own.
    llm = SarvamLLMService(
        api_key=settings.sarvam_api_key,
        settings=SarvamLLMService.Settings(
            model=settings.sarvam_llm_model,
            reasoning_effort=settings.sarvam_reasoning_effort or None,
        ),
    )

    tts = SarvamTTSService(
        api_key=settings.sarvam_api_key,
        settings=SarvamTTSService.Settings(
            model=settings.sarvam_tts_model,
            voice=settings.sarvam_voice,
            language=settings.language,
        ),
        # The normalizer needs whole sentences (so "2026-10-12T10:00" isn't split),
        # which is what SENTENCE aggregation gives it.
        text_aggregation_mode=TextAggregationMode.SENTENCE,
        text_filters=[SpeechNormalizer(settings.language)],
    )
    return stt, llm, tts


async def run_bot(transport: BaseTransport, runner_args: RunnerArguments):
    stt, llm, tts = build_services()

    context = LLMContext()
    aggregators = LLMContextAggregatorPair(
        context, user_params=LLMUserAggregatorParams(vad_analyzer=SileroVADAnalyzer())
    )

    pipeline = Pipeline(
        [transport.input(), stt, aggregators.user(), llm, tts, transport.output(), aggregators.assistant()]
    )

    worker = PipelineWorker(pipeline, params=PipelineParams(enable_metrics=True, enable_usage_metrics=True))
    runner = WorkerRunner(handle_sigint=runner_args.handle_sigint)
    await runner.add_workers(worker)

    flow_manager = FlowManager(
        llm=llm,
        context_aggregator=aggregators,
        worker=worker,
        transport=transport,
        global_functions=nodes.global_functions(),
    )

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        logger.info("Caller connected")
        await flow_manager.initialize(nodes.greet_identify())

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info("Caller disconnected")
        await runner.cancel()

    await runner.run()


async def bot(runner_args: RunnerArguments):
    """Pipecat runner entry point."""
    init_db()
    transport = await create_transport(
        runner_args,
        {"webrtc": lambda: TransportParams(audio_in_enabled=True, audio_out_enabled=True)},
    )
    await run_bot(transport, runner_args)