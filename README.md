# Bubble

![Bubble Froth](froth.jpg)

An experimental framework exploring personal knowledge spaces and their
interconnections. It aims to create environments where formal semantics,
natural language, and computation flow together like a carefully crafted
Belgian tripel.

## The Bubble Metaphor

A bubble is a personal world of knowledge, capabilities, and commitments -
your epistemological horizon. Like all living things, we exist in our own
local, particular spheres of understanding and action. But bubbles aren't
isolated:

- Each bubble is a Git repository containing RDF graphs and N3 rules
- Bubbles can link to other bubbles, forming what we call "froth"
- Froth is a mesh network of knowledge spaces, carefully brewed together
- Bubbles can replicate across machines while maintaining their identity
- The system maintains awareness of its own distributed nature

This metaphor plays with the tension between necessary insularity (we all live
in our bubbles) and meaningful connection (bubbles touch, merge, and
interact). The goal isn't to "break out" of our bubbles, but to make them more
transparent, structured, and interlinked.

## Vision

Bubble explores what computing might look like if we move beyond traditional
information management paradigms toward a unified semantic foundation. Key
ideas:

- Using knowledge graphs as a formal grounding layer for both LLMs and humans
- Treating computation itself as a semantic domain that can be reasoned about
- Breaking down the walls between "apps" through shared semantic understanding
- Creating fluid interfaces between natural and formal languages
- Building a "froth" of interconnected personal knowledge spaces

The project combines:

- RDF/N3 for knowledge representation
- Logic programming through Prolog and the EYE reasoner
- Modern web tech (FastAPI, HTMX, Tailwind)
- Language models (via Anthropic's Claude)
- Structured concurrency with Trio

## Current State

This is an exploratory research project, currently focusing on:

- `bubble/repo.py`: Git-based RDF/N3 document management
- `bubble/mind.py`: EYE reasoner integration for logical inference
- `bubble/http.py`: Web interface with HTMX for fluid interactions
- `bubble/main.py`: CLI interface with LLM-powered graph exploration

The system maintains a knowledge graph about its own state and capabilities,
which serves as both:

1. A formal model that can be reasoned about by the system
2. A grounding context for language model interactions

## Prerequisites

- Python 3.13+
- Node.js (for Tailwind CSS)
- SWI-Prolog: A modern implementation of Prolog, the original logical
  programming language. While often overlooked in today's landscape, Prolog
  represents one of computing's most elegant approaches to knowledge
  representation and reasoning.
- EYE reasoner (clone from https://github.com/josd/eye)
- Git
- API keys for language models (currently Claude)

## Quick Start

```bash
# Clone the repository
git clone https://github.com/lessrest/bubble.git
cd bubble

# Create Python virtual environment
uv venv

# Option 1: Using direnv (recommended)
# First install direnv (https://direnv.net)
# The .envrc will automatically activate the venv
direnv allow

# Option 2: Manual venv activation
source .venv/bin/activate

# Install dependencies
uv sync

# Install Node.js dependencies
npm install

# Set up your environment
cp .env.example .env
# Edit .env to add your API keys

# Start the development environment
overmind start
```

This will start:

- FastAPI server on http://localhost:8000
- Tailwind CSS watcher
- pytest watcher

## Development

The project uses Overmind to manage the development processes. The `Procfile`
defines three main services:

- `server`: The FastAPI application
- `css`: Tailwind CSS watcher
- `test`: pytest watcher

Key commands:

```bash
# Start all development processes
overmind start

# Connect to a specific process
overmind connect server
overmind connect css
overmind connect test

# Explore your bubble's knowledge graph with LLM assistance
python -m bubble.cli show
```

## Project Structure

- `/bubble`: Core Python package
  - `repo.py`: RDF/N3 document management
  - `mind.py`: EYE reasoner + LLM integration
  - `http.py`: Web interface
  - `main.py`: CLI interface
- `/vocab`: RDF vocabularies and ontologies
- `/rules`: N3 rules for inference
- `/static`: Frontend assets

## Design Philosophy

Bubble explores several ambitious ideas:

1. **Semantic Grounding**

   - Using RDF as a formal foundation for system state
   - Grounding LLM interactions in verifiable knowledge
   - Making formal semantics accessible through natural language

2. **Unified Computation**

   - Breaking down application boundaries through shared semantics
   - Treating all computation as queryable/manipulable knowledge
   - Using rules and inference instead of traditional programming

3. **Fluid Interfaces**

   - Seamless transitions between formal and natural language
   - UI as a projection of semantic knowledge
   - Direct manipulation of the knowledge graph through conversation

4. **Agent Architecture**

   - LLMs as interpreters between human intent and formal semantics
   - Knowledge graph as shared context for human-AI collaboration
   - Reasoning about capabilities and permissions through formal logic

5. **The Froth**
   - Distributed networks of personal knowledge spaces
   - Git as a synchronization and distribution layer
   - Bubbles that know about their own distributed nature
   - Careful brewing of shared understanding

The project is intentionally experimental and speculative, focusing on
exploring new paradigms rather than traditional application development. Like
the Trappist monks and their dedication to brewing excellence, we're
interested in crafting something with depth, character, and a touch of the
divine.

## Contributing

Since this is an exploratory project, contributions should focus on

- experimenting with novel human-AI interaction patterns;
- exploring different approaches to semantic grounding;
- improving the fluidity between formal and natural language;
- adding interesting domains to reason about; or, especially,
- brewing new ways for bubbles to interact and form froth.

## License

This project is licensed under the
[GNU Affero General Public License v3.0 or later](LICENSE.md).

The AGPL is chosen deliberately. If you run a modified version of Bubble as a
service, you must share your modifications with your users. This aligns with
our vision of collaborative knowledge and transparent computation.
