// AudioWorklet-Prozessor: sammelt eingehende Float32-PCM-Frames (bereits vom
// Browser auf die AudioContext-Sample-Rate resampelt) zu Chunks fester Groesse
// und schickt sie per postMessage an den Main-Thread, der sie roh ueber den
// WebSocket-Proxy (/ws/stt-stream) an den Parakeet-Server weiterleitet.
class PCMWorkletProcessor extends AudioWorkletProcessor {
    constructor(options) {
        super();
        const chunkSize = (options && options.processorOptions && options.processorOptions.chunkSize) || 2048;
        this._chunkSize = chunkSize;
        this._buffer = new Float32Array(chunkSize);
        this._offset = 0;
    }

    process(inputs) {
        const input = inputs[0];
        if (input && input.length > 0) {
            const channelData = input[0];
            for (let i = 0; i < channelData.length; i++) {
                this._buffer[this._offset++] = channelData[i];
                if (this._offset >= this._chunkSize) {
                    this.port.postMessage(this._buffer.slice(0));
                    this._offset = 0;
                }
            }
        }
        return true;
    }
}

registerProcessor('pcm-worklet-processor', PCMWorkletProcessor);
