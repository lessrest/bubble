// Browser-side actor system implementation
class Actor {
  constructor(uri, system) {
    this.uri = uri
    this.system = system
    this.mailbox = new TransformStream()
    this.reader = this.mailbox.readable.getReader()
    this.writer = this.mailbox.writable.getWriter()
  }

  async *messages() {
    try {
      while (true) {
        const { value, done } = await this.reader.read()
        if (done) break
        yield value
      }
    } finally {
      this.reader.releaseLock()
    }
  }

  async send(message) {
    await this.writer.write(message)
  }
}

class ActorSystem {
  constructor(site) {
    this.site = site
    this.actors = new Map()
    this.nextId = 0
  }

  createActor(handler) {
    const uri = `${this.site}#${this.nextId++}`
    const actor = new Actor(uri, this)
    this.actors.set(uri, actor)

    // Start the actor's message handling loop
    this.runActor(actor, handler)

    return actor
  }

  async runActor(actor, handler) {
    try {
      await handler(actor)
    } catch (error) {
      console.error("Actor crashed:", error)
    } finally {
      this.actors.delete(actor.uri)
    }
  }

  async send(uri, message) {
    const actor = this.actors.get(uri)
    if (actor) {
      await actor.send(message)
    } else {
      console.warn("Actor not found:", uri)
    }
  }
}

function generateRandomId() {
  // Generate a random UUID v4
  return (
    "urn:uuid:" +
    ([1e7] + -1e3 + -4e3 + -8e3 + -1e11).replace(/[018]/g, (c) =>
      (
        c ^
        (crypto.getRandomValues(new Uint8Array(1))[0] & (15 >> (c / 4)))
      ).toString(16)
    )
  )
}

class JsonLdSocket extends HTMLElement {
  static get observedAttributes() {
    return ["endpoint", "uptime-target"]
  }

  get endpoint() {
    return this.getAttribute("endpoint")
  }

  get uptimeTarget() {
    return this.getAttribute("uptime-target")
  }

  constructor() {
    super()
    this.socket = null
    this.system = null
    this.attachShadow({ mode: "open" })

    // Create basic UI with Tailwind classes
    this.shadowRoot.innerHTML = `
      <div class="block p-4 border border-slate-200 dark:border-slate-800 rounded-lg">
        <div class="status mb-4 font-mono" data-connected="false">⚪ Disconnected</div>
        
        <div class="flex gap-2 mb-4">
          <button class="send-hello px-3 py-2 text-sm 
            bg-white dark:bg-slate-800
            border border-slate-300 dark:border-slate-700 
            rounded-md shadow-sm
            hover:bg-slate-50 dark:hover:bg-slate-700
            focus:outline-none focus:ring-2 focus:ring-indigo-500 dark:focus:ring-indigo-600
            transition-colors duration-150">
            Send Hello Message
          </button>

          <button class="get-uptime px-3 py-2 text-sm 
            bg-white dark:bg-slate-800
            border border-slate-300 dark:border-slate-700 
            rounded-md shadow-sm
            hover:bg-slate-50 dark:hover:bg-slate-700
            focus:outline-none focus:ring-2 focus:ring-indigo-500 dark:focus:ring-indigo-600
            transition-colors duration-150">
            Get Server Uptime
          </button>
        </div>

        <pre class="mt-4 p-4 
          bg-slate-50 dark:bg-slate-900
          border border-slate-200 dark:border-slate-800
          rounded-lg overflow-x-auto
          font-mono text-sm
          whitespace-pre-wrap">
        </pre>
      </div>
    `

    // Add styles for connection status
    const style = document.createElement("style")
    style.textContent = `
      .status[data-connected="true"] { color: rgb(34 197 94); }
      .status[data-connected="false"] { color: rgb(239 68 68); }
    `
    this.shadowRoot.appendChild(style)

    // Get UI elements
    this.statusEl = this.shadowRoot.querySelector(".status")
    this.logEl = this.shadowRoot.querySelector("pre")
    this.sendButton = this.shadowRoot.querySelector(".send-hello")
    this.uptimeButton = this.shadowRoot.querySelector(".get-uptime")

    // Bind methods
    this.sendHello = this.sendHello.bind(this)
    this.connect = this.connect.bind(this)
    this.disconnect = this.disconnect.bind(this)
    this.log = this.log.bind(this)

    // Add event listeners
    this.sendButton.addEventListener("click", this.sendHello)
    this.uptimeButton.addEventListener("click", () => this.requestUptime())
  }

