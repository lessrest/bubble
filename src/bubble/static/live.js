document.addEventListener("DOMContentLoaded", function () {
  const s = window.location.protocol === "https:" ? "s" : ""
  const ws = new WebSocket(`ws${s}://${window.location.host}/live`)
  ws.onmessage = function (event) {
    const { id, html, action } = JSON.parse(event.data)
    const element = document.getElementById(id)
    document.startViewTransition(() => {
      if (action === "append") {
        element.insertAdjacentHTML("beforeend", html)
      } else if (action === "replace") {
        element.innerHTML = html
      } else if (action === "prepend") {
        element.insertAdjacentHTML("afterbegin", html)
      }
      htmx.process(element)
    })
  }
  ws.onopen = function () {
    for (const element of document.querySelectorAll(".live")) {
      ws.send(
        JSON.stringify({
          action: "subscribe",
          id: element.id,
        })
      )
    }
  }
  ws.onclose = function () {}

  const observer = new MutationObserver((mutations) => {
    mutations.forEach(({ type, addedNodes, removedNodes }) => {
      if (type === "childList") {
        const processNodes = (nodes, action) => {
          nodes.forEach((node) => {
            if (node.nodeType === Node.ELEMENT_NODE) {
              const liveNodes = [
                ...node.querySelectorAll(".live"),
                ...(node.classList.contains("live") ? [node] : []),
              ]
              liveNodes.forEach((liveNode) => {
                ws.send(JSON.stringify({ action, id: liveNode.id }))
              })
            }
          })
        }

        processNodes(removedNodes, "unsubscribe")
        processNodes(addedNodes, "subscribe")
      }
    })
  })

  observer.observe(document.body, {
    childList: true,
    subtree: true,
  })
})
