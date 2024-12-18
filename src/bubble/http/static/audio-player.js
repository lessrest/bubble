function attachShadowRoots(root) {
  root.querySelectorAll("template[shadowrootmode]").forEach((template) => {
    const mode = template.getAttribute("shadowrootmode")
    const shadowRoot =
      template.parentNode.shadowRoot ||
      template.parentNode.attachShadow({ mode })
    shadowRoot.appendChild(template.content)
    template.remove()
    attachShadowRoots(shadowRoot)
  })
}

new MutationObserver((records) => {
  for (const record of records) {
    for (const node of record.addedNodes) {
      if (node instanceof HTMLElement) {
        attachShadowRoots(node)
      }
    }
  }
}).observe(document, { childList: true, subtree: true })

class CustomAudioPlayer extends HTMLElement {
  constructor() {
    super()
    this.animationFrameId = null
    this.audio = null
    this.duration = null
    this.internals = this.attachInternals()
    this.overshootFactor = 1.05 // 5% overshoot
    this.isRecording = false
    this.mediaRecorder = null
    this.audioChunks = []
    this.recordingStartTime = null
  }

  static get observedAttributes() {
    return ["src", "duration"]
  }

  attributeChangedCallback(name, oldValue, newValue) {
    if (oldValue === newValue) return

    switch (name) {
      case "src":
        this.handleSrcChange(newValue)
        break
      case "duration":
        this.handleDurationChange(newValue)
        break
    }
  }

  handleSrcChange(newSrc) {
    if (this.audio) {
      this.audio.removeEventListener("play", this.onPlay)
      this.audio.removeEventListener("pause", this.onPause)
      this.audio.removeEventListener("ended", this.audioEnded)
    }

    if (newSrc) {
      this.audio = new Audio(newSrc)
      this.setupAudioEventListeners()
    } else {
      this.audio = null
    }

    setTimeout(() => {
      this.setupUI()
    }, 0)
  }

  handleDurationChange(newDuration) {
    this.duration = newDuration ? parseFloat(newDuration) : null
  }

  connectedCallback() {
    //this.setupShadowDOM()
    //this.setupUI()
    this.setupEventListeners()
  }

  disconnectedCallback() {
    this.stopProgressAnimation()
    this.stopRecording()
    if (this.audio) {
      this.audio.removeEventListener("play", this.onPlay)
      this.audio.removeEventListener("pause", this.onPause)
      this.audio.removeEventListener("ended", this.audioEnded)
    }
  }

  setupShadowDOM() {
    if (!this.shadowRoot) {
      const template = this.querySelector("template")
      const shadowRoot = this.attachShadow({ mode: "open" })
      shadowRoot.appendChild(template.content.cloneNode(true))
    }
  }

  setupUI() {
    this.playPauseBtn = this.shadowRoot.querySelector(".play-pause")
    this.progressBar = this.shadowRoot.querySelector(".progress-bar")
    this.container = this.shadowRoot.querySelector(".container")

    if (this.audio) {
      this.container.classList.add("audio-mode")
      this.container.classList.remove("record-mode")
    } else {
      this.container.classList.add("record-mode")
      this.container.classList.remove("audio-mode")
    }
  }

  setupAudioEventListeners() {
    this.onPlay = () => {
      console.log("Audio playback started")
      document.startViewTransition(() => {
        this.internals.states.add("playing")
        this.startProgressAnimation()
      })
    }

    this.onPause = () => {
      console.log("Audio playback paused")
      document.startViewTransition(() => {
        this.internals.states.delete("playing")
        this.stopProgressAnimation()
      })
    }

    this.audioEnded = () => {
      console.log("Audio playback ended")
      requestAnimationFrame(() => {
        document.startViewTransition(() => {
          this.progressBar.style.strokeDashoffset = "0"
        })
      })
    }

    this.audio.addEventListener("play", this.onPlay)
    this.audio.addEventListener("pause", this.onPause)
    this.audio.addEventListener("ended", this.audioEnded)
  }

  setupEventListeners() {
    this.addEventListener("click", () => {
      if (this.audio) {
        this.togglePlayPause()
      } else {
        this.toggleRecording()
      }
    })
  }

  togglePlayPause() {
    if (this.audio.paused) {
      this.audio.play()
    } else {
      this.audio.pause()
    }
  }

  toggleRecording() {
    if (this.isRecording) {
      this.stopRecording()
    } else {
      this.startRecording()
    }
  }

  async startRecording() {
    console.log("Starting recording...")
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    this.mediaRecorder = new MediaRecorder(stream)
    this.audioChunks = []

    this.mediaRecorder.addEventListener("dataavailable", (event) => {
      console.log("Data available from media recorder")
      this.audioChunks.push(event.data)
    })

    this.mediaRecorder.addEventListener("stop", () => {
      console.log("Recording stopped")
      const audioBlob = new Blob(this.audioChunks, { type: "audio/webm" })
      const audioUrl = URL.createObjectURL(audioBlob)
      this.setAttribute("src", audioUrl)

      const duration = (Date.now() - this.recordingStartTime) / 1000
      console.log(`Recording duration: ${duration} seconds`)
      this.dispatchEvent(
        new CustomEvent("recorded", {
          detail: { audioBlob, duration },
        })
      )
      this.removeAttribute("src")
      this.removeAttribute("duration")
    })

    this.mediaRecorder.start()
    console.log("Media recorder started")
    this.isRecording = true
    this.recordingStartTime = Date.now()
    this.internals.states.add("recording")
    this.dispatchEvent(new Event("recordingStart"))
    console.log("Recording started event dispatched")
  }

  stopRecording() {
    if (this.mediaRecorder && this.mediaRecorder.state === "recording") {
      console.log("Stopping recording...")
      this.mediaRecorder.stop()
      this.isRecording = false
      this.internals.states.delete("recording")
      this.dispatchEvent(new Event("recordingStop"))
      console.log("Recording stopped event dispatched")
    }
  }

  startProgressAnimation() {
    const updateProgress = () => {
      if (this.duration) {
        const rawProgress = this.audio.currentTime / this.duration
        const progress = Math.min(rawProgress * this.overshootFactor, 1)
        const circumference = 2 * Math.PI * 45
        const dashOffset = circumference * (1 - progress)
        this.progressBar.style.strokeDashoffset = dashOffset.toFixed(2)
      }

      if (!this.audio.paused) {
        this.animationFrameId = requestAnimationFrame(updateProgress)
      }
    }

    this.animationFrameId = requestAnimationFrame(updateProgress)
  }

  stopProgressAnimation() {
    if (this.animationFrameId) {
      cancelAnimationFrame(this.animationFrameId)
      this.animationFrameId = null
    }
  }
}

customElements.define("audio-player", CustomAudioPlayer)
