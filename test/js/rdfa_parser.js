const fs = require("fs")
const RdfaParser = require("rdfa-streaming-parser").RdfaParser
const N3 = require("n3")

function parseRdfaToNquads(htmlPath) {
  const parser = new RdfaParser({
    baseIRI: "http://example.org/",
    contentType: "text/html",
  })

  let quads = []
  const writer = new N3.Writer({ format: "N-Quads" })

  fs.createReadStream(htmlPath)
    .pipe(parser)
    .on("data", (quad) => {
      console.error("Parsed quad:", quad)
      quads.push(quad)
    })
    .on("error", (error) => {
      console.error("Parser error:", error)
      process.exit(1)
    })
    .on("end", () => {
      writer.addQuads(quads)
      writer.end((error, result) => {
        if (error) {
          console.error("Writer error:", error)
          process.exit(1)
        }
        console.log(result)
      })
    })
}

if (require.main === module) {
  const htmlPath = process.argv[2]
  if (!htmlPath) {
    console.error("Please provide an HTML file path")
    process.exit(1)
  }
  parseRdfaToNquads(htmlPath)
}
