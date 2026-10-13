import { useCallback, useRef, useState } from "react";
import { api, errorMessage } from "@/lib/api";

export type SttMode = "stream" | "upload";

interface UseSttOptions {
  // stream: live ins Feld (Parakeet). upload: aufnehmen, beim Stoppen an /api/stt senden (Whisper u. a.)
  mode: SttMode;
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

const UPLOAD_MIME_TYPES = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg;codecs=opus"];
const MAX_UPLOAD_RECORDING_MS = 10 * 60 * 1000;

function extensionFor(mime: string): string {
  if (mime.includes("mp4")) return "m4a";
  if (mime.includes("ogg")) return "ogg";
  return "webm";
}

export function useStt({ mode, onText, onFinal, onError }: UseSttOptions) {
  const [recording, setRecording] = useState(false);
  const [transcribing, setTranscribing] = useState(false);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const limitTimerRef = useRef<number | null>(null);
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
    if (recorderRef.current && recorderRef.current.state !== "inactive") {
      recorderRef.current.stop(); // beendet die Aufnahme, danach laeuft der Upload (onstop)
      return;
    }
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ event: "stop" }));
    }
    cleanup();
  }, [cleanup]);

  const startUpload = useCallback(async () => {
    if (!navigator.mediaDevices || !window.MediaRecorder) {
      throw new Error("Die Aufnahme wird von diesem Browser nicht unterstützt.");
    }
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    streamRef.current = stream;
    const mime = UPLOAD_MIME_TYPES.find((t) => MediaRecorder.isTypeSupported(t)) ?? "";
    const recorder = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
    const chunks: Blob[] = [];
    recorder.ondataavailable = (e) => {
      if (e.data.size > 0) chunks.push(e.data);
    };
    recorder.onstop = async () => {
      if (limitTimerRef.current !== null) window.clearTimeout(limitTimerRef.current);
      limitTimerRef.current = null;
      recorderRef.current = null;
      stream.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
      setRecording(false);
      const type = recorder.mimeType || mime || "audio/webm";
      const blob = new Blob(chunks, { type });
      if (blob.size < 1000) return; // versehentlicher Tipp, nichts gesagt
      setTranscribing(true);
      try {
        const form = new FormData();
        form.append("audio", blob, `aufnahme.${extensionFor(type)}`);
        const result = await api.post<{ text: string }>("/api/stt", form);
        const text = (result.text ?? "").trim();
        onTextRef.current(text);
        if (text) onFinalRef.current(text);
      } catch (e) {
        onErrorRef.current(`Spracherkennung fehlgeschlagen: ${errorMessage(e)}`);
      } finally {
        setTranscribing(false);
      }
    };
    recorderRef.current = recorder;
    recorder.start();
    limitTimerRef.current = window.setTimeout(() => recorder.state !== "inactive" && recorder.stop(), MAX_UPLOAD_RECORDING_MS);
    setRecording(true);
  }, []);

  const start = useCallback(async () => {
    if (!window.isSecureContext) {
      throw new Error(
        "Die Spracheingabe braucht eine sichere Verbindung (HTTPS oder localhost). " +
          "Mit http://<Adresse> sperrt der Browser das Mikrofon.",
      );
    }
    if (mode === "upload") {
      await startUpload();
      return;
    }
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
  }, [cleanup, mode, startUpload]);

  return { recording, transcribing, start, stop };
}
