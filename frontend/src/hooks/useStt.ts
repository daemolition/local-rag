import { useCallback, useRef, useState } from "react";

interface UseSttOptions {
  onText: (text: string) => void;
  onFinal: (text: string) => void;
  onError: (message: string) => void;
}

interface SttMessage {
  partial?: string;
  committed?: string;
  final?: string;
  error?: string;
}

const WORKLET_URL = `${import.meta.env.BASE_URL}pcm-worklet-processor.js`;

export function useStt({ onText, onFinal, onError }: UseSttOptions) {
  const [recording, setRecording] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const workletRef = useRef<AudioWorkletNode | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const committedRef = useRef("");
  const onTextRef = useRef(onText);
  const onFinalRef = useRef(onFinal);
  const onErrorRef = useRef(onError);
  onTextRef.current = onText;
  onFinalRef.current = onFinal;
  onErrorRef.current = onError;

  const cleanup = useCallback(() => {
    workletRef.current?.disconnect();
    workletRef.current = null;
    audioContextRef.current?.close().catch(() => {});
    audioContextRef.current = null;
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    setRecording(false);
  }, []);

  const stop = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ event: "stop" }));
    }
    cleanup();
  }, [cleanup]);

  const start = useCallback(async () => {
    if (!navigator.mediaDevices || !window.AudioContext || !window.AudioWorkletNode) {
      throw new Error("Live-Spracheingabe wird von diesem Browser nicht unterstützt.");
    }

    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    streamRef.current = stream;

    const audioContext = new AudioContext({ sampleRate: 16000 });
    audioContextRef.current = audioContext;
    await audioContext.audioWorklet.addModule(WORKLET_URL);

    const source = audioContext.createMediaStreamSource(stream);
    const worklet = new AudioWorkletNode(audioContext, "pcm-worklet-processor");
    workletRef.current = worklet;

    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const ws = new WebSocket(`${protocol}//${window.location.host}/ws/stt-stream`);
    ws.binaryType = "arraybuffer";
    wsRef.current = ws;
    committedRef.current = "";

    ws.onopen = () => {
      const silentGain = audioContext.createGain();
      silentGain.gain.value = 0;
      source.connect(worklet);
      worklet.connect(silentGain);
      silentGain.connect(audioContext.destination);
    };

    worklet.port.onmessage = (event: MessageEvent<Float32Array>) => {
      if (ws.readyState === WebSocket.OPEN) ws.send(event.data.buffer);
    };

    ws.onmessage = (event) => {
      let msg: SttMessage;
      try {
        msg = JSON.parse(event.data as string) as SttMessage;
      } catch {
        return;
      }

      if (msg.error) {
        cleanup();
        ws.close();
        onErrorRef.current(`Spracherkennung fehlgeschlagen: ${msg.error}`);
        return;
      }
      if (msg.committed !== undefined) {
        committedRef.current = msg.committed;
        onTextRef.current(msg.committed);
      }
      if (msg.partial) {
        const combined = committedRef.current
          ? `${committedRef.current} ${msg.partial}`
          : msg.partial;
        onTextRef.current(combined.trim());
      }
      if (msg.final !== undefined) {
        onTextRef.current(msg.final);
        ws.close();
        cleanup();
        if (msg.final) onFinalRef.current(msg.final);
      }
    };

    ws.onerror = () => {
      cleanup();
      onErrorRef.current("Verbindung zur Spracherkennung fehlgeschlagen.");
    };

    setRecording(true);
  }, [cleanup]);

  return { recording, start, stop };
}
