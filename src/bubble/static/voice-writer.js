/**
 * VoiceWriter is a custom element that creates a seamless voice-to-text experience.
 * It captures audio input, streams it to a WebSocket server for real-time transcription,
 * and displays the results with a typewriter effect, showing interim results in a faded
 * style and final transcriptions in solid text.
 */
export class VoiceWriter extends HTMLElement {
  constructor() {
    super()
    this.handleTranscript = this.handleTranscript.bind(this)
    this.processAudio = this.processAudio.bind(this)
    this.reconnectAttempts = 0
    this.maxReconnectAttempts = 5
    this.reconnectDelay = 1000
    this.lastTranscriptTime = Date.now()

    // Audio processing metrics
    this.bytesSent = 0
    this.uploadRate = 0
    this.movingAverage = 0
    this.alpha = 0.2 // Smoothing factor for moving average
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
    this.writer = document.createElement("type-writer")
    this.writer.className = "block"
    this.appendChild(this.writer)

    navigator.mediaDevices
      .getUserMedia({ audio: true })
      .then((stream) => this.beginListening(stream))
      .catch(console.error)
  }

  disconnectedCallback() {
    this.encoder?.close()
    this.processor?.disconnect()
    this.source?.disconnect()
    this.context?.close()
    this.ws?.close()
  }

  async connectWebSocket() {
    try {
      this.ws = new WebSocket(this.wsUrl)
      this.ws.binaryType = "arraybuffer"

      this.ws.addEventListener("message", this.handleTranscript)
      this.ws.addEventListener("open", () => {
        console.log("🎤 Connected to transcription service")
        this.reconnectAttempts = 0
        this.reconnectDelay = 1000
      })

      this.ws.addEventListener("close", () => {
        console.log("🎤 Disconnected from transcription service")
        this.attemptReconnect()
      })

      this.ws.addEventListener("error", (error) => {
        console.error("🎤 WebSocket error:", error)
      })
    } catch (error) {
      console.error("🎤 Failed to connect:", error)
    }
  }

  attemptReconnect() {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      console.error("🎤 Max reconnection attempts reached")
      return
    }

    setTimeout(() => {
      this.reconnectAttempts++
      this.connectWebSocket()
      this.reconnectDelay = Math.min(this.reconnectDelay * 2, 10000)
    }, this.reconnectDelay)
  }

  async beginListening(stream) {
    await this.connectWebSocket()

    // Initialize audio context and processing pipeline
    this.context = new AudioContext()
    this.source = this.context.createMediaStreamSource(stream)
    const channels = stream.getAudioTracks()[0].getSettings().channelCount ?? 1
    this.processor = this.context.createScriptProcessor(16384, channels, 1)

    // Configure audio encoder
    this.encoder = new AudioEncoder({
      output: (packet) => {
        if (this.ws?.readyState === WebSocket.OPEN) {
          const buffer = new ArrayBuffer(packet.byteLength)
          packet.copyTo(buffer)
          this.ws.send(buffer)
          this.bytesSent += buffer.byteLength
        }
      },
      error: console.error,
    })

    await this.encoder.configure({
      codec: "opus",
      sampleRate: 48000,
      numberOfChannels: 1,
      opus: {
        application: "lowdelay",
        signal: "voice",
      },
    })

    // Connect audio pipeline
    this.source.connect(this.processor)
    this.processor.connect(this.context.destination)
    this.processor.addEventListener("audioprocess", this.processAudio)
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

      // Add line break for natural pauses
      if (timeSinceLastTranscript > 5000 && this.writer.lastElementChild) {
        this.writer.appendChild(document.createElement("br"))
      }

      this.lastTranscriptTime = currentTime
      let element = this.writer.lastElementChild

      // Use <ins> for interim results
      if (!element || !element.matches("ins")) {
        element = document.createElement("ins")
        this.writer.appendChild(element)
      }

      element.textContent = text

      if (result.is_final) {
        // Convert to final text with appropriate punctuation
        const span = document.createElement("span")
        span.textContent = text + (text.match(/[.!?]$/) ? " " : "— ")

        // Smooth transition from interim to final text
        document.startViewTransition(() => {
          element.replaceWith(span)
        })
      }
    } catch (error) {
      console.error("Error parsing transcript:", error)
    }
  }
}

// Add styles for interim transcriptions
const sheet = new CSSStyleSheet()
sheet.replaceSync(`
    voice-writer ins {
      text-decoration: none;
      opacity: 0.6;
    }

    voice-writer br {
      display: block;
      content: " ";
    }
  `)

document.adoptedStyleSheets = [...document.adoptedStyleSheets, sheet]

// Register the custom element
customElements.define("voice-writer", VoiceWriter)

// Usage:
// <voice-writer language="en-US" server="wss://swa.sh"></voice-writer>
