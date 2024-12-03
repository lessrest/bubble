/**
 * VoiceRecorderWriter combines audio recording UI with real-time transcription.
 * It provides a circular progress indicator during recording and streams audio
 * for transcription simultaneously.
 */
export class VoiceRecorderWriter extends HTMLElement {
  constructor() {
    super()
    this.handleTranscript = this.handleTranscript.bind(this)
    this.isRecording = false
    this.internals = this.attachInternals()
    this.reconnectAttempts = 0
    this.maxReconnectAttempts = 5
    this.reconnectDelay = 1000
    this.lastTranscriptTime = 0
    this.packetEma = 0
    this.emaAlpha = 0.1
    this.speechThreshold = 130
  }

  static get observedAttributes() {
    return ["language", "server"]
  }

  get language() {
    return this.getAttribute("language") ?? "en-US"
  }

  get server() {
    return this.getAttribute("server") ?? "wss://swa.sh"
  }

  get wsUrl() {
    return `${this.server}/transcribe?language=${this.language}`
  }

  connectedCallback() {
    this.setupUI()
    this.setupEventListeners()
  }

  disconnectedCallback() {
    this.stopRecording()
    this.ws?.close()
  }

  setupUI() {
    // Create shadow DOM structure
    const shadow = this.attachShadow({ mode: "open" })

    // Add styles
    const style = document.createElement("style")
    style.textContent = `
      :host {
        display: flex;
        position: relative;
        cursor: pointer;
      }

      .container {
        display: flex;
        flex-direction: row;
        align-items: start;
        gap: 1em;
        border-color: #ff3b30;
        filter: grayscale(0.8);
        transition: filter 0.2s ease-in-out;
      }

      .container:hover, .recording.container {
        filter: grayscale(0.0);
      }

      .wave-container {
      flex-shrink: 0;
        border: 2px solid #ccc3;
        height: 6mm;
        width: 6mm;
        background: #9b000061;
        border-radius: 50%;
        overflow: hidden;
        border-color: oklab(0.49 0.14 0.06 / 0.7);
        box-shadow: 0px 0px 6mm #aaa8;
      }

      svg {
        width: 12mm;
      }

      path {
        fill: none;
        stroke: #ccc3;
        stroke-width: 8;
        stroke-linecap: round;
        transform: translateX(0);
        stroke: #FF3B30;
        filter: blur(0px) drop-shadow(-24px 0px 4px #ff3b30) drop-shadow(24px 0px 6px #ff3b30);
      }

      .recording path {
        animation: waveMove 2s cubic-bezier(0.41, 0.76, 0.44, 0.17) infinite;
      }

      .recording .wave-container {
        transform-origin: center;
      }

      @keyframes waveMove {
        from {
          transform: translateX(0);
        }

        50% {
          transform: translateX(-25%);
        }

        to {
          transform: translateX(-50%);
        }
      }

      @keyframes waveSpin {
        from {
          transform: rotate(0deg);
        }

        25% {
          transform: rotate(12deg);
        }

        50% {
          transform: rotate(-12deg);
        }

        to {
          transform: rotate(0deg);
        }
      }

      @keyframes blurwait {
        from {
          filter: blur(0px);
        }

        50% {
          filter: blur(3px);
        }

        to {
          filter: blur(0px);
        }
      }

      .transcript {
      }

      .transcript ins {
        text-decoration: none;
        opacity: 0.6;
      }

      .transcript br {
        content: " ";
        display: block;
        margin: 0.5em 0;
      }
    `

    // Create SVG structure
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg")
    svg.setAttribute("viewBox", "0 0 200 100")

    const wavePath = document.createElementNS(
      "http://www.w3.org/2000/svg",
      "path"
    )
    const points = []
    for (let x = -100; x <= 300; x += 5) {
      const y = 50 + Math.sin((x / 100) * Math.PI * 2) * 30
      points.push(`${x} ${y}`)
    }
    wavePath.setAttribute("d", `M ${points.join(" L ")}`)

    const waveContainer = document.createElement("div")
    waveContainer.classList.add("wave-container")

    svg.appendChild(wavePath)
    waveContainer.appendChild(svg)

    const container = document.createElement("div")
    container.classList.add("container")
    container.appendChild(waveContainer)

    const transcript = document.createElement("type-writer")
    transcript.classList.add("transcript")
    container.appendChild(transcript)

    shadow.appendChild(style)
    shadow.appendChild(container)

    this.container = container
    this.transcriptDiv = transcript
  }

