/**
 * Copyright (c) 2024 Mikael Brockman <https://github.com/mbrock>
 *
 * Permission is hereby granted, free of charge, to any person obtaining a copy
 * of this software and associated documentation files (the "Software"), to deal
 * in the Software without restriction, including without limitation the rights
 * to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
 * copies of the Software, and to permit persons to whom the Software is
 * furnished to do so, subject to the following conditions:
 *
 * The above copyright notice and this permission notice shall be included in all
 * copies or substantial portions of the Software.
 *
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 * IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 * FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
 * AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
 * LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
 * OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
 * SOFTWARE.
 */

/**
 * TypeWriter reveals text gradually using the CSS Highlight API,
 * creating a smooth typing animation.
 *
 * The typing speed varies based on punctuation and position in the text,
 * with natural pauses at punctuation marks and acceleration as it progresses.
 */
export class TypeWriter extends HTMLElement {
  constructor() {
    super()
    // Counter for how many characters to reveal
    this.limit = 0
    // Range object used to hide unrevealed text
    this.blind = new Range()
    // Observer that watches for content changes and triggers updates
    this.scout = new MutationObserver(() => {
      this.update()
      if (!this.timer) this.proceed()
    })
    this.lastTranscriptTime = Date.now()
  }

  // Typing speed delays for different punctuation marks (in relative units)
  static delays = {
    " ": 3,
    ",": 8,
    ";": 8,
    ":": 9,
    ".": 10,
    "—": 12,
    "–": 7,
    "!": 15,
    "?": 15,
    "\n": 20,
  }

  // Base typing speed configuration
  static get speedConfig() {
    return {
      min: 30, // Minimum characters per second
      max: 80, // Maximum characters per second
      curve: 2, // Acceleration curve power
    }
  }

  connectedCallback() {
    // Set up CSS highlight API for revealing text gradually
    const css = new CSSStyleSheet()
    css.replaceSync(`::highlight(transparent) { color: transparent }`)
    document.adoptedStyleSheets = [...document.adoptedStyleSheets, css]

    // Initialize the blind range to cover all content
    this.blind.selectNodeContents(this)

    // Create or get the highlight for unrevealed text
    const highlight = CSS.highlights.get("transparent") ?? new Highlight()
    highlight.add(this.blind)
    CSS.highlights.set("transparent", highlight)

    // Start observing content changes
    this.scout.observe(this, {
      childList: true,
      subtree: true,
      characterData: true,
    })

    this.proceed()
  }

  disconnectedCallback() {
    this.scout.disconnect()
    CSS.highlights.get("transparent")?.delete(this.blind)
    clearTimeout(this.timer)
  }

  update() {
    // Walk through text nodes to find where to place the blind range
    const walk = document.createTreeWalker(this, NodeFilter.SHOW_TEXT)
    let node = null
    let limit = this.limit

    while ((node = walk.nextNode())) {
      const length = node.data.slice(0, limit).length
      limit -= length
      if (limit <= 0) {
        // Found the node where the reveal cutoff should be
        this.blind.setStart(node, length)
        break
      }
    }

    if (limit > 0) {
      // If we've revealed all text, reset blind to start
      this.blind.setStart(this, 0)
    }

    // Always set blind to end after all content
    this.blind.setEndAfter(this)
  }

  proceed() {
    if (this.blind.toString().trim() === "") {
      this.timer = undefined
      this.dispatchEvent(new CustomEvent("typingComplete"))
      return
    }

    this.limit = Math.min(this.limit + 1, this.innerText.length)
    this.update()

    const remainingText = this.blind.toString()
    const totalLength = this.innerText.length
    const speed = this.calculateSpeed(totalLength, remainingText)

    this.timer = setTimeout(() => this.proceed(), 1000 / speed)
  }

  calculateSpeed(totalLength, remainingText) {
    const { min, max, curve } = TypeWriter.speedConfig
    const speedRange = max - min
    const progress = 1 - remainingText.length / totalLength
    const baseSpeed = min + speedRange * progress ** curve
    const nextChar = remainingText[0]
    return baseSpeed / (TypeWriter.delays[nextChar] ?? 1)
  }

  setSpeed(multiplier) {
    const { min, max } = TypeWriter.speedConfig
    TypeWriter.speedConfig.min = min * multiplier
    TypeWriter.speedConfig.max = max * multiplier
  }
}

customElements.define("type-writer", TypeWriter)