  connectedCallback() {
    const endpoint = this.getAttribute("endpoint")
    if (endpoint) {
      this.connect(endpoint)
    }
  }

  disconnectedCallback() {
    this.disconnect()
  }

  connect(endpoint) {
    try {
      this.log("connecting to", endpoint)
      this.socket = new WebSocket(endpoint)

      // Create actor system when connection established
      this.socket.onopen = () => {
        this.statusEl.textContent = "🟢 Connected"
        this.statusEl.dataset.connected = "true"
        this.log("WebSocket connection established")

        // Initialize actor system with the websocket endpoint as site
        this.system = new ActorSystem(endpoint)

        // Create a log actor that can append to our log
        const logActor = this.system.createActor(
          async function* (actor) {
            for await (const message of actor.messages()) {
              if (message["@type"] === "Append") {
                this.log(message.text)
              }
            }
          }.bind(this)
        )

        this.logActor = logActor
        this.log("Created log actor:", logActor.uri)
      }

      this.socket.onclose = () => {
        this.statusEl.textContent = "⚪ Disconnected"
        this.statusEl.dataset.connected = "false"
        this.log("WebSocket connection closed")
        this.system = null
      }

      this.socket.onerror = (error) => {
        console.error(error)
        this.log(`WebSocket error: ${error.message}`)
      }

      this.socket.onmessage = async (event) => {
        try {
          const data = JSON.parse(event.data)
          this.log("Received:", data)

          // Handle messages addressed to specific actors
          if (data.actor && this.system) {
            await this.system.send(data.actor, data)
          }

          // Dispatch custom event with parsed data
          const customEvent = new CustomEvent("jsonld-message", {
            detail: data,
            bubbles: true,
            composed: true,
          })
          this.dispatchEvent(customEvent)
        } catch (error) {
          this.log(`Error parsing message: ${error}`)
        }
      }
    } catch (error) {
      this.log(`Connection error: ${error}`)
    }
  }

  disconnect() {
    if (this.socket) {
      this.socket.close()
      this.socket = null
    }
    this.system = null
  }

  sendHello() {
    if (!this.socket || this.socket.readyState !== WebSocket.OPEN) {
      this.log("Not connected!")
      return
    }

    const message = {
      "@id": generateRandomId(),
      "@context": {
        "@vocab": "https://node.town/2024/",
      },
      "@type": "Message",
      text: "Hello from browser!",
    }

    try {
      this.socket.send(JSON.stringify(message))
      this.log("Sent:", message)
    } catch (error) {
      this.log(`Error sending message: ${error}`)
    }
  }

  async requestUptime() {
    if (
      !this.socket ||
      this.socket.readyState !== WebSocket.OPEN ||
      !this.logActor ||
      !this.uptimeTarget
    ) {
      this.log("Not ready to request uptime!")
      return
    }

    const message = {
      "@id": generateRandomId(),
      "@context": {
        "@vocab": "https://node.town/2024/",
      },
      "@type": "UptimeRequest",
      target: this.uptimeTarget,
      //replyTo: this.logActor.uri,
    }

    try {
      this.socket.send(JSON.stringify(message))
      this.log("Requested uptime")
    } catch (error) {
      this.log(`Error requesting uptime: ${error}`)
    }
  }

  log(...args) {
    const time = new Date().toISOString()
    const message = args
      .map((arg) =>
        typeof arg === "object" ? JSON.stringify(arg, null, 2) : String(arg)
      )
      .join(" ")

    this.logEl.textContent = `${time} ${message}\n${this.logEl.textContent}`
  }

  // Add a helper method for sending messages
  sendMessage(message) {
    if (!this.socket || this.socket.readyState !== WebSocket.OPEN) {
      throw new Error("Socket not connected")
    }

    // Ensure message has an @id
    if (!message["@id"]) {
      message["@id"] = generateRandomId()
    }

    try {
      this.socket.send(JSON.stringify(message))
      this.log("Sent:", message)
    } catch (error) {
      this.log(`Error sending message: ${error}`)
      throw error
    }
  }
}

// Register the custom element
customElements.define("jsonld-socket", JsonLdSocket)

export { JsonLdSocket, Actor, ActorSystem }
