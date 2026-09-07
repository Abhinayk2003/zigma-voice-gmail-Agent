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

  const [connected, setConnected] =
    useState(false);

  const [authenticated, setAuthenticated] =
    useState(false);

  const [recording, setRecording] =
    useState(false);

  const [text, setText] =
    useState("");

  const [transcript, setTranscript] =
    useState("");

  const [response, setResponse] =
    useState("");

  const [interimTranscript, setInterimTranscript] =
    useState("");

  const [status, setStatus] =
    useState("Disconnected");

  const [error, setError] =
    useState("");

  const [accountEmail, setAccountEmail] =
    useState("");

  const [checkingSession, setCheckingSession] =
    useState(true);


  // ========================================================================
  // Check Google authentication session
  // ========================================================================

  const checkSession = async () => {

    try {

      setCheckingSession(true);

      console.log(
        "Checking Google session..."
      );

      const sessionResponse =
        await fetch(
          `${BACKEND_URL}/auth/google/session`,
          {
            method: "GET",

            credentials: "include",

            headers: {
              Accept:
                "application/json",
            },
          }
        );


      if (!sessionResponse.ok) {

        throw new Error(
          `Session check failed: ${sessionResponse.status}`
        );
      }


      const data =
        await sessionResponse.json();


      console.log(
        "Google session:",
        data
      );


      const isAuthenticated =
        Boolean(
          data.authenticated
        );


      setAuthenticated(
        isAuthenticated
      );


      setAccountEmail(
        data.account_email ||
          ""
      );


      if (isAuthenticated) {

        setStatus(
          "Google account authenticated"
        );

      } else {

        setStatus(
          "Please sign in with Google"
        );
      }


      return isAuthenticated;


    } catch (err) {

      console.error(
        "Session check failed:",
        err
      );


      setAuthenticated(
        false
      );


      setAccountEmail(
        ""
      );


      setStatus(
        "Unable to verify Google session"
      );


      return false;


    } finally {

      setCheckingSession(
        false
      );
    }
  };


  // ========================================================================
  // Initial session check
  // ========================================================================

  useEffect(() => {

    checkSession();

  }, []);


  // ========================================================================
  // Cleanup on component unmount
  // ========================================================================

  useEffect(() => {

    return () => {

      stopMicrophone();


      if (
        websocketRef.current
      ) {

        try {

          websocketRef.current.close();

        } catch {}

        websocketRef.current =
          null;
      }

    };

  }, []);


  // ========================================================================
  // Google Login
  // ========================================================================

  const signInWithGoogle = () => {

    setError("");

    setStatus(
      "Redirecting to Google..."
    );


    window.location.href =
      `${BACKEND_URL}/auth/google/login`;
  };


  // ========================================================================
  // Logout
  // ========================================================================

  const logout = async () => {

    try {

      stopMicrophone();


      if (
        websocketRef.current
      ) {

        try {

          websocketRef.current.close();

        } catch {}

        websocketRef.current =
          null;
      }


      await fetch(
        `${BACKEND_URL}/auth/google/logout`,
        {
          method: "GET",
          credentials: "include",
        }
      );


    } catch (err) {

      console.error(
        "Logout failed:",
        err
      );


    } finally {

      setAuthenticated(false);

      setAccountEmail("");

      setConnected(false);

      setRecording(false);

      setTranscript("");

      setInterimTranscript("");

      setResponse("");

      setError("");

      setText("");

      setStatus(
        "Signed out"
      );
    }
  };


  // ========================================================================
  // Play received audio
  // ========================================================================

  const playReceivedAudio = async (
    audioData
  ) => {

    try {

      if (!audioData) {
        return;
      }


      console.log(
        "Received binary audio:",
        audioData.byteLength,
        "bytes"
      );


      const blob =
        new Blob(
          [audioData],
          {
            type:
              "audio/wav",
          }
        );


      const audioUrl =
        URL.createObjectURL(
          blob
        );


      if (
        audioRef.current
      ) {

        try {

          audioRef.current.pause();

        } catch {}

        audioRef.current =
          null;
      }


      const audio =
        new Audio(
          audioUrl
        );


      audioRef.current =
        audio;


      audio.onended = () => {

        URL.revokeObjectURL(
          audioUrl
        );


        if (
          audioRef.current ===
          audio
        ) {

          audioRef.current =
            null;
        }
      };


      audio.onerror = () => {

        console.warn(
          "Unable to play received audio."
        );


        URL.revokeObjectURL(
          audioUrl
        );


        if (
          audioRef.current ===
          audio
        ) {

          audioRef.current =
            null;
        }
      };


      await audio.play();


      console.log(
        "Received audio playback started."
      );


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


    // ----------------------------------------------------------------------
    // Verify Google session
    // ----------------------------------------------------------------------

    const sessionValid =
      await checkSession();


    if (!sessionValid) {

      setError(
        "Please sign in with Google first."
      );

      return;
    }


    // ----------------------------------------------------------------------
    // Prevent duplicate WebSocket connections
    // ----------------------------------------------------------------------

    if (
      websocketRef.current &&
      (
        websocketRef.current.readyState ===
          WebSocket.OPEN ||
        websocketRef.current.readyState ===
          WebSocket.CONNECTING
      )
    ) {

      console.log(
        "WebSocket already connected or connecting."
      );

      return;
    }


    // ----------------------------------------------------------------------
    // Determine WebSocket protocol
    // ----------------------------------------------------------------------

    const protocol =
      window.location.protocol ===
      "https:"
        ? "wss:"
        : "ws:";


    const url =
      `${protocol}//${BACKEND_HOST}/ws/voice`;


    console.log(
      "Connecting WebSocket:",
      url
    );


    setStatus(
      "Connecting voice agent..."
    );


    // ----------------------------------------------------------------------
    // Create WebSocket
    // ----------------------------------------------------------------------

    const ws =
      new WebSocket(
        url
      );


    ws.binaryType =
      "arraybuffer";


    websocketRef.current =
      ws;


    // ======================================================================
    // WebSocket Open
    // ======================================================================

    ws.onopen = () => {

      console.log(
        "Voice WebSocket opened."
      );


      setConnected(true);

      setError("");


      setStatus(
        "Waiting for voice agent..."
      );
    };


    // ======================================================================
    // WebSocket Message
    // ======================================================================

    ws.onmessage =
      async (event) => {

        // ------------------------------------------------------------------
        // Binary audio
        // ------------------------------------------------------------------

        if (
          event.data instanceof
          ArrayBuffer
        ) {

          await playReceivedAudio(
            event.data
          );

          return;
        }


        // ------------------------------------------------------------------
        // Blob audio
        // ------------------------------------------------------------------

        if (
          event.data instanceof
          Blob
        ) {

          try {

            const buffer =
              await event.data.arrayBuffer();


            await playReceivedAudio(
              buffer
            );


          } catch (err) {

            console.error(
              "Unable to read binary WebSocket audio:",
              err
            );
          }

          return;
        }


        // ------------------------------------------------------------------
        // JSON messages
        // ------------------------------------------------------------------

        if (
          typeof event.data !==
          "string"
        ) {

          console.warn(
            "Unknown WebSocket message type:",
            typeof event.data
          );

          return;
        }


        let message;


        try {

          message =
            JSON.parse(
              event.data
            );


        } catch {

          console.warn(
            "Invalid WebSocket JSON:",
            event.data
          );

          return;
        }


        console.log(
          "WS MESSAGE:",
          message
        );


        // ================================================================
        // Connected
        // ================================================================

        if (
          message.type ===
          "connected"
        ) {

          setConnected(true);


          setAuthenticated(
            Boolean(
              message.authenticated
            )
          );


          setAccountEmail(
            message.account_email ||
              ""
          );


          setStatus(
            message.authenticated
              ? "Voice Agent Ready"
              : "Authentication required"
          );


          return;
        }


        // ================================================================
        // Audio received
        // ================================================================

        if (
          message.type ===
          "audio_received"
        ) {

          if (
            recordingRef.current
          ) {

            setStatus(
              "Listening..."
            );
          }


          return;
        }


        // ================================================================
        // Speech started
        // ================================================================

        if (
          message.type ===
          "speech_started"
        ) {

          setInterimTranscript(
            ""
          );


          setStatus(
            "Listening..."
          );


          return;
        }


        // ================================================================
        // Interim transcript
        // ================================================================

        if (
          message.type ===
          "interim_transcript"
        ) {

          setInterimTranscript(
            message.text ||
              ""
          );


          setStatus(
            "Recognizing..."
          );


          return;
        }


        // ================================================================
        // Final transcript
        // ================================================================

        if (
          message.type ===
          "transcript"
        ) {

          setTranscript(
            message.text ||
              ""
          );


          setInterimTranscript(
            ""
          );


          setStatus(
            "Processing..."
          );


          return;
        }


        // ================================================================
        // Processing
        // ================================================================

        if (
          message.type ===
          "processing"
        ) {

          setStatus(
            "AI is processing..."
          );


          return;
        }


        // ================================================================
        // Agent response
        // ================================================================

        if (
          message.type ===
          "response"
        ) {

          setResponse(
            message.text ||
              ""
          );


          setStatus(
            message.success
              ? "Completed"
              : "Request failed"
          );


          return;
        }


        // ================================================================
        // Speech ended
        // ================================================================

        if (
          message.type ===
          "speech_ended"
        ) {

          setInterimTranscript(
            ""
          );


          if (
            recordingRef.current
          ) {

            setStatus(
              "Listening..."
            );

          } else {

            setStatus(
              "Ready"
            );
          }


          return;
        }


        // ================================================================
        // Error
        // ================================================================

        if (
          message.type ===
          "error"
        ) {

          console.error(
            "Voice backend error:",
            message.message
          );


          setError(
            message.message ||
              "Voice processing failed."
          );


          setStatus(
            "Error"
          );


          if (
            message.authenticated ===
            false
          ) {

            setAuthenticated(
              false
            );


            setAccountEmail(
              ""
            );


            stopMicrophone();
          }


          return;
        }
      };


    // ======================================================================
    // WebSocket Close
    // ======================================================================

    ws.onclose = (
      event
    ) => {

      console.log(
        "Voice WebSocket closed:",
        event.code,
        event.reason
      );


      stopMicrophone();


      setConnected(false);

      setRecording(false);


      setStatus(
        "Disconnected"
      );


      if (
        websocketRef.current ===
        ws
      ) {

        websocketRef.current =
          null;
      }
    };


    // ======================================================================
    // WebSocket Error
    // ======================================================================

    ws.onerror = (
      event
    ) => {

      console.error(
        "WebSocket error:",
        event
      );


      setError(
        "Unable to connect to the voice backend."
      );


      setStatus(
        "Connection error"
      );
    };
  };


  // ========================================================================
  // Disconnect
  // ========================================================================

  const disconnect = () => {

    stopMicrophone();


    if (
      audioRef.current
    ) {

      try {

        audioRef.current.pause();

      } catch {}

      audioRef.current =
        null;
    }


    if (
      websocketRef.current
    ) {

      try {

        websocketRef.current.close();

      } catch {}

      websocketRef.current =
        null;
    }


    setConnected(false);

    setRecording(false);


    setStatus(
      "Disconnected"
    );
  };


  // ========================================================================
  // Send text
  // ========================================================================

  const sendText = () => {

    const value =
      text.trim();


    if (!value) {
      return;
    }


    if (
      !websocketRef.current ||
      websocketRef.current.readyState !==
        WebSocket.OPEN
    ) {

      setError(
        "Connect to the Voice Agent first."
      );

      return;
    }


    if (!authenticated) {

      setError(
        "Please sign in with Google first."
      );

      return;
    }


    setTranscript(
      value
    );


    setInterimTranscript(
      ""
    );


    setResponse(
      ""
    );


    setError(
      ""
    );


    setStatus(
      "AI is processing..."
    );


    console.log(
      "Sending text command:",
      value
    );


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
        input.length /
          ratio
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
            (i + 1) *
              ratio
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

      // --------------------------------------------------------------------
      // Connection validation
      // --------------------------------------------------------------------

      if (!connected) {

        setError(
          "Connect to the Voice Agent first."
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
          "Voice WebSocket is not connected."
        );

        return;
      }


      if (
        recordingRef.current
      ) {

        console.log(
          "Microphone is already running."
        );

        return;
      }


      try {

        setError("");

        setResponse("");

        setInterimTranscript("");


        setStatus(
          "Requesting microphone..."
        );


        // ================================================================
        // Browser microphone support
        // ================================================================

        if (
          !navigator.mediaDevices ||
          !navigator.mediaDevices.getUserMedia
        ) {

          throw new Error(
            "Browser microphone access is not supported."
          );
        }


        // ================================================================
        // Get microphone
        // ================================================================

        console.log(
          "Requesting microphone permission..."
        );


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


        streamRef.current =
          stream;


        console.log(
          "Microphone permission granted."
        );


        // ================================================================
        // AudioContext
        // ================================================================

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


        console.log(
          "Input sample rate:",
          inputSampleRate
        );


        console.log(
          "Target sample rate:",
          TARGET_SAMPLE_RATE
        );


        // ================================================================
        // Source
        // ================================================================

        const source =
          audioContext.createMediaStreamSource(
            stream
          );


        sourceRef.current =
          source;


        // ================================================================
        // Script processor
        // ================================================================

        const processor =
          audioContext.createScriptProcessor(
            4096,
            1,
            1
          );


        processorRef.current =
          processor;


        // ================================================================
        // Silent output
        // ================================================================

        const silentGain =
          audioContext.createGain();


        silentGain.gain.value =
          0;


        silentGainRef.current =
          silentGain;


        // ================================================================
        // Audio processing
        // ================================================================

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


            // ------------------------------------------------------------
            // Copy microphone buffer
            // ------------------------------------------------------------

            const copied =
              new Float32Array(
                input.length
              );


            copied.set(
              input
            );


            // ------------------------------------------------------------
            // Resample to 16 kHz
            // ------------------------------------------------------------

            const resampled =
              resampleTo16k(
                copied,
                inputSampleRate
              );


            // ------------------------------------------------------------
            // Convert Float32 → Int16
            // ------------------------------------------------------------

            const pcm =
              floatTo16BitPCM(
                resampled
              );


            if (
              pcm.length === 0
            ) {

              return;
            }


            // ------------------------------------------------------------
            // Debug
            // ------------------------------------------------------------

            console.log(
              "SENDING AUDIO:",
              pcm.byteLength,
              "bytes"
            );


            // ------------------------------------------------------------
            // Send raw PCM
            // ------------------------------------------------------------

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


        // ================================================================
        // Connect audio graph
        // ================================================================

        source.connect(
          processor
        );


        processor.connect(
          silentGain
        );


        silentGain.connect(
          audioContext.destination
        );


        // ================================================================
        // Recording state
        // ================================================================

        recordingRef.current =
          true;


        setRecording(
          true
        );


        setStatus(
          "Listening..."
        );


        console.log(
          "============================================================"
        );


        console.log(
          "Microphone streaming started."
        );


        console.log(
          "Streaming format: PCM Int16 / Mono / 16 kHz"
        );


        console.log(
          "============================================================"
        );


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

    console.log(
      "Stopping microphone..."
    );


    recordingRef.current =
      false;


    // ----------------------------------------------------------------------
    // Processor
    // ----------------------------------------------------------------------

    if (
      processorRef.current
    ) {

      try {

        processorRef.current.disconnect();

      } catch {}


      processorRef.current =
        null;
    }


    // ----------------------------------------------------------------------
    // Source
    // ----------------------------------------------------------------------

    if (
      sourceRef.current
    ) {

      try {

        sourceRef.current.disconnect();

      } catch {}


      sourceRef.current =
        null;
    }


    // ----------------------------------------------------------------------
    // Silent gain
    // ----------------------------------------------------------------------

    if (
      silentGainRef.current
    ) {

      try {

        silentGainRef.current.disconnect();

      } catch {}


      silentGainRef.current =
        null;
    }


    // ----------------------------------------------------------------------
    // Stop microphone tracks
    // ----------------------------------------------------------------------

    if (
      streamRef.current
    ) {

      streamRef.current
        .getTracks()
        .forEach(
          (track) => {

            try {

              track.stop();

            } catch {}
          }
        );


      streamRef.current =
        null;
    }


    // ----------------------------------------------------------------------
    // Close AudioContext
    // ----------------------------------------------------------------------

    if (
      audioContextRef.current
    ) {

      const context =
        audioContextRef.current;


      audioContextRef.current =
        null;


      try {

        context.close();

      } catch {}
    }


    setRecording(
      false
    );


    console.log(
      "Microphone stopped."
    );
  };


  // ========================================================================
  // UI
  // ========================================================================

  const connectionLabel =
    connected
      ? (
          recording
            ? "Listening"
            : "Connected"
        )
      : "Disconnected";


  return (

    <div className="app-shell">

      {/* ================================================================
          TOP BAR
          ================================================================ */}

      <header className="topbar">

        <div className="brand-block">

          <div className="brand-mark">
            Z
          </div>

          <div>

            <h1>
              Zigma
            </h1>

            <span>
              Voice Gmail Agent
            </span>

          </div>

        </div>


        <div className="topbar-center">

          <span
            className={
              connected
                ? "status-pill online"
                : "status-pill"
            }
          >

            <span className="status-dot" />

            {connectionLabel}

          </span>


          <span className="provider-pill">
            Amazon Nova Pro
          </span>

        </div>


        <div className="account-block">

          {authenticated ? (

            <>

              <div className="avatar">

                {
                  (
                    accountEmail ||
                    "U"
                  )
                    .charAt(0)
                    .toUpperCase()
                }

              </div>


              <div className="account-text">

                <strong>
                  {accountEmail}
                </strong>

                <span>
                  Google account
                </span>

              </div>


              <button
                className="ghost-button"
                onClick={logout}
              >
                Sign out
              </button>

            </>

          ) : (

            <button
              className="primary-button compact"
              onClick={signInWithGoogle}
              disabled={checkingSession}
            >
              Sign in with Google
            </button>

          )}

        </div>

      </header>


      {/* ================================================================
          MAIN WORKSPACE
          ================================================================ */}

      <main className="workspace">


        {/* ================================================================
            HERO
            ================================================================ */}

        <section className="hero-row">

          <div>

            <div className="eyebrow">
              AI EMAIL WORKSPACE
            </div>


            <h2>
              Gmail Voice Agent.
            </h2>


            <p>
              Speak naturally or type a command.
              Zigma understands your request and
              performs the Gmail action for you.
            </p>

          </div>


          <div className="hero-actions">

            {!connected ? (

              <button
                className="primary-button"
                onClick={connect}
                disabled={
                  !authenticated ||
                  checkingSession
                }
              >
                Connect agent
              </button>

            ) : (

              <button
                className="secondary-button"
                onClick={disconnect}
              >
                Disconnect
              </button>

            )}


            {!recording ? (

              <button
                className="mic-button"
                onClick={startMicrophone}
                disabled={
                  !connected ||
                  !authenticated
                }
              >

                <span className="mic-icon">
                  ●
                </span>

                Start listening

              </button>

            ) : (

              <button
                className="mic-button recording-button"
                onClick={stopMicrophone}
              >

                <span className="recording-pulse" />

                Stop listening

              </button>

            )}

          </div>

        </section>


        {/* ================================================================
            METRICS
            ================================================================ */}

        <section className="metrics-grid">

          <div className="metric-card">

            <span className="metric-label">
              Connection
            </span>

            <strong>
              {connected ? "Ready" : "Offline"}
            </strong>

            <span className="metric-sub">
              WebSocket voice channel
            </span>

          </div>


          <div className="metric-card">

            <span className="metric-label">
              Authentication
            </span>

            <strong>
              {authenticated
                ? "Verified"
                : "Required"}
            </strong>

            <span className="metric-sub">
              Google Gmail access
            </span>

          </div>


          <div className="metric-card">

            <span className="metric-label">
              Model
            </span>

            <strong>
              Nova Pro
            </strong>

            <span className="metric-sub">
              Bedrock inference
            </span>

          </div>


          <div className="metric-card">

            <span className="metric-label">
              Input
            </span>

            <strong>
              {recording
                ? "Live voice"
                : "Voice / Text"}
            </strong>

            <span className="metric-sub">
              16 kHz mono PCM
            </span>

          </div>

        </section>


        {/* ================================================================
            COMMAND CENTER
            ================================================================ */}

        <section className="command-panel panel-card">

          <div className="panel-heading">

            <div>

              <span className="panel-kicker">
                COMMAND CENTER
              </span>

              <h3>
                Ask Zigma
              </h3>

            </div>


            <span
              className={
                connected &&
                authenticated
                  ? "ready-badge"
                  : "muted-badge"
              }
            >

              {
                connected &&
                authenticated
                  ? "Agent ready"
                  : "Connect to begin"
              }

            </span>

          </div>


          <div className="command-input-row">

            <div className="command-icon">
              ⌕
            </div>


            <input
              value={text}
              onChange={
                (event) =>
                  setText(
                    event.target.value
                  )
              }
              onKeyDown={
                (event) => {

                  if (
                    event.key ===
                    "Enter"
                  ) {

                    sendText();
                  }

                }
              }
              placeholder="Try: Show me today's emails, read the first one, or reply to that email..."
              disabled={
                !connected ||
                !authenticated
              }
            />


            <button
              className="send-button"
              disabled={
                !connected ||
                !authenticated ||
                !text.trim()
              }
              onClick={
                sendText
              }
            >
              Send
            </button>

          </div>


          <div className="suggestions">

            <span>
              Try a command
            </span>


            <button
              onClick={
                () =>
                  setText(
                    "Show me today's emails"
                  )
              }
              disabled={
                !connected ||
                !authenticated
              }
            >
              Today's emails
            </button>


            <button
              onClick={
                () =>
                  setText(
                    "Show me unread emails"
                  )
              }
              disabled={
                !connected ||
                !authenticated
              }
            >
              Unread emails
            </button>


            <button
              onClick={
                () =>
                  setText(
                    "Read the first email"
                  )
              }
              disabled={
                !connected ||
                !authenticated
              }
            >
              Read first email
            </button>

          </div>

        </section>


        {/* ================================================================
            VOICE INPUT
            ================================================================ */}

        <section className="voice-input-panel panel-card">

          <div className="panel-heading small">

            <div>

              <span className="panel-kicker">
                VOICE INPUT
              </span>

              <h3>
                Live recognition
              </h3>

            </div>


            {recording && (

              <span className="live-badge">

                <span />

                LIVE

              </span>

            )}

          </div>


          <div className="live-box">

            <div className="waveform">

              {[...Array(40)].map(
                (_, index) => (

                  <span
                    key={index}
                    style={{
                      height:
                        `${10 + ((index * 17) % 34)}px`,
                    }}
                  />

                )
              )}

            </div>


            <p>

              {
                interimTranscript ||
                "Waiting for speech..."
              }

            </p>

          </div>


          <div className="transcript-block">

            <div className="label-row">

              <span>
                Transcript
              </span>

              <span>
                {
                  transcript
                    ? "Latest command"
                    : "No input yet"
                }
              </span>

            </div>


            <div className="transcript-text">

              {
                transcript ||
                "Your spoken or typed command will appear here."
              }

            </div>

          </div>

        </section>


        {/* ================================================================
            AGENT RESPONSE
            ================================================================ */}

        <section className="response-panel panel-card">

          <div className="panel-heading small">

            <div>

              <span className="panel-kicker">
                AI OUTPUT
              </span>

              <h3>
                Agent response
              </h3>

            </div>


            {response && (

              <span className="success-badge">
                Completed
              </span>

            )}

          </div>


          <div className="markdown-output">

            {response ? (

              <ReactMarkdown>
                {response}
              </ReactMarkdown>

            ) : (

              <div className="empty-response">

                <div className="empty-icon">
                  ✦
                </div>

                <strong>
                  Waiting for your command
                </strong>

                <span>
                  Responses from the Gmail agent
                  will appear here.
                </span>

              </div>

            )}

          </div>

        </section>


        {/* ================================================================
            SESSION ACTIVITY
            ================================================================ */}

        <section className="activity-panel panel-card">

          <div className="panel-heading small">

            <div>

              <span className="panel-kicker">
                SESSION ACTIVITY
              </span>

              <h3>
                Current session
              </h3>

            </div>


            <span className="session-id">
              Live interaction
            </span>

          </div>


          <div className="activity-row">

            <div className="activity-item">

              <span className="activity-number">
                01
              </span>

              <div>

                <strong>
                  Authenticate
                </strong>

                <span>
                  {
                    authenticated
                      ? accountEmail
                      : "Google sign-in required"
                  }
                </span>

              </div>

            </div>


            <div className="activity-item">

              <span className="activity-number">
                02
              </span>

              <div>

                <strong>
                  Connect
                </strong>

                <span>
                  {
                    connected
                      ? "Voice WebSocket connected"
                      : "Agent not connected"
                  }
                </span>

              </div>

            </div>


            <div className="activity-item">

              <span className="activity-number">
                03
              </span>

              <div>

                <strong>
                  Process
                </strong>

                <span>
                  {status}
                </span>

              </div>

            </div>

          </div>

        </section>


        {/* ================================================================
            ERROR
            ================================================================ */}

        {error && (

          <div className="error-banner">

            <strong>
              Request error
            </strong>

            <span>
              {error}
            </span>

          </div>

        )}

      </main>


      {/* ================================================================
          FOOTER
          ================================================================ */}

      <footer className="footer">

        <span>
          Zigma Voice Gmail Agent
        </span>

        <span>
          Amazon Bedrock · Gmail API · Voice WebSocket
        </span>

      </footer>

    </div>
  );
}


export default App;