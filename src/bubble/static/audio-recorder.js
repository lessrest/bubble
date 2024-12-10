export class AudioRecorder extends HTMLElement {
  constructor() {
    super()
    this.isRecording = false
    this.internals = this.attachInternals()
  }

  static get observedAttributes() {
    return ["language", "endpoint"]
  }

  get language() {
    return this.getAttribute("language") ?? "en-US"
  }

  get endpoint() {
    return this.getAttribute("endpoint") ?? "/audio"
  }

  connectedCallback() {
    this.setupUI()
    this.setupEventListeners()
  }

  disconnectedCallback() {
    this.stopRecording()
  }

  setupUI() {
    const shadow = this.attachShadow({ mode: "open" })

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
        box-shadow: 0px 0px 6mm #aaa3;
      }

      .recording .wave-container {
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
        from { transform: translateX(0); }
        50% { transform: translateX(-25%); }
        to { transform: translateX(-50%); }
      }
    `

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

    shadow.appendChild(style)
    shadow.appendChild(container)

    this.container = container
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

      this.mediaRecorder = new MediaRecorder(stream, {
        mimeType: "audio/webm;codecs=opus",
      })

      // Create WebSocket connection
      this.ws = new WebSocket(this.endpoint)

      this.ws.addEventListener("error", (error) => {
        console.error("WebSocket error:", error)
        this.stopRecording()
      })

      this.ws.addEventListener("close", () => {
        if (this.isRecording) {
          this.stopRecording()
        }
      })

      // Wait for WebSocket connection to be established
      await new Promise((resolve, reject) => {
        this.ws.addEventListener("open", resolve)
        this.ws.addEventListener("error", reject)
      })

      this.mediaRecorder.addEventListener("dataavailable", async (event) => {
        if (event.data.size > 0 && this.ws?.readyState === WebSocket.OPEN) {
          try {
            // Convert Blob to ArrayBuffer and send
            const arrayBuffer = await event.data.arrayBuffer()
            this.ws.send(arrayBuffer)
          } catch (error) {
            console.error("Error sending audio chunk:", error)
          }
        }
      })

      this.mediaRecorder.addEventListener("stop", () => {
        if (this.ws?.readyState === WebSocket.OPEN) {
          this.ws.close()
        }
      })

      // Request data every 250ms
      this.mediaRecorder.start(250)

      this.isRecording = true
      this.container.classList.add("recording")
      this.internals.states.add("recording")
    } catch (error) {
      console.error("Error starting recording:", error)
    }
  }

  stopRecording() {
    if (this.mediaRecorder && this.mediaRecorder.state !== "inactive") {
      this.mediaRecorder.stop()
      this.mediaRecorder.stream.getTracks().forEach((track) => track.stop())
    }

    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.close()
    }

    this.isRecording = false
    this.container.classList.remove("recording")
    this.internals.states.delete("recording")
  }
}

// Register the custom element
customElements.define("audio-recorder", AudioRecorder)