  setupEventListeners() {
    this.addEventListener("click", () => this.toggleRecording())
  }

  async toggleRecording() {
    if (this.isRecording) {
      this.stopRecording()
    } else {
      this.startRecording()
    }
  }

  async startRecording() {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: true,
      })
      await this.connectWebSocket()

      // Initialize audio context and processing
      this.context = new AudioContext()
      this.source = this.context.createMediaStreamSource(stream)
      const channels =
        stream.getAudioTracks()[0].getSettings().channelCount ?? 1
      this.processor = this.context.createScriptProcessor(16384, channels, 1)

      // Configure audio encoder
      this.encoder = new AudioEncoder({
        output: (packet) => {
          if (this.ws?.readyState === WebSocket.OPEN) {
            const buffer = new ArrayBuffer(packet.byteLength)
            packet.copyTo(buffer)
            this.ws.send(buffer)
          }
        },
        error: console.error,
      })

      await this.encoder.configure({
        codec: "opus",
        sampleRate: 48000,
        numberOfChannels: 1,
        opus: { application: "lowdelay", signal: "voice" },
      })

      // Connect audio pipeline
      this.source.connect(this.processor)
      this.processor.connect(this.context.destination)
      this.processor.addEventListener(
        "audioprocess",
        this.processAudio.bind(this)
      )

      this.isRecording = true
      this.container.classList.add("recording")
      this.internals.states.add("recording")
    } catch (error) {
      console.error("Error starting recording:", error)
    }
  }

  stopRecording() {
    this.encoder?.close()
    this.processor?.disconnect()
    this.source?.disconnect()
    this.context?.close()
    this.ws?.close()

    this.isRecording = false
    this.container.classList.remove("recording")
    this.internals.states.delete("recording")
  }

  connectWebSocket() {
    return new Promise((resolve, reject) => {
      this.ws = new WebSocket(this.wsUrl)
      this.ws.binaryType = "arraybuffer"

      this.ws.addEventListener("message", this.handleTranscript)
      this.ws.addEventListener("open", () => {
        console.log("Connected to transcription service")
        this.reconnectAttempts = 0
        this.reconnectDelay = 1000
        resolve()
      })

      this.ws.addEventListener("close", () => {
        console.log("Disconnected from transcription service")
        this.attemptReconnect()
      })

      this.ws.addEventListener("error", (error) => {
        console.error("WebSocket error:", error)
        reject(error)
      })
    })
  }

  processAudio(event) {
    if (this.ws?.readyState !== WebSocket.OPEN) return

    const inputData = event.inputBuffer.getChannelData(0)
    const buffer = new ArrayBuffer(inputData.length * 4)
    const view = new DataView(buffer)

    for (let i = 0; i < inputData.length; i++) {
      view.setFloat32(i * 4, inputData[i], true)
    }

    this.encoder?.encode(
      new AudioData({
        data: buffer,
        timestamp: event.playbackTime * 1000000,
        format: "f32",
        numberOfChannels: 1,
        numberOfFrames: inputData.length,
        sampleRate: 48000,
      })
    )
  }

  handleTranscript(event) {
    if (typeof event.data !== "string") return

    try {
      const result = JSON.parse(event.data)
      if (
        !result.type === "Results" ||
        !result.channel?.alternatives?.[0]?.transcript
      )
        return

      const text = result.channel.alternatives[0].transcript
      if (!text) return

      const currentTime = Date.now()
      const timeSinceLastTranscript = currentTime - this.lastTranscriptTime

      if (timeSinceLastTranscript > 5000 && this.lastTranscriptTime) {
        this.transcriptDiv.appendChild(document.createElement("br"))
      }

      this.lastTranscriptTime = currentTime
      let element = this.transcriptDiv.lastElementChild

      if (!element || !element.matches("ins")) {
        element = document.createElement("ins")
        this.transcriptDiv.appendChild(element)
      }

      document.startViewTransition(() => {
        element.textContent = text
      })

      if (result.is_final) {
        const span = document.createElement("span")
        span.textContent = text + (text.match(/[.!?]$/) ? " " : "— ")
        document.startViewTransition(() => {
          element.replaceWith(span)
        })
      }
    } catch (error) {
      console.error("Error parsing transcript:", error)
    }
  }
}

// Register the custom element
customElements.define("voice-recorder-writer", VoiceRecorderWriter)
