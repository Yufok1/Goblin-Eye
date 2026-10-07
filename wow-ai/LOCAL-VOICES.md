# Optional private voices

Desktop speech remains the default. An ignored bridge/neural-voice.json can connect a local voice runtime and user-owned reference assets for Orc/Goblin profiles. Lich is absent. The assets, model weights, neural config and speech preferences are not committed or redistributed. The restored local configuration points to surviving assets in this workspace.

The renderer uses a reusable model worker, fixed-cache CUDA decoder and windowed waveform generation; speech buffers adapt to measured rendering speed. GPU contention can still increase startup or buffering. Keep speech opt-in. Code tests verify queue/cancellation behavior; earlier local real-model benchmarks are evidence for the saved implementation, not a new playback guarantee.
