import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import "./App.css";

const TARGET_SAMPLE_RATE = 16000;

const BACKEND_URL =
  import.meta.env.VITE_BACKEND_URL ||
  "http://localhost:8000";

const BACKEND_HOST =
  import.meta.env.VITE_BACKEND_HOST ||
  "localhost:8000";

function App() {
  // ========================================================================
  // Refs
  // ========================================================================

  const websocketRef = useRef(null);
  const audioRef = useRef(null);
  const streamRef = useRef(null);
  const audioContextRef = useRef(null);
  const sourceRef = useRef(null);
  const processorRef = useRef(null);
  const silentGainRef = useRef(null);
  const recordingRef = useRef(false);

  // ========================================================================
  // State
  // ========================================================================

  const [connected, setConnected] = useState(false);
  const [authenticated, setAuthenticated] = useState(false);
  const [recording, setRecording] = useState(false);

  const [text, setText] = useState("");
  const [interimTranscript, setInterimTranscript] = useState("");

  // ------------------------------------------------------------------------
  // Complete frontend conversation history
  // ------------------------------------------------------------------------

  const [messages, setMessages] = useState([]);

  const [status, setStatus] = useState("Disconnected");
  const [error, setError] = useState("");

  const [accountEmail, setAccountEmail] = useState("");
  const [checkingSession, setCheckingSession] = useState(true);

  // ========================================================================
  // Check Google authentication session
  // ========================================================================

  const checkSession = async () => {
    try {
      setCheckingSession(true);

      const sessionResponse = await fetch(
        `${BACKEND_URL}/auth/google/session`,
        {
          method: "GET",
          credentials: "include",
          headers: {
            Accept: "application/json",
          },
        }
      );

      if (!sessionResponse.ok) {
        throw new Error(
          `Session check failed: ${sessionResponse.status}`
        );
      }

      const data = await sessionResponse.json();

      const isAuthenticated = Boolean(data.authenticated);

      setAuthenticated(isAuthenticated);
      setAccountEmail(data.account_email || "");

      if (isAuthenticated) {
        setStatus("Google account connected");
      } else {
        setStatus("Please sign in with Google");
      }

      return isAuthenticated;
    } catch (err) {
      console.error("Session check failed:", err);

      setAuthenticated(false);
      setAccountEmail("");
      setStatus("Unable to verify Google session");

      return false;
    } finally {
      setCheckingSession(false);
    }
  };

  // ========================================================================
  // Initial session check
  // ========================================================================

  useEffect(() => {
    checkSession();
  }, []);

  // ========================================================================
  // Cleanup
  // ========================================================================

  useEffect(() => {
    return () => {
      stopMicrophone();

      if (websocketRef.current) {
        try {
          websocketRef.current.close();
        } catch {}

        websocketRef.current = null;
      }
    };
  }, []);

  // ========================================================================
  // Google Login
  // ========================================================================

  const signInWithGoogle = () => {
    setError("");
    setStatus("Redirecting to Google...");

    window.location.href =
      `${BACKEND_URL}/auth/google/login`;
  };

  // ========================================================================
  // Logout
  // ========================================================================

  const logout = async () => {
    try {
      stopMicrophone();

      if (websocketRef.current) {
        try {
          websocketRef.current.close();
        } catch {}

        websocketRef.current = null;
      }

      await fetch(
        `${BACKEND_URL}/auth/google/logout`,
        {
          method: "GET",
          credentials: "include",
        }
      );
    } catch (err) {
      console.error("Logout failed:", err);
    } finally {
      setAuthenticated(false);
      setAccountEmail("");
      setConnected(false);
      setRecording(false);

      setInterimTranscript("");
      setMessages([]);

      setError("");
      setText("");

      setStatus("Signed out");
    }
  };

  // ========================================================================
  // Play received audio
  // ========================================================================

  const playReceivedAudio = async (audioData) => {
    try {
      if (!audioData) {
        return;
      }

      const blob = new Blob(
        [audioData],
        {
          type: "audio/wav",
        }
      );

      const audioUrl = URL.createObjectURL(blob);

      if (audioRef.current) {
        try {
          audioRef.current.pause();
        } catch {}

        audioRef.current = null;
      }

      const audio = new Audio(audioUrl);

      audioRef.current = audio;

      audio.onended = () => {
        URL.revokeObjectURL(audioUrl);

        if (audioRef.current === audio) {
          audioRef.current = null;
        }
      };

      audio.onerror = () => {
        console.warn(
          "Unable to play received audio."
        );

        URL.revokeObjectURL(audioUrl);

        if (audioRef.current === audio) {
          audioRef.current = null;
        }
      };

      await audio.play();
    } catch (err) {
      console.error(
        "Audio playback failed:",
        err
      );
    }
  };

  // ========================================================================
  // Connect WebSocket
  // ========================================================================

  const connect = async () => {
    setError("");

    const sessionValid = await checkSession();

    if (!sessionValid) {
      setError(
        "Please sign in with Google first."
      );
      return;
    }

    if (
      websocketRef.current &&
      (
        websocketRef.current.readyState ===
          WebSocket.OPEN ||
        websocketRef.current.readyState ===
          WebSocket.CONNECTING
      )
    ) {
      return;
    }

    const protocol =
      window.location.protocol === "https:"
        ? "wss:"
        : "ws:";

    const url =
      `${protocol}//${BACKEND_HOST}/ws/voice`;

    setStatus("Connecting...");

    const ws = new WebSocket(url);

    ws.binaryType = "arraybuffer";

    websocketRef.current = ws;

    // ======================================================================
    // WebSocket Open
    // ======================================================================

    ws.onopen = () => {
      setConnected(true);
      setError("");
      setStatus("Voice agent ready");
    };

    // ======================================================================
    // WebSocket Message
    // ======================================================================

    ws.onmessage = async (event) => {
      // --------------------------------------------------------------------
      // Binary audio
      // --------------------------------------------------------------------

      if (
        event.data instanceof ArrayBuffer
      ) {
        await playReceivedAudio(
          event.data
        );
        return;
      }

      // --------------------------------------------------------------------
      // Blob audio
      // --------------------------------------------------------------------

      if (event.data instanceof Blob) {
        try {
          const buffer =
            await event.data.arrayBuffer();

          await playReceivedAudio(buffer);
        } catch (err) {
          console.error(
            "Unable to read binary WebSocket audio:",
            err
          );
        }

        return;
      }

      // --------------------------------------------------------------------
      // JSON
      // --------------------------------------------------------------------

      if (
        typeof event.data !== "string"
      ) {
        return;
      }

      let message;

      try {
        message = JSON.parse(event.data);
      } catch {
        console.warn(
          "Invalid WebSocket JSON:",
          event.data
        );
        return;
      }

      // ====================================================================
      // Connected
      // ====================================================================

      if (message.type === "connected") {
        setConnected(true);

        setAuthenticated(
          Boolean(message.authenticated)
        );

        setAccountEmail(
          message.account_email || ""
        );

        setStatus(
          message.authenticated
            ? "Voice agent ready"
            : "Authentication required"
        );

        return;
      }

      // ====================================================================
      // Audio received
      // ====================================================================

      if (
        message.type === "audio_received"
      ) {
        if (recordingRef.current) {
          setStatus("Listening...");
        }

        return;
      }

      // ====================================================================
      // Speech started
      // ====================================================================

      if (
        message.type === "speech_started"
      ) {
        setInterimTranscript("");
        setStatus("Listening...");
        return;
      }

      // ====================================================================
      // Interim transcript
      // ====================================================================

      if (
        message.type ===
        "interim_transcript"
      ) {
        setInterimTranscript(
          message.text || ""
        );

        setStatus("Listening...");
        return;
      }

      // ====================================================================
      // Final transcript
      // ====================================================================

      if (
        message.type === "transcript"
      ) {
        const transcriptText =
          (message.text || "").trim();

        if (transcriptText) {
          // --------------------------------------------------------------
          // Add voice user message to conversation history
          // --------------------------------------------------------------

          setMessages((previousMessages) => [
            ...previousMessages,
            {
              id:
                `${Date.now()}-user-${Math.random()}`,
              role: "user",
              content: transcriptText,
            },
          ]);
        }

        setInterimTranscript("");
        setStatus("Processing...");
        return;
      }

      // ====================================================================
      // Processing
      // ====================================================================

      if (
        message.type === "processing"
      ) {
        setStatus("Thinking...");
        return;
      }

      // ====================================================================
      // Agent response
      // ====================================================================

      if (
        message.type === "response"
      ) {
        const responseText =
          (message.text || "").trim();

        if (responseText) {
          // --------------------------------------------------------------
          // ADD response instead of replacing previous response
          // --------------------------------------------------------------

          setMessages((previousMessages) => [
            ...previousMessages,
            {
              id:
                `${Date.now()}-assistant-${Math.random()}`,
              role: "assistant",
              content: responseText,
            },
          ]);
        }

        setStatus(
          message.success
            ? "Completed"
            : "Request failed"
        );

        return;
      }

      // ====================================================================
      // Speech ended
      // ====================================================================

      if (
        message.type === "speech_ended"
      ) {
        setInterimTranscript("");

        if (recordingRef.current) {
          setStatus("Listening...");
        } else {
          setStatus("Ready");
        }

        return;
      }

      // ====================================================================
      // Error
      // ====================================================================

      if (
        message.type === "error"
      ) {
        console.error(
          "Voice backend error:",
          message.message
        );

        setError(
          message.message ||
            "Voice processing failed."
        );

        setStatus("Error");

        if (
          message.authenticated === false
        ) {
          setAuthenticated(false);
          setAccountEmail("");
          stopMicrophone();
        }
      }
    };

    // ======================================================================
    // WebSocket Close
    // ======================================================================

    ws.onclose = (event) => {
      console.log(
        "Voice WebSocket closed:",
        event.code,
        event.reason
      );

      stopMicrophone();

      setConnected(false);
      setRecording(false);
      setStatus("Disconnected");

      if (
        websocketRef.current === ws
      ) {
        websocketRef.current = null;
      }
    };

    // ======================================================================
    // WebSocket Error
    // ======================================================================

    ws.onerror = (event) => {
      console.error(
        "WebSocket error:",
        event
      );

      setError(
        "Unable to connect to the voice agent."
      );

      setStatus("Connection error");
    };
  };

  // ========================================================================
  // Disconnect
  // ========================================================================

  const disconnect = () => {
    stopMicrophone();

    if (audioRef.current) {
      try {
        audioRef.current.pause();
      } catch {}

      audioRef.current = null;
    }

    if (websocketRef.current) {
      try {
        websocketRef.current.close();
      } catch {}

      websocketRef.current = null;
    }

    setConnected(false);
    setRecording(false);
    setStatus("Disconnected");
  };

  // ========================================================================
  // Send text
  // ========================================================================

  const sendText = () => {
    const value = text.trim();

    if (!value) {
      return;
    }

    if (
      !websocketRef.current ||
      websocketRef.current.readyState !==
        WebSocket.OPEN
    ) {
      setError(
        "Connect to the voice agent first."
      );
      return;
    }

    if (!authenticated) {
      setError(
        "Please sign in with Google first."
      );
      return;
    }

    // ----------------------------------------------------------------------
    // Add user message to conversation history
    // ----------------------------------------------------------------------

    setMessages((previousMessages) => [
      ...previousMessages,
      {
        id:
          `${Date.now()}-user-${Math.random()}`,
        role: "user",
        content: value,
      },
    ]);

    setInterimTranscript("");
    setError("");
    setStatus("Thinking...");

    websocketRef.current.send(
      JSON.stringify({
        type: "text",
        text: value,
      })
    );

    setText("");
  };

  // ========================================================================
  // Resample audio to 16 kHz
  // ========================================================================

  const resampleTo16k = (
    input,
    inputSampleRate
  ) => {
    if (
      inputSampleRate ===
      TARGET_SAMPLE_RATE
    ) {
      return input;
    }

    const ratio =
      inputSampleRate /
      TARGET_SAMPLE_RATE;

    const outputLength =
      Math.floor(
        input.length / ratio
      );

    const output =
      new Float32Array(
        outputLength
      );

    let inputIndex = 0;

    for (
      let i = 0;
      i < outputLength;
      i++
    ) {
      const nextInputIndex =
        Math.min(
          Math.floor(
            (i + 1) * ratio
          ),
          input.length
        );

      let sum = 0;
      let count = 0;

      for (
        let j = inputIndex;
        j < nextInputIndex;
        j++
      ) {
        sum += input[j];
        count++;
      }

      output[i] =
        count > 0
          ? sum / count
          : 0;

      inputIndex =
        nextInputIndex;
    }

    return output;
  };

  // ========================================================================
  // Float32 → Int16 PCM
  // ========================================================================

  const floatTo16BitPCM = (
    input
  ) => {
    const output =
      new Int16Array(
        input.length
      );

    for (
      let i = 0;
      i < input.length;
      i++
    ) {
      const sample =
        Math.max(
          -1,
          Math.min(
            1,
            input[i]
          )
        );

      output[i] =
        sample < 0
          ? sample * 0x8000
          : sample * 0x7fff;
    }

    return output;
  };

  // ========================================================================
  // Start microphone
  // ========================================================================

  const startMicrophone =
    async () => {
      if (!connected) {
        setError(
          "Connect to the voice agent first."
        );
        return;
      }

      if (!authenticated) {
        setError(
          "Please sign in with Google first."
        );
        return;
      }

      if (
        websocketRef.current?.readyState !==
        WebSocket.OPEN
      ) {
        setError(
          "Voice agent is not connected."
        );
        return;
      }

      if (recordingRef.current) {
        return;
      }

      try {
        setError("");
        setInterimTranscript("");

        setStatus(
          "Requesting microphone..."
        );

        if (
          !navigator.mediaDevices ||
          !navigator.mediaDevices.getUserMedia
        ) {
          throw new Error(
            "Browser microphone access is not supported."
          );
        }

        const stream =
          await navigator.mediaDevices.getUserMedia(
            {
              audio: {
                channelCount: 1,
                echoCancellation: true,
                noiseSuppression: true,
                autoGainControl: true,
              },
            }
          );

        streamRef.current = stream;

        const AudioContext =
          window.AudioContext ||
          window.webkitAudioContext;

        if (!AudioContext) {
          throw new Error(
            "Web Audio API is not supported."
          );
        }

        const audioContext =
          new AudioContext();

        audioContextRef.current =
          audioContext;

        if (
          audioContext.state ===
          "suspended"
        ) {
          await audioContext.resume();
        }

        const inputSampleRate =
          audioContext.sampleRate;

        const source =
          audioContext.createMediaStreamSource(
            stream
          );

        sourceRef.current = source;

        const processor =
          audioContext.createScriptProcessor(
            4096,
            1,
            1
          );

        processorRef.current =
          processor;

        const silentGain =
          audioContext.createGain();

        silentGain.gain.value = 0;

        silentGainRef.current =
          silentGain;

        processor.onaudioprocess =
          (event) => {
            const ws =
              websocketRef.current;

            if (
              !ws ||
              ws.readyState !==
                WebSocket.OPEN
            ) {
              return;
            }

            if (
              !recordingRef.current
            ) {
              return;
            }

            const input =
              event.inputBuffer
                .getChannelData(0);

            if (
              !input ||
              input.length === 0
            ) {
              return;
            }

            const copied =
              new Float32Array(
                input.length
              );

            copied.set(input);

            const resampled =
              resampleTo16k(
                copied,
                inputSampleRate
              );

            const pcm =
              floatTo16BitPCM(
                resampled
              );

            if (
              pcm.length === 0
            ) {
              return;
            }

            try {
              ws.send(
                pcm.buffer
              );
            } catch (err) {
              console.error(
                "Failed to send audio:",
                err
              );
            }
          };

        source.connect(processor);

        processor.connect(
          silentGain
        );

        silentGain.connect(
          audioContext.destination
        );

        recordingRef.current =
          true;

        setRecording(true);
        setStatus("Listening...");
      } catch (err) {
        console.error(
          "Microphone error:",
          err
        );

        stopMicrophone();

        setError(
          err?.message ||
            "Microphone access failed."
        );

        setStatus(
          "Microphone error"
        );
      }
    };

  // ========================================================================
  // Stop microphone
  // ========================================================================

  const stopMicrophone = () => {
    recordingRef.current = false;

    if (processorRef.current) {
      try {
        processorRef.current.disconnect();
      } catch {}

      processorRef.current = null;
    }

    if (sourceRef.current) {
      try {
        sourceRef.current.disconnect();
      } catch {}

      sourceRef.current = null;
    }

    if (silentGainRef.current) {
      try {
        silentGainRef.current.disconnect();
      } catch {}

      silentGainRef.current = null;
    }

    if (streamRef.current) {
      streamRef.current
        .getTracks()
        .forEach((track) => {
          try {
            track.stop();
          } catch {}
        });

      streamRef.current = null;
    }

    if (audioContextRef.current) {
      const context =
        audioContextRef.current;

      audioContextRef.current = null;

      try {
        context.close();
      } catch {}
    }

    setRecording(false);
  };

  // ========================================================================
  // Quick command
  // ========================================================================

  const useSuggestion = (value) => {
    setText(value);
    setError("");
  };

  // ========================================================================
  // Derived UI state
  // ========================================================================

  const isReady =
    connected && authenticated;

  const hasConversation =
    messages.length > 0 ||
    Boolean(interimTranscript);

  // ========================================================================
  // UI
  // ========================================================================

  return (
    <div className="app-shell">

      {/* ==================================================================
          HEADER
          ================================================================== */}

      <header className="topbar">

        <div className="brand">
          <div className="brand-icon">
            Z
          </div>

          <div className="brand-name">
            <strong>Zigma</strong>
            <span>Mail Assistant</span>
          </div>
        </div>

        <div className="header-right">

          {authenticated ? (
            <div className="account">

              <div className="account-avatar">
                {(
                  accountEmail || "U"
                )
                  .charAt(0)
                  .toUpperCase()}
              </div>

              <span className="account-email">
                {accountEmail}
              </span>

              <button
                className="signout-button"
                onClick={logout}
              >
                Sign out
              </button>

            </div>
          ) : (
            <button
              className="google-button"
              onClick={signInWithGoogle}
              disabled={checkingSession}
            >
              <span className="google-g">
                G
              </span>

              Sign in with Google
            </button>
          )}

        </div>

      </header>

      {/* ==================================================================
          MAIN
          ================================================================== */}

      <main className="main-content">

        {!hasConversation ? (

          /* ================================================================
             EMPTY / WELCOME STATE
             ================================================================ */

          <section className="welcome">

            <div className="welcome-icon">
              ✦
            </div>

            <p className="welcome-label">
              ZIGMA MAIL ASSISTANT
            </p>

            <h1>
              Your Gmail,
              <br />
              <span>just a conversation.</span>
            </h1>

            <p className="welcome-description">
              Ask Zigma to find, read, send,
              reply to, or manage your emails
              using your voice or text.
            </p>

            {!authenticated ? (

              <button
                className="welcome-google-button"
                onClick={signInWithGoogle}
                disabled={checkingSession}
              >
                <span>G</span>
                Connect Gmail with Google
              </button>

            ) : !connected ? (

              <button
                className="connect-button"
                onClick={connect}
              >
                Connect to Zigma
              </button>

            ) : null}

            <div className="suggestion-area">

              <span className="suggestion-label">
                Try asking
              </span>

              <div className="suggestions">

                <button
                  onClick={() =>
                    useSuggestion(
                      "Show me today's received mails"
                    )
                  }
                  disabled={!isReady}
                >
                  Show today's emails
                </button>

                <button
                  onClick={() =>
                    useSuggestion(
                      "Show me unread emails"
                    )
                  }
                  disabled={!isReady}
                >
                  Show unread emails
                </button>

                <button
                  onClick={() =>
                    useSuggestion(
                      "Find my latest email"
                    )
                  }
                  disabled={!isReady}
                >
                  Find my latest email
                </button>

              </div>

            </div>

          </section>

        ) : (

          /* ================================================================
             CONVERSATION
             ================================================================ */

          <section className="conversation">

            <div className="conversation-header">

              <div>
                <span className="conversation-label">
                  CONVERSATION
                </span>

                <h2>
                  Gmail Assistant
                </h2>
              </div>

              <div className="connection-status">

                <span
                  className={
                    isReady
                      ? "status-dot connected"
                      : "status-dot"
                  }
                />

                {recording
                  ? "Listening"
                  : isReady
                    ? "Ready"
                    : "Offline"}

              </div>

            </div>

            <div className="messages">

              {/* ==========================================================
                  SAVED CONVERSATION HISTORY
                  ========================================================== */}

              {messages.map((message) => (

                message.role === "user" ? (

                  <div
                    className="message user-message"
                    key={message.id}
                  >

                    <div className="message-avatar user-avatar">
                      You
                    </div>

                    <div className="message-content">

                      <span className="message-name">
                        You
                      </span>

                      <div className="message-bubble">
                        {message.content}
                      </div>

                    </div>

                  </div>

                ) : (

                  <div
                    className="message assistant-message"
                    key={message.id}
                  >

                    <div className="message-avatar assistant-avatar">
                      Z
                    </div>

                    <div className="message-content">

                      <span className="message-name">
                        Zigma
                      </span>

                      <div className="assistant-bubble">

                        <ReactMarkdown>
                          {message.content}
                        </ReactMarkdown>

                      </div>

                    </div>

                  </div>

                )

              ))}

              {/* ==========================================================
                  LIVE INTERIM VOICE TRANSCRIPT
                  ========================================================== */}

              {interimTranscript && (

                <div className="message user-message">

                  <div className="message-avatar user-avatar">
                    You
                  </div>

                  <div className="message-content">

                    <span className="message-name">
                      You
                    </span>

                    <div className="message-bubble interim">
                      {interimTranscript}
                    </div>

                  </div>

                </div>

              )}

            </div>

          </section>

        )}

        {/* ==================================================================
            ERROR
            ================================================================== */}

        {error && (
          <div className="error-message">

            <span className="error-icon">
              !
            </span>

            <span>
              {error}
            </span>

            <button
              onClick={() =>
                setError("")
              }
            >
              ×
            </button>

          </div>
        )}

      </main>

      {/* ==================================================================
          INPUT AREA
          ================================================================== */}

      <div className="input-area">

        {!authenticated && (
          <p className="input-hint">
            Sign in with Google to start using Zigma.
          </p>
        )}

        {authenticated && !connected && (
          <button
            className="connect-inline"
            onClick={connect}
          >
            Connect to voice agent
          </button>
        )}

        <div
          className={
            `input-box ${
              recording
                ? "input-recording"
                : ""
            }`
          }
        >

          <button
            className={
              `mic-button ${
                recording
                  ? "mic-active"
                  : ""
              }`
            }
            onClick={
              recording
                ? stopMicrophone
                : startMicrophone
            }
            disabled={!isReady}
            title={
              recording
                ? "Stop listening"
                : "Start listening"
            }
          >

            {recording ? (
              <span className="stop-icon" />
            ) : (
              <span className="mic-icon">
                🎙
              </span>
            )}

          </button>

          <input
            value={text}
            onChange={(event) =>
              setText(
                event.target.value
              )
            }
            onKeyDown={(event) => {
              if (
                event.key ===
                "Enter"
              ) {
                sendText();
              }
            }}
            placeholder={
              recording
                ? "Listening..."
                : "Ask Zigma anything about your Gmail..."
            }
            disabled={!isReady}
          />

          <button
            className="send-button"
            onClick={sendText}
            disabled={
              !isReady ||
              !text.trim()
            }
            title="Send"
          >
            ➤
          </button>

        </div>

        <div className="input-footer">

          <span>
            {recording
              ? "Zigma is listening..."
              : status}
          </span>

          <span>
            Voice or text
          </span>

        </div>

      </div>

      {/* ==================================================================
          FOOTER
          ================================================================== */}

      <footer className="footer">

        <span>
          Zigma Mail Assistant
        </span>

        <span>
          Your Gmail assistant
        </span>

      </footer>

    </div>
  );
}

export default App;